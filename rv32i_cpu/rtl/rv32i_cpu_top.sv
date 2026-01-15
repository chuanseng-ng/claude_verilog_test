// RV32I CPU Top - Top-level module integrating CPU core with AXI4-Lite and APB interfaces
module rv32i_cpu_top
    import rv32i_pkg::*;
    import axi4lite_pkg::*;
(
    input  logic                      clk,
    input  logic                      rst_n,

    // =========================================================================
    // AXI4-Lite Master Interface (Memory)
    // =========================================================================
    // Write Address Channel
    output logic [AXI_ADDR_WIDTH-1:0] m_axi_awaddr,
    output logic                      m_axi_awvalid,
    input  logic                      m_axi_awready,

    // Write Data Channel
    output logic [AXI_DATA_WIDTH-1:0] m_axi_wdata,
    output logic [AXI_STRB_WIDTH-1:0] m_axi_wstrb,
    output logic                      m_axi_wvalid,
    input  logic                      m_axi_wready,

    // Write Response Channel
    input  logic [1:0]                m_axi_bresp,
    input  logic                      m_axi_bvalid,
    output logic                      m_axi_bready,

    // Read Address Channel
    output logic [AXI_ADDR_WIDTH-1:0] m_axi_araddr,
    output logic                      m_axi_arvalid,
    input  logic                      m_axi_arready,

    // Read Data Channel
    input  logic [AXI_DATA_WIDTH-1:0] m_axi_rdata,
    input  logic [1:0]                m_axi_rresp,
    input  logic                      m_axi_rvalid,
    output logic                      m_axi_rready,

    // =========================================================================
    // APB3 Slave Interface (Debug)
    // =========================================================================
    input  logic [11:0]               s_apb_paddr,
    input  logic                      s_apb_psel,
    input  logic                      s_apb_penable,
    input  logic                      s_apb_pwrite,
    input  logic [31:0]               s_apb_pwdata,
    output logic [31:0]               s_apb_prdata,
    output logic                      s_apb_pready,
    output logic                      s_apb_pslverr
);

    // =========================================================================
    // Internal Signals
    // =========================================================================

    // Memory interface (between core and AXI master)
    logic [XLEN-1:0] mem_addr;
    logic [XLEN-1:0] mem_wdata;
    logic [3:0]      mem_wstrb;
    logic [XLEN-1:0] mem_rdata;
    logic            mem_req;
    logic            mem_we;
    logic            mem_ready;
    logic            mem_valid;

    // Debug signals
    logic            dbg_halt_req;
    logic            dbg_resume_req;
    logic            dbg_step_req;
    logic            dbg_reset_req;
    logic            dbg_halted;
    halt_cause_e     dbg_halt_cause;

    // Debug PC access
    logic            dbg_pc_we;
    logic [XLEN-1:0] dbg_pc_wdata;
    logic [XLEN-1:0] dbg_pc_rdata;
    logic [ILEN-1:0] dbg_instr;

    // Debug register access
    logic [REG_ADDR_WIDTH-1:0] dbg_reg_addr;
    logic [XLEN-1:0]           dbg_reg_wdata;
    logic                      dbg_reg_we;
    logic [XLEN-1:0]           dbg_reg_rdata;

    // Breakpoint signals
    logic [XLEN-1:0] bp0_addr;
    logic            bp0_en;
    logic [XLEN-1:0] bp1_addr;
    logic            bp1_en;
    logic            bp_hit;
    logic [1:0]      bp_index;

    // Reset synchronization
    logic rst_n_sync;
    logic rst_n_meta;

    // =========================================================================
    // Reset Synchronizer
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rst_n_meta <= 1'b0;
            rst_n_sync <= 1'b0;
        end else begin
            rst_n_meta <= 1'b1;
            rst_n_sync <= rst_n_meta;
        end
    end

    // Combined reset (external or debug-initiated)
    logic combined_rst_n;
    assign combined_rst_n = rst_n_sync && !dbg_reset_req;

    // =========================================================================
    // CPU Core
    // =========================================================================
    rv32i_core u_core (
        .clk            (clk),
        .rst_n          (combined_rst_n),

        // Memory interface
        .mem_addr       (mem_addr),
        .mem_wdata      (mem_wdata),
        .mem_wstrb      (mem_wstrb),
        .mem_rdata      (mem_rdata),
        .mem_req        (mem_req),
        .mem_we         (mem_we),
        .mem_ready      (mem_ready),
        .mem_valid      (mem_valid),

        // Debug interface
        .dbg_halt_req   (dbg_halt_req),
        .dbg_resume_req (dbg_resume_req),
        .dbg_step_req   (dbg_step_req),
        .dbg_pc_we      (dbg_pc_we),
        .dbg_pc_wdata   (dbg_pc_wdata),
        .dbg_pc_rdata   (dbg_pc_rdata),
        .dbg_instr      (dbg_instr),
        .dbg_halted     (dbg_halted),
        .dbg_halt_cause (dbg_halt_cause),

        // Debug register access
        .dbg_reg_addr   (dbg_reg_addr),
        .dbg_reg_wdata  (dbg_reg_wdata),
        .dbg_reg_we     (dbg_reg_we),
        .dbg_reg_rdata  (dbg_reg_rdata),

        // Breakpoint
        .bp_hit         (bp_hit)
    );

    // =========================================================================
    // AXI4-Lite Master Interface
    // =========================================================================
    axi4lite_master u_axi_master (
        .clk            (clk),
        .rst_n          (combined_rst_n),

        // Simple memory interface
        .mem_addr       (mem_addr),
        .mem_wdata      (mem_wdata),
        .mem_wstrb      (mem_wstrb),
        .mem_rdata      (mem_rdata),
        .mem_req        (mem_req),
        .mem_we         (mem_we),
        .mem_ready      (mem_ready),
        .mem_valid      (mem_valid),

        // AXI4-Lite interface
        .m_axi_awaddr   (m_axi_awaddr),
        .m_axi_awvalid  (m_axi_awvalid),
        .m_axi_awready  (m_axi_awready),
        .m_axi_wdata    (m_axi_wdata),
        .m_axi_wstrb    (m_axi_wstrb),
        .m_axi_wvalid   (m_axi_wvalid),
        .m_axi_wready   (m_axi_wready),
        .m_axi_bresp    (m_axi_bresp),
        .m_axi_bvalid   (m_axi_bvalid),
        .m_axi_bready   (m_axi_bready),
        .m_axi_araddr   (m_axi_araddr),
        .m_axi_arvalid  (m_axi_arvalid),
        .m_axi_arready  (m_axi_arready),
        .m_axi_rdata    (m_axi_rdata),
        .m_axi_rresp    (m_axi_rresp),
        .m_axi_rvalid   (m_axi_rvalid),
        .m_axi_rready   (m_axi_rready)
    );

    // =========================================================================
    // APB3 Slave Interface (Debug)
    // =========================================================================
    apb3_slave u_apb_slave (
        .clk            (clk),
        .rst_n          (rst_n_sync),

        // APB interface
        .paddr          (s_apb_paddr),
        .psel           (s_apb_psel),
        .penable        (s_apb_penable),
        .pwrite         (s_apb_pwrite),
        .pwdata         (s_apb_pwdata),
        .prdata         (s_apb_prdata),
        .pready         (s_apb_pready),
        .pslverr        (s_apb_pslverr),

        // Debug control
        .dbg_halt_req   (dbg_halt_req),
        .dbg_resume_req (dbg_resume_req),
        .dbg_step_req   (dbg_step_req),
        .dbg_reset_req  (dbg_reset_req),

        // Debug status
        .dbg_halted     (dbg_halted),
        .dbg_halt_cause (dbg_halt_cause),

        // PC access
        .dbg_pc_we      (dbg_pc_we),
        .dbg_pc_wdata   (dbg_pc_wdata),
        .dbg_pc_rdata   (dbg_pc_rdata),

        // Instruction
        .dbg_instr      (dbg_instr),

        // Register access
        .dbg_reg_addr   (dbg_reg_addr),
        .dbg_reg_wdata  (dbg_reg_wdata),
        .dbg_reg_we     (dbg_reg_we),
        .dbg_reg_rdata  (dbg_reg_rdata),

        // Breakpoints
        .bp0_addr       (bp0_addr),
        .bp0_en         (bp0_en),
        .bp1_addr       (bp1_addr),
        .bp1_en         (bp1_en)
    );

    // =========================================================================
    // Debug Controller (Breakpoints)
    // =========================================================================
    rv32i_debug u_debug (
        .clk            (clk),
        .rst_n          (combined_rst_n),

        // PC
        .pc             (dbg_pc_rdata),

        // Breakpoint configuration
        .bp0_addr       (bp0_addr),
        .bp0_en         (bp0_en),
        .bp1_addr       (bp1_addr),
        .bp1_en         (bp1_en),

        // Breakpoint hit
        .bp_hit         (bp_hit),
        .bp_index       (bp_index)
    );

endmodule
