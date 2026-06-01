// interrupt_controller.sv
// Phase 5 (M4) — Level-sensitive interrupt controller, AXI4-Lite slave.
//
// Register map (word indices into the axi_lite_register_bank):
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
// Lint target: verilator -Wall 0 errors 0 warnings.

`default_nettype none

module interrupt_controller
    import axi_pkg::*;
#(
    parameter int unsigned ADDR_W    = 12,   // AXI-Lite local address width
    parameter int unsigned N_SOURCES = 5     // number of interrupt sources
) (
    input  logic clk,
    input  logic rst_n,

    // =========================================================================
    // AXI4-Lite slave — control/status registers
    // Port names match axi_lite_register_bank.sv exactly so the sub-module
    // connection is positional-free.
    // =========================================================================
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] s_axil_awaddr,
    input  logic [2:0]        s_axil_awprot,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic              s_axil_awvalid,
    output logic              s_axil_awready,
    input  logic [31:0]       s_axil_wdata,
    input  logic [3:0]        s_axil_wstrb,
    input  logic              s_axil_wvalid,
    output logic              s_axil_wready,
    output logic [1:0]        s_axil_bresp,
    output logic              s_axil_bvalid,
    input  logic              s_axil_bready,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] s_axil_araddr,
    input  logic [2:0]        s_axil_arprot,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic              s_axil_arvalid,
    output logic              s_axil_arready,
    output logic [31:0]       s_axil_rdata,
    output logic [1:0]        s_axil_rresp,
    output logic              s_axil_rvalid,
    input  logic              s_axil_rready,

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

    axi_lite_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .RESET_VAL (RESET_VAL),
        .WMASK     (WMASK)
    ) u_regbank (
        .clk            (clk),
        .rst_n          (rst_n),
        .s_axil_awaddr  (s_axil_awaddr),
        .s_axil_awprot  (s_axil_awprot),
        .s_axil_awvalid (s_axil_awvalid),
        .s_axil_awready (s_axil_awready),
        .s_axil_wdata   (s_axil_wdata),
        .s_axil_wstrb   (s_axil_wstrb),
        .s_axil_wvalid  (s_axil_wvalid),
        .s_axil_wready  (s_axil_wready),
        .s_axil_bresp   (s_axil_bresp),
        .s_axil_bvalid  (s_axil_bvalid),
        .s_axil_bready  (s_axil_bready),
        .s_axil_araddr  (s_axil_araddr),
        .s_axil_arprot  (s_axil_arprot),
        .s_axil_arvalid (s_axil_arvalid),
        .s_axil_arready (s_axil_arready),
        .s_axil_rdata   (s_axil_rdata),
        .s_axil_rresp   (s_axil_rresp),
        .s_axil_rvalid  (s_axil_rvalid),
        .s_axil_rready  (s_axil_rready),
        .regs_o         (regs_o),
        .hw_wen_i       (hw_wen_i),
        .hw_wdata_i     (hw_wdata_i)
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
