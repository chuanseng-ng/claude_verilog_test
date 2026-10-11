// interrupt_controller.sv
// Phase 5 (M4) — Level-sensitive interrupt controller.
// APB migration PR-5: converted from AXI4-Lite slave to APB4 slave.
//
// Register map (word indices into the apb4_register_bank):
//   0  IRQ_STATUS        RO  [N_SOURCES-1:0] = synchronised raw source levels
//   1  IRQ_MASK          RW  [N_SOURCES-1:0] = per-source enable (1 = enabled)
//   2  IRQ_PENDING_MASKED RO  [N_SOURCES-1:0] = IRQ_STATUS & IRQ_MASK
//
// irq_src_i bit assignments (module default N_SOURCES=5; soc_top.sv instantiates
// with N_SOURCES=12 as of Phase 6, bead claude_verilog_test-f7vs.2 — bit 6 (PWM) is
// live as of Phase 6a-2 (bead claude_verilog_test-f7vs.6), bit 7 (WDT) as of Phase 6a-3
// (bead claude_verilog_test-f7vs.7), bit 8 (TRNG) as of Phase 6a-4
// (bead claude_verilog_test-f7vs.8), bit 9 (I2C) as of Phase 6a-5 (bead
// claude_verilog_test-f7vs.9), bit 10 (CRYPTO) as of Phase 6b (bead
// claude_verilog_test-f7vs.10), bit 11 (NPU) as of Phase 6c (bead
// claude_verilog_test-f7vs.11)):
//   [0] UART  [1] SPI  [2] TIMER  [3] DMA  [4] GPU  [5] GPIO  [6] PWM  [7] WDT
//   [8] TRNG  [9] I2C  [10] CRYPTO  [11] NPU  (soc_top.sv only)
//
// irq_o → CPU ext_irq_i (MEIP in RISC-V M-mode).
// Sources are level-sensitive; no W1C.  SW clears by masking at IRQ_MASK
// or by having the peripheral clear its own IRQ output.
//
// APB4 interface (ARM IHI0024C):
//   pclk = clk, presetn = rst_n (active-low synchronous reset)
//   ADDR_W = 12 (byte address; [1:0] unused, word-aligned)
//   Zero wait states: pready driven 1 every ACCESS phase.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module interrupt_controller
#(
    parameter int unsigned ADDR_W    = 12,   // APB4 local address width
    parameter int unsigned N_SOURCES = 5     // number of interrupt sources
) (
    input  logic clk,
    input  logic rst_n,

    // =========================================================================
    // APB4 slave — control/status registers
    // pclk = clk, presetn = rst_n (active-low).
    // SETUP  phase: psel=1, penable=0 (one cycle).
    // ACCESS phase: psel=1, penable=1; transfer complete when pready=1.
    // =========================================================================
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] paddr,   // byte address; [1:0] unused (word-aligned)
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,

    // =========================================================================
    // Interrupt sources and output
    // =========================================================================
    input  logic [N_SOURCES-1:0] irq_src_i,   // raw level inputs from peripherals
    output logic                 irq_o         // → CPU ext_irq_i (MEIP)
);

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned REG_IRQ_STATUS         = 0;
    localparam int unsigned REG_IRQ_MASK           = 1;
    localparam int unsigned REG_IRQ_PENDING_MASKED = 2;
    localparam int unsigned N_REGS                 = 3;

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  // 0 IRQ_STATUS         RO
        32'h0000_0000,  // 1 IRQ_MASK            RW  (all sources disabled at reset)
        32'h0000_0000   // 2 IRQ_PENDING_MASKED  RO
    };

    // WMASK: only IRQ_MASK is SW-writable; STATUS and PENDING_MASKED are RO
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_0000,                          // 0 IRQ_STATUS         RO
        32'(({32{1'b1}} >> (32 - N_SOURCES))),  // 1 IRQ_MASK  [N_SOURCES-1:0]
        32'h0000_0000                           // 2 IRQ_PENDING_MASKED RO
    };

    logic [31:0] regs_o    [N_REGS];
    logic        hw_wen_i  [N_REGS];
    logic [31:0] hw_wdata_i[N_REGS];

    apb4_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .RESET_VAL (RESET_VAL),
        .WMASK     (WMASK)
    ) u_regbank (
        .pclk       (clk),
        .presetn    (rst_n),
        .psel       (psel),
        .penable    (penable),
        .pwrite     (pwrite),
        .paddr      (paddr),
        .pwdata     (pwdata),
        .pstrb      (pstrb),
        .prdata     (prdata),
        .pready     (pready),
        .pslverr    (pslverr),
        .regs_o     (regs_o),
        .hw_wen_i   (hw_wen_i),
        .hw_wdata_i (hw_wdata_i)
    );

    // =========================================================================
    // 2-FF synchroniser for irq_src_i (CDC hardening)
    // irq_src_i originates from peripheral IRQ lines. In soc_top every source
    // is currently synchronous to this clock (core_clk, or the gated copy of it
    // that clocks the GPU), so for today's SoC the chain is a two-cycle
    // retiming stage; it is kept as a real synchroniser so a source that moves
    // to another clock domain stays safe.
    //
    // N_SOURCES independent single-bit cdc_2ff_sync instances (STAGES=2, reset
    // 0), not one WIDTH(N_SOURCES) instance: the sources are independent
    // level-held lines with no cross-bit coherency requirement, and
    // cdc_2ff_sync.sv's scope warning forbids a multi-bit binary bus. Same
    // pattern as gpio_controller.sv (g_in_sync). Behaviour vs the previous
    // hand-written chain: same 2-cycle latency and same reset value (0); the
    // reset is now asserted asynchronously by the primitive (see the
    // cdc_2ff_sync header) where it was synchronous here.
    // =========================================================================
    logic [N_SOURCES-1:0] irq_src_sync_q;   // synchronised source

    genvar s;
    generate
        for (s = 0; s < N_SOURCES; s++) begin : g_irq_sync
            cdc_2ff_sync #(
                .WIDTH  (1),
                .STAGES (2)
            ) u_irq_sync (
                .clk_i   (clk),
                .rst_n_i (rst_n),
                .d_i     (irq_src_i[s]),
                .q_o     (irq_src_sync_q[s])
            );
        end
    endgenerate

    // =========================================================================
    // Masking logic
    // =========================================================================
    logic [N_SOURCES-1:0] masked;

    assign masked = irq_src_sync_q & regs_o[REG_IRQ_MASK][N_SOURCES-1:0];

    // =========================================================================
    // HW-writeback — combinational mirrors driven every cycle
    // =========================================================================
    always_comb begin
        // Default all hw_wen_i/hw_wdata_i to inactive
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // IRQ_STATUS: live synchronised raw sources (RO — HW owns this)
        hw_wen_i  [REG_IRQ_STATUS] = 1'b1;
        hw_wdata_i[REG_IRQ_STATUS] = {{(32-N_SOURCES){1'b0}}, irq_src_sync_q};

        // IRQ_PENDING_MASKED: masked sources (RO — HW owns this)
        hw_wen_i  [REG_IRQ_PENDING_MASKED] = 1'b1;
        hw_wdata_i[REG_IRQ_PENDING_MASKED] = {{(32-N_SOURCES){1'b0}}, masked};

        // IRQ_MASK: SW-owned (RW), HW does not write it
        hw_wen_i  [REG_IRQ_MASK] = 1'b0;
        hw_wdata_i[REG_IRQ_MASK] = 32'h0;
    end

    // =========================================================================
    // IRQ output — any unmasked source asserts the CPU interrupt line
    // =========================================================================
    assign irq_o = |masked;

endmodule : interrupt_controller
