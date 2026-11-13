// interrupt_controller - level-sensitive interrupt controller, APB4 slave.
//
// Function: The module synchronises the N_SOURCES raw source levels and ORs the masked sources into irq_o.
//   irq_o drives the CPU ext_irq_i input (MEIP in RISC-V M-mode) through a synchroniser in soc_top. ext_irq_i is a CPU port.
// Registers (word index):
//   0 IRQ_STATUS (RO): [N_SOURCES-1:0] synchronised raw source levels.
//   1 IRQ_MASK (RW): per-source enable, 1 = enabled. Every source is disabled at reset.
//   2 IRQ_PENDING_MASKED (RO): IRQ_STATUS & IRQ_MASK.
// Source bits in soc_top (N_SOURCES = 12): [0] UART, [1] SPI, [2] TIMER, [3] DMA, [4] GPU, [5] GPIO, [6] PWM,
//   [7] WDT, [8] TRNG, [9] I2C, [10] CRYPTO, [11] NPU. The module default is N_SOURCES = 5.
// Parameters: ADDR_W (APB address width, default 12), N_SOURCES (default 5),
//   SYNC_STAGES (irq_src_i synchroniser depth, at least 2, default 2).
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous (pclk = clk, presetn = rst_n).
//   Each source goes through its own single-bit cdc_sync with reset value 0. The primitive asserts that reset asynchronously.
// Caller rules:
//   - Sources are level-sensitive. There is no W1C.
//   - Software clears an interrupt by masking it in IRQ_MASK, or by clearing the peripheral's own IRQ output.
//   - APB access has zero wait states. pready is 1 in every ACCESS phase.
// Doc: ds:mod:interrupt-controller, tm:mod:interrupt-controller, cr:mod:interrupt-controller

module interrupt_controller
#(
    parameter int unsigned ADDR_W      = 12,  // APB4 local address width
    parameter int unsigned N_SOURCES   = 5,   // number of interrupt sources
    parameter int unsigned SYNC_STAGES = 2    // irq_src_i synchroniser depth (>= 2, bead xtaa)
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

    // Synchroniser for irq_src_i: N_SOURCES single-bit cdc_sync instances (reset 0), one per source.
    // The sources are independent level-held lines. cdc_sync forbids a multi-bit binary bus. Same pattern as gpio_controller.
    // The latency is 2 cycles with the default SYNC_STAGES. The primitive asserts the reset asynchronously.
    logic [N_SOURCES-1:0] irq_src_sync_q;   // synchronised source

    genvar s;
    generate
        for (s = 0; s < N_SOURCES; s++) begin : g_irq_sync
            cdc_sync #(
                .WIDTH  (1),
                .STAGES (SYNC_STAGES)
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
