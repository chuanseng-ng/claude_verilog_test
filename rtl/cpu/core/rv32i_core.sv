// rv32i_core.sv
// RV32I CPU Core — 5-Stage Pipelined Implementation (Phase 2)
//
// Replaces the Phase 1 single-cycle FSM with a 5-stage in-order pipeline.
// Module name rv32i_core is preserved for backward compatibility.
//
// New ports vs Phase 1: ext_irq_i, timer_irq_i
// All Phase 1 ports preserved.

import rv32i_pipeline_pkg::*;

module rv32i_core (
    input  logic        clk,
    input  logic        rst_n,

    // ── AXI4-Lite master (unified instruction/data via arbiter) ──────────────
    output logic [31:0] axi_araddr,
    output logic        axi_arvalid,
    input  logic        axi_arready,
    input  logic [31:0] axi_rdata,
    input  logic [1:0]  axi_rresp,
    input  logic        axi_rvalid,
    output logic        axi_rready,
    output logic [31:0] axi_awaddr,
    output logic        axi_awvalid,
    input  logic        axi_awready,
    output logic [31:0] axi_wdata,
    output logic [3:0]  axi_wstrb,
    output logic        axi_wvalid,
    input  logic        axi_wready,
    input  logic [1:0]  axi_bresp,
    input  logic        axi_bvalid,
    output logic        axi_bready,

    // ── Debug interface ───────────────────────────────────────────────────────
    input  logic        dbg_halt_req,
    input  logic        dbg_resume_req,
    input  logic        dbg_step_req,
    output logic        dbg_halted,

    input  logic        dbg_pc_wr_en,
    input  logic [31:0] dbg_pc_wr_data,

    input  logic        dbg_reg_wr_en,
    input  logic [4:0]  dbg_reg_wr_addr,
    input  logic [31:0] dbg_reg_wr_data,
    input  logic [4:0]  dbg_reg_rd_addr,
    output logic [31:0] dbg_reg_rd_data,

    // ── Commit interface (verification observability) ─────────────────────────
    output logic        commit_valid,
    output logic [31:0] commit_pc,
    output logic [31:0] commit_insn,
    output logic        trap_taken,
    output logic [3:0]  trap_cause,

    // ── Debug observability (Phase 1 compatibility) ───────────────────────────
    output logic [31:0] debug_rs1_data,
    output logic [31:0] debug_rs2_data,
    output logic        debug_branch_taken,
    output logic        debug_take_branch_jump,
    output logic        debug_pc_src,
    output logic [3:0]  debug_state,
    output logic        debug_ebreak,

    // ── Interrupt inputs (Phase 2 new) ────────────────────────────────────────
    input  logic        ext_irq_i,
    input  logic        timer_irq_i,

    // ── CSR debug outputs (for APB debug register access at 0x200-0x214) ─────
    output logic [31:0] dbg_csr_mstatus_o,
    output logic [31:0] dbg_csr_mie_o,
    output logic [31:0] dbg_csr_mtvec_o,
    output logic [31:0] dbg_csr_mepc_o,
    output logic [31:0] dbg_csr_mcause_o,
    output logic [31:0] dbg_csr_mip_o,

    // ── IF stage PC (for DBG_PC register — correct value when halted) ─────────
    output logic [31:0] pc_if_o
);

    // =========================================================================
    // Pipeline registers
    // =========================================================================
    if_id_reg_t  if_id_reg;
    id_ex_reg_t  id_ex_reg;
    ex_mem_reg_t ex_mem_reg;
    mem_wb_reg_t mem_wb_reg;

    // =========================================================================
    // Hazard unit outputs
    // =========================================================================
    logic        stall_pc, stall_if_id, stall_id_ex, stall_ex_mem;
    logic        flush_if_id, flush_id_ex;
    logic [1:0]  fwd_a_sel, fwd_b_sel, fwd_store_sel;

    // =========================================================================
    // Stall signals (from pipeline stages / arbiter)
    // =========================================================================
    logic if_axi_stall, mem_axi_stall;

    // =========================================================================
    // PC redirect signals
    // =========================================================================
    logic        ex_pc_redirect;
    logic [31:0] ex_pc_target;
    logic        jal_redirect;
    logic [31:0] jal_target;

    // =========================================================================
    // Register file signals (core-level instantiation)
    // =========================================================================
    logic [4:0]  rf_rs1_addr, rf_rs2_addr;
    logic [31:0] rf_rs1_data, rf_rs2_data;
    logic        rf_wr_en;
    logic [4:0]  rf_wr_addr;
    logic [31:0] rf_wr_data;

    // =========================================================================
    // CSR file signals
    // =========================================================================
    logic        csr_wr_en;
    logic        csr_rd_access;  // Pure decode (no !csr_illegal feedback) for csr_file.csr_access
    logic [11:0] csr_addr_ex;
    logic [2:0]  csr_op_ex;
    logic [31:0] csr_wdata_ex;
    logic [4:0]  csr_rs1_addr_ex;
    logic [31:0] csr_rdata;
    logic        csr_illegal;
    logic [31:0] mtvec;
    logic [31:0] mret_pc_val;
    logic        mstatus_mie, mstatus_mie_eff, mie_mtie, mie_meie;
    logic [31:0] mip;
    logic        trap_entry;
    logic [31:0] trap_pc_val, trap_cause_val;
    logic        mret_ex;

    // =========================================================================
    // Interrupt controller signals
    // =========================================================================
    logic        irq_valid;
    logic [31:0] irq_cause;
    logic        ext_irq_pending, timer_irq_pending;

    // =========================================================================
    // Forwarding unit outputs
    // =========================================================================
    logic [31:0] fwd_rs1, fwd_rs2, fwd_store;

    // =========================================================================
    // Debug signals
    // =========================================================================
    logic        dbg_halted_wb;     // from WB stage
    logic        dbg_halted_if;     // from IF stage (fetch stopped)
    logic        dbg_halt_combined; // combined halt request
    logic        dbg_ebreak_from_ex;// EBREAK halt request from EX stage

    // Combined halt: APB request, EBREAK, or single-step
    assign dbg_halt_combined = dbg_halt_req || dbg_ebreak_from_ex;
    // The pipeline must be fully drained before signalling halt.
    // Checking only !mem_wb_reg.valid is insufficient: if EX/MEM still holds a valid
    // instruction it will arrive at WB the next cycle, dropping dbg_halted_wb to 0 and
    // triggering the cpu_top auto-clear that permanently deasserts halt_req.
    assign dbg_halted = dbg_halted_wb && !id_ex_reg.valid && !ex_mem_reg.valid;

    logic [31:0] pc_if_out;   // IF-stage PC register (fetch address)

    // =========================================================================
    // AXI arbiter IF interface signals
    // =========================================================================
    logic [31:0] if_araddr;
    logic        if_arvalid;
    logic        if_arready;
    logic [31:0] if_rdata;
    logic [1:0]  if_rresp;
    logic        if_rvalid;
    logic        if_rready;

    // =========================================================================
    // AXI arbiter MEM interface signals
    // =========================================================================
    logic [31:0] mem_araddr;
    logic        mem_arvalid;
    logic        mem_arready;
    logic [31:0] mem_rdata;
    logic [1:0]  mem_rresp;
    logic        mem_rvalid;
    logic        mem_rready;
    logic [31:0] mem_awaddr;
    logic        mem_awvalid;
    logic        mem_awready;
    logic [31:0] mem_wdata;
    logic [3:0]  mem_wstrb;
    logic        mem_wvalid;
    logic        mem_wready;
    logic        mem_bvalid;
    logic [1:0]  mem_bresp;
    logic        mem_bready;

    // =========================================================================
    // Hazard Unit
    // =========================================================================
    rv32i_hazard_unit u_hazard (
        .id_ex_rs1_addr    (id_ex_reg.rs1_addr),
        .id_ex_rs2_addr    (id_ex_reg.rs2_addr),
        .id_ex_rd_addr     (id_ex_reg.rd_addr),
        .id_ex_mem_rd      (id_ex_reg.mem_rd),
        .id_ex_reg_wr_en   (id_ex_reg.reg_wr_en),
        .ex_mem_rd_addr    (ex_mem_reg.rd_addr),
        .ex_mem_reg_wr_en  (ex_mem_reg.reg_wr_en),
        .ex_mem_mem_rd     (ex_mem_reg.mem_rd),
        .mem_wb_rd_addr    (mem_wb_reg.rd_addr),
        .mem_wb_reg_wr_en  (mem_wb_reg.reg_wr_en),
        .if_id_rs1_addr    (if_id_reg.instruction[19:15]),
        .if_id_rs2_addr    (if_id_reg.instruction[24:20]),
        .if_axi_stall      (if_axi_stall),
        .mem_axi_stall     (mem_axi_stall),
        .ex_pc_redirect    (ex_pc_redirect),
        .id_jal_taken      (jal_redirect),
        .stall_pc          (stall_pc),
        .stall_if_id       (stall_if_id),
        .stall_id_ex       (stall_id_ex),
        .stall_ex_mem      (stall_ex_mem),
        .flush_if_id       (flush_if_id),
        .flush_id_ex       (flush_id_ex),
        .fwd_a_sel         (fwd_a_sel),
        .fwd_b_sel         (fwd_b_sel),
        .fwd_store_sel     (fwd_store_sel)
    );

    // =========================================================================
    // Forwarding Unit
    // =========================================================================
    rv32i_forwarding_unit u_fwd (
        .fwd_a_sel          (fwd_a_sel),
        .fwd_b_sel          (fwd_b_sel),
        .fwd_store_sel      (fwd_store_sel),
        .id_ex_rs1_data     (id_ex_reg.rs1_data),
        .id_ex_rs2_data     (id_ex_reg.rs2_data),
        .ex_mem_alu_result  (ex_mem_reg.alu_result),
        .ex_mem_csr_rdata   (ex_mem_reg.csr_rdata),
        .ex_mem_pc          (ex_mem_reg.pc),
        .ex_mem_csr_access  (ex_mem_reg.csr_access),
        .ex_mem_jump        (ex_mem_reg.jump),
        .mem_wb_alu_result  (mem_wb_reg.alu_result),
        .mem_wb_mem_rdata   (mem_wb_reg.mem_rdata),
        .mem_wb_csr_rdata   (mem_wb_reg.csr_rdata),
        .mem_wb_pc          (mem_wb_reg.pc),
        .mem_wb_mem_rd      (mem_wb_reg.mem_rd),
        .mem_wb_csr_access  (mem_wb_reg.csr_access),
        .mem_wb_jump        (mem_wb_reg.jump),
        .fwd_rs1            (fwd_rs1),
        .fwd_rs2            (fwd_rs2),
        .fwd_store          (fwd_store)
    );

    // =========================================================================
    // CSR File
    // =========================================================================
    // csr_rd_access: pure decode signal (no !csr_illegal feedback) used to
    // drive csr_file.csr_access, breaking the combinational loop:
    //   csr_wr_en (uses !csr_illegal) → csr_file.csr_access → csr_illegal
    assign csr_rd_access = id_ex_reg.csr_access && id_ex_reg.valid;

    rv32i_csr_file u_csr (
        .clk              (clk),
        .rst_n            (rst_n),
        .csr_access       (csr_rd_access),
        .csr_addr         (csr_addr_ex),
        .csr_op           (csr_op_ex),
        .csr_wdata        (csr_wdata_ex),
        .rs1_addr         (csr_rs1_addr_ex),
        .trap_entry       (trap_entry),
        .trap_pc          (trap_pc_val),
        .trap_cause       (trap_cause_val),
        .mret             (mret_ex),
        .ext_irq_i        (ext_irq_i),
        .timer_irq_i      (timer_irq_i),
        .csr_rdata        (csr_rdata),
        .csr_illegal      (csr_illegal),
        .mtvec_out        (mtvec),
        .mret_pc          (mret_pc_val),
        .mstatus_mie      (mstatus_mie),
        .mstatus_mie_eff  (mstatus_mie_eff),
        .mie_mtie         (mie_mtie),
        .mie_meie         (mie_meie),
        .mip              (mip),
        .dbg_mstatus_o    (dbg_csr_mstatus_o),
        .dbg_mie_o        (dbg_csr_mie_o),
        .dbg_mcause_o     (dbg_csr_mcause_o)
    );

    // =========================================================================
    // Interrupt Controller
    // =========================================================================
    rv32i_interrupt_ctrl u_irq_ctrl (
        .mstatus_mie       (mstatus_mie_eff),  // OQ-4: use effective MIE
        .mie_mtie          (mie_mtie),
        .mie_meie          (mie_meie),
        .ext_irq_i         (ext_irq_i),
        .timer_irq_i       (timer_irq_i),
        .ext_irq_pending   (ext_irq_pending),
        .timer_irq_pending (timer_irq_pending),
        .irq_valid         (irq_valid),
        .irq_cause         (irq_cause)
    );

    // =========================================================================
    // AXI Arbiter
    // =========================================================================
    rv32i_axi_arbiter u_arbiter (
        .clk              (clk),
        .rst_n            (rst_n),
        // IF side
        .if_araddr_i      (if_araddr),
        .if_arvalid_i     (if_arvalid),
        .if_arready_o     (if_arready),
        .if_rdata_o       (if_rdata),
        .if_rresp_o       (if_rresp),
        .if_rvalid_o      (if_rvalid),
        .if_rready_i      (if_rready),
        // MEM read
        .mem_araddr_i     (mem_araddr),
        .mem_arvalid_i    (mem_arvalid),
        .mem_arready_o    (mem_arready),
        .mem_rdata_o      (mem_rdata),
        .mem_rresp_o      (mem_rresp),
        .mem_rvalid_o     (mem_rvalid),
        .mem_rready_i     (mem_rready),
        // MEM write
        .mem_awaddr_i     (mem_awaddr),
        .mem_awvalid_i    (mem_awvalid),
        .mem_awready_o    (mem_awready),
        .mem_wdata_i      (mem_wdata),
        .mem_wstrb_i      (mem_wstrb),
        .mem_wvalid_i     (mem_wvalid),
        .mem_wready_o     (mem_wready),
        .mem_bready_i     (mem_bready),
        .mem_bvalid_o     (mem_bvalid),
        .mem_bresp_o      (mem_bresp),
        // AXI master
        .axi_araddr_o     (axi_araddr),
        .axi_arvalid_o    (axi_arvalid),
        .axi_arready_i    (axi_arready),
        .axi_rdata_i      (axi_rdata),
        .axi_rresp_i      (axi_rresp),
        .axi_rvalid_i     (axi_rvalid),
        .axi_rready_o     (axi_rready),
        .axi_awaddr_o     (axi_awaddr),
        .axi_awvalid_o    (axi_awvalid),
        .axi_awready_i    (axi_awready),
        .axi_wdata_o      (axi_wdata),
        .axi_wstrb_o      (axi_wstrb),
        .axi_wvalid_o     (axi_wvalid),
        .axi_wready_i     (axi_wready),
        .axi_bvalid_i     (axi_bvalid),
        .axi_bresp_i      (axi_bresp),
        .axi_bready_o     (axi_bready),
        // Stall outputs — left open; IF and MEM stages drive if_axi_stall / mem_axi_stall
        // directly from their own pending-transaction registers (single driver per net).
        /* verilator lint_off PINCONNECTEMPTY */
        .if_axi_stall_o   (),
        .mem_axi_stall_o  ()
        /* verilator lint_on PINCONNECTEMPTY */
    );

    // =========================================================================
    // Register File (core level — read ports used by ID, write by WB)
    // =========================================================================
    rv32i_regfile u_regfile (
        .clk         (clk),
        .rst_n       (rst_n),
        .wr_en       (rf_wr_en),
        .wr_addr     (rf_wr_addr),
        .wr_data     (rf_wr_data),
        .rd_addr1    (rf_rs1_addr),
        .rd_data1    (rf_rs1_data),
        .rd_addr2    (rf_rs2_addr),
        .rd_data2    (rf_rs2_data),
        .dbg_wr_en   (dbg_reg_wr_en),
        .dbg_wr_addr (dbg_reg_wr_addr),
        .dbg_wr_data (dbg_reg_wr_data),
        .dbg_rd_addr (dbg_reg_rd_addr),
        .dbg_rd_data (dbg_reg_rd_data)
    );

    // =========================================================================
    // IF Stage
    // =========================================================================
    rv32i_pipeline_if u_if (
        .clk              (clk),
        .rst_n            (rst_n),
        .stall_pc         (stall_pc),
        .stall_if_id      (stall_if_id),
        .flush_if_id      (flush_if_id),
        .pc_redirect      (ex_pc_redirect),
        .pc_target        (ex_pc_target),
        .jal_redirect     (jal_redirect),
        .jal_target       (jal_target),
        .dbg_halt_req     (dbg_halt_combined),
        .dbg_step_pending (dbg_step_req),      // step_pending_q from cpu_top
        .dbg_pc_wr_en     (dbg_pc_wr_en),
        .dbg_pc_wr_data   (dbg_pc_wr_data),
        .dbg_halted       (dbg_halted_if),
        .if_araddr_o      (if_araddr),
        .if_arvalid_o     (if_arvalid),
        .if_arready_i     (if_arready),
        .if_rdata_i       (if_rdata),
        .if_rresp_i       (if_rresp),
        .if_rvalid_i      (if_rvalid),
        .if_rready_o      (if_rready),
        .if_axi_stall_o   (if_axi_stall),
        .if_id_reg_o      (if_id_reg),
        .pc_out           (pc_if_out)
    );

    // =========================================================================
    // ID Stage
    // =========================================================================
    rv32i_pipeline_id u_id (
        .clk              (clk),
        .rst_n            (rst_n),
        .stall_id_ex      (stall_id_ex),
        .flush_id_ex      (flush_id_ex),
        .if_id_reg_i      (if_id_reg),
        .rf_rs1_addr_o    (rf_rs1_addr),
        .rf_rs1_data_i    (rf_rs1_data),
        .rf_rs2_addr_o    (rf_rs2_addr),
        .rf_rs2_data_i    (rf_rs2_data),
        .jal_redirect_o   (jal_redirect),
        .jal_target_o     (jal_target),
        .id_ex_reg_o      (id_ex_reg)
    );

    // =========================================================================
    // EX Stage
    // =========================================================================
    rv32i_pipeline_ex u_ex (
        .clk              (clk),
        .rst_n            (rst_n),
        .stall_ex_mem     (stall_ex_mem),
        .id_ex_reg_i      (id_ex_reg),
        .fwd_rs1          (fwd_rs1),
        .fwd_rs2          (fwd_rs2),
        .fwd_store        (fwd_store),
        .csr_rdata_i      (csr_rdata),
        .csr_illegal_i    (csr_illegal),
        .irq_valid_i      (irq_valid),
        .irq_cause_i      (irq_cause),
        .mtvec_i          (mtvec),
        .mret_pc_i        (mret_pc_val),
        .ex_pc_redirect_o (ex_pc_redirect),
        .ex_pc_target_o   (ex_pc_target),
        .csr_wr_en_o      (csr_wr_en),
        .csr_wdata_o      (csr_wdata_ex),
        .csr_addr_o       (csr_addr_ex),
        .csr_op_o         (csr_op_ex),
        .rs1_addr_o       (csr_rs1_addr_ex),
        .trap_entry_o     (trap_entry),
        .trap_pc_o        (trap_pc_val),
        .trap_cause_o     (trap_cause_val),
        .mret_o           (mret_ex),
        .dbg_halt_req_o   (dbg_ebreak_from_ex),
        .ex_mem_reg_o     (ex_mem_reg)
    );

    // =========================================================================
    // MEM Stage
    // =========================================================================
    rv32i_pipeline_mem u_mem (
        .clk              (clk),
        .rst_n            (rst_n),
        .ex_mem_reg_i     (ex_mem_reg),
        .mem_araddr_o     (mem_araddr),
        .mem_arvalid_o    (mem_arvalid),
        .mem_arready_i    (mem_arready),
        .mem_rdata_i      (mem_rdata),
        .mem_rresp_i      (mem_rresp),
        .mem_rvalid_i     (mem_rvalid),
        .mem_rready_o     (mem_rready),
        .mem_awaddr_o     (mem_awaddr),
        .mem_awvalid_o    (mem_awvalid),
        .mem_awready_i    (mem_awready),
        .mem_wdata_o      (mem_wdata),
        .mem_wstrb_o      (mem_wstrb),
        .mem_wvalid_o     (mem_wvalid),
        .mem_wready_i     (mem_wready),
        .mem_bvalid_i     (mem_bvalid),
        .mem_bresp_i      (mem_bresp),
        .mem_bready_o     (mem_bready),
        .mem_axi_stall_o  (mem_axi_stall),
        .mem_wb_reg_o     (mem_wb_reg)
    );

    // =========================================================================
    // WB Stage
    // =========================================================================
    rv32i_pipeline_wb u_wb (
        .clk              (clk),
        .rst_n            (rst_n),
        .mem_wb_reg_i     (mem_wb_reg),
        .dbg_halt_req     (dbg_halt_combined),
        .if_stage_idle    (dbg_halted_if),
        .rf_wr_en_o       (rf_wr_en),
        .rf_wr_addr_o     (rf_wr_addr),
        .rf_wr_data_o     (rf_wr_data),
        .dbg_halted       (dbg_halted_wb),
        .commit_valid_o   (commit_valid),
        .commit_pc_o      (commit_pc),
        .commit_insn_o    (commit_insn),
        .trap_taken_o     (trap_taken),
        .trap_cause_o     (trap_cause)
    );

    // =========================================================================
    // Phase 1 debug compatibility outputs
    // Most are not directly meaningful in a pipelined design; tie to safe values
    // to preserve testbench compatibility.
    // =========================================================================
    assign debug_rs1_data         = 32'h0;
    assign debug_rs2_data         = 32'h0;
    assign debug_branch_taken     = 1'b0;
    assign debug_take_branch_jump = ex_pc_redirect;
    assign debug_pc_src           = ex_pc_redirect;
    assign debug_state            = 4'h0;  // No FSM state in Phase 2
    assign debug_ebreak           = dbg_ebreak_from_ex;

    // CSR debug output assignments (mtvec, mepc, mip from existing signals)
    assign dbg_csr_mtvec_o = mtvec;
    assign dbg_csr_mepc_o  = mret_pc_val;
    assign dbg_csr_mip_o   = mip;

    // IF-stage PC output (frozen during halt by rv32i_pipeline_if)
    assign pc_if_o = pc_if_out;

    // dbg_resume_req is consumed by top-level APB logic; not needed in the pipeline.
    /* verilator lint_off UNUSEDSIGNAL */
    logic _unused_resume = dbg_resume_req;
    /* verilator lint_on UNUSEDSIGNAL */
    // dbg_step_req (= step_pending_q from cpu_top) is routed to IF as dbg_step_pending.

endmodule
