// interrupt_controller.sv
// Phase 5 (M4) — Level-sensitive interrupt controller.
// APB migration PR-5: converted from AXI4-Lite slave to APB4 slave.
//
// Register map (word indices into the apb4_register_bank):
//   0  IRQ_STATUS        RO  [N_SOURCES-1:0] = synchronised raw source levels
//   1  IRQ_MASK          RW  [N_SOURCES-1:0] = per-source enable (1 = enabled)
//   2  IRQ_PENDING_MASKED RO  [N_SOURCES-1:0] = IRQ_STATUS & IRQ_MASK
//
// irq_src_i bit assignments (N_SOURCES=5 default):
//   [0] UART  [1] SPI  [2] TIMER  [3] DMA  [4] GPU
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
    // irq_src_i originates from peripheral IRQ lines that may be asynchronous to
    // this clock in a multi-clock SoC; a two-stage synchroniser per bit removes
    // metastability before the level is consumed by masking / status logic.
    // stage1 samples the raw input; stage2 (irq_src_sync_q) is the synced source.
    // =========================================================================
    logic [N_SOURCES-1:0] irq_src_stage1_q;
    logic [N_SOURCES-1:0] irq_src_sync_q;   // stage2 — synchronised source

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            irq_src_stage1_q <= {N_SOURCES{1'b0}};
            irq_src_sync_q   <= {N_SOURCES{1'b0}};
        end else begin
            irq_src_stage1_q <= irq_src_i;
            irq_src_sync_q   <= irq_src_stage1_q;
        end
    end

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
