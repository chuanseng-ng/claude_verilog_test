// rv32i_core.sv
// RV32I CPU Core — 5-Stage Pipelined Implementation (Phase 3)
//
// Phase 3 changes vs Phase 2:
//   - AXI arbiter replaced by I-cache + D-cache + cache arbiter
//   - IF stage uses I-cache interface (ic_addr/valid/rdata/stall)
//   - MEM stage uses D-cache interface (dc_addr/valid/we/wdata/wstrb/rdata/stall)
//   - if_axi_stall / mem_axi_stall renamed to if_cache_stall / mem_cache_stall
//   - FENCE.I: fence_i_o from EX stage wired to I-cache invalidate
//   - External AXI4-Lite interface preserved (cpu_top unchanged)


import rv32i_pipeline_pkg::*;
import rv32i_cache_pkg::*;
module rv32i_core(
    input  logic        clk,
    input  logic        rst_n,

    // ── AXI4-Lite master (unified cache → memory) ────────────────────────────
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

    // ── Commit interface ──────────────────────────────────────────────────────
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

    // ── Interrupt inputs ──────────────────────────────────────────────────────
    input  logic        ext_irq_i,
    input  logic        timer_irq_i,

    // ── CSR debug outputs ─────────────────────────────────────────────────────
    output logic [31:0] dbg_csr_mstatus_o,
    output logic [31:0] dbg_csr_mie_o,
    output logic [31:0] dbg_csr_mtvec_o,
    output logic [31:0] dbg_csr_mepc_o,
    output logic [31:0] dbg_csr_mcause_o,
    output logic [31:0] dbg_csr_mip_o,

    // ── IF stage PC ───────────────────────────────────────────────────────────
    output logic [31:0] pc_if_o
);

    // =========================================================================
    // Pipeline registers
    // =========================================================================
    if_id_reg_t   if_id_reg;
    id_ex_reg_t   id_ex_reg;
    // ex1_ex2_reg removed Run-23: replaced by ex1b_comb (wire) + ex1b_ex2_reg_q (FF)
    ex_mem_reg_t  ex_mem_reg;
    mem_wb_reg_t  mem_wb_reg;

    // =========================================================================
    // Hazard unit outputs
    // =========================================================================
    logic        stall_pc, stall_if_id, stall_id_ex, stall_ex_mem;
    logic        stall_ex1_ex2, stall_ex1a_ex1b, stall_ex1c_ex1b;
    logic        flush_if_id, flush_id_ex, flush_ex_mem;
    logic        flush_ex1_ex2, flush_ex1a_ex1b, flush_ex1c_ex1b;

    // Forwarding unit EX1c tier selects
    logic        fwd_a_ex1c, fwd_b_ex1c, fwd_store_ex1c;
    // Forwarding unit EX1b2 tier selects (Run-23: new ex1b_ex2_reg_q tier)
    logic        fwd_a_ex1b2, fwd_b_ex1b2, fwd_store_ex1b2;
    logic [1:0]  fwd_a_sel, fwd_b_sel, fwd_store_sel;

    // Pre-decoded forwarding selects (from hazard unit, registered for timing)
    logic [1:0] fwd_a_sel_pre_w, fwd_b_sel_pre_w;
    logic       fwd_a_ex1c_pre_w, fwd_b_ex1c_pre_w;
    logic       fwd_a_ex1b2_pre_w, fwd_b_ex1b2_pre_w;
    logic [1:0] fwd_a_sel_r, fwd_b_sel_r, fwd_store_sel_r;
    logic       fwd_a_ex1c_r, fwd_b_ex1c_r, fwd_store_ex1c_r;
    logic       fwd_a_ex1b2_r, fwd_b_ex1b2_r, fwd_store_ex1b2_r;

    // =========================================================================
    // Cache stall signals (Phase 3: renamed from axi_stall)
    // =========================================================================
    logic if_cache_stall, mem_cache_stall;

    // =========================================================================
    // PC redirect signals
    // =========================================================================
    logic        ex_pc_redirect;
    logic [31:0] ex_pc_target;
    logic        jal_redirect;
    logic [31:0] jal_target;

    // MEM-stage misaligned trap signals (combinational, from u_mem)
    logic        mem_trap_redirect;
    logic [31:0] mem_trap_target;
    logic        mem_trap_entry;
    logic [31:0] mem_trap_pc_val, mem_trap_cause_val;

    // Registered MEM-trap signals — breaks MEM→IF combinational feedback (timing fix)
    logic        mem_trap_redirect_r;
    logic [31:0] mem_trap_target_r;
    logic        mem_trap_entry_r;
    logic [31:0] mem_trap_pc_val_r, mem_trap_cause_val_r;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            mem_trap_redirect_r  <= 1'b0;
            mem_trap_entry_r     <= 1'b0;
            mem_trap_target_r    <= '0;
            mem_trap_pc_val_r    <= '0;
            mem_trap_cause_val_r <= '0;
        end else begin
            mem_trap_redirect_r  <= mem_trap_redirect;
            mem_trap_entry_r     <= mem_trap_entry;
            mem_trap_target_r    <= mem_trap_target;
            mem_trap_pc_val_r    <= mem_trap_pc_val;
            mem_trap_cause_val_r <= mem_trap_cause_val;
        end
    end

    // Registered EX-redirect — breaks EX→flush_id_ex combinational path (timing fix)
    logic        ex_pc_redirect_r;
    logic [31:0] ex_pc_target_r;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            ex_pc_redirect_r <= 1'b0;
            ex_pc_target_r   <= '0;
        end else begin
            ex_pc_redirect_r <= ex_pc_redirect;
            ex_pc_target_r   <= ex_pc_target;
        end
    end

    // Ghost instruction kill: NOP-out EX→MEM path when registered MEM-trap fires
    ex_mem_reg_t ex_mem_reg_to_mem;
    assign ex_mem_reg_to_mem = mem_trap_redirect_r ? ex_mem_nop() : ex_mem_reg;

    // Merged PC redirect (MEM trap has priority over EX redirect)
    logic        pc_redirect_combined;
    logic [31:0] pc_target_combined;
    assign pc_redirect_combined = ex_pc_redirect_r | mem_trap_redirect_r;
    assign pc_target_combined   = mem_trap_redirect_r ? mem_trap_target_r : ex_pc_target_r;

    // =========================================================================
    // Register file signals
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
    logic        csr_rd_access;
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
    logic        trap_entry;             // From EX
    logic [31:0] trap_pc_val, trap_cause_val;  // From EX
    // Merged trap channel (MEM misalign takes priority over EX trap)
    logic        trap_entry_merged;
    logic [31:0] trap_pc_merged, trap_cause_merged;
    assign trap_entry_merged = (trap_entry && !flush_ex_mem) | mem_trap_entry_r;
    assign trap_pc_merged    = mem_trap_entry_r ? mem_trap_pc_val_r  : trap_pc_val;
    assign trap_cause_merged = mem_trap_entry_r ? mem_trap_cause_val_r : trap_cause_val;
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
    logic        dbg_halted_wb;
    logic        dbg_halted_if;
    logic        dbg_halt_combined;
    logic        dbg_ebreak_from_ex;

    assign dbg_halt_combined = dbg_halt_req || dbg_ebreak_from_ex;
    assign dbg_halted = dbg_halted_wb && !id_ex_reg.valid && !ex1a_ex1b_reg_q.valid && !ex1c_ex1b_reg_q.valid && !ex1b_ex2_reg_q.valid && !ex_mem_reg.valid;

    logic [31:0] pc_if_out;

    // =========================================================================
    // EX1a/EX1c/EX1b pipeline FFs (Run-26: EX1c re-inserted)
    // ex1a_ex1b_reg_q: registered output of EX1a (trap_type=TRAP_NONE placeholder;
    //                  pre_wstrb/pre_wdata_aligned default — EX1c overwrites both).
    // ex1c_comb:       combinational output of u_ex1c — trap_type + byte-align
    //                  re-encoded on the registered ex1a_ex1b_reg_q inputs.
    // ex1c_ex1b_reg_q: registered EX1c output → feeds u_ex1b.
    // ex1b_ex2_reg_q:  registered output of EX1b → input to EX2 FF (Run-23).
    // =========================================================================
    ex1a_ex1b_t ex1a_ex1b_comb;    // combinational output from u_ex (EX1a)
    ex1a_ex1b_t ex1a_ex1b_reg_q;   // registered EX1a output — input to u_ex1c
    ex1a_ex1b_t ex1c_comb;         // combinational output from u_ex1c (EX1c)
    ex1a_ex1b_t ex1c_ex1b_reg_q;   // registered EX1c output — fed into u_ex1b
    ex1_ex2_reg_t ex1b_comb;       // combinational output from u_ex1b (EX1b)
    ex1_ex2_reg_t ex1b_ex2_reg_q;  // registered EX1b output — fed into u_ex2 (Run-23)

    always_ff @(posedge clk) begin
        if (!rst_n || flush_ex1a_ex1b)
            ex1a_ex1b_reg_q <= ex1a_ex1b_nop();
        else if (!stall_ex1a_ex1b)
            ex1a_ex1b_reg_q <= ex1a_ex1b_comb;
    end

    // EX1c stage (Run-26): re-encodes trap_type + byte-align on registered inputs
    rv32i_pipeline_ex1c u_ex1c (
        .ex1a_i (ex1a_ex1b_reg_q),
        .ex1c_o (ex1c_comb)
    );

    // EX1c output register: ex1c_comb → ex1c_ex1b_reg_q
    always_ff @(posedge clk) begin
        if (!rst_n || flush_ex1c_ex1b)
            ex1c_ex1b_reg_q <= ex1a_ex1b_nop();
        else if (!stall_ex1c_ex1b)
            ex1c_ex1b_reg_q <= ex1c_comb;
    end

    // Run-23: EX1b→EX2 register — breaks the ex1c_ex1b_reg_q→EX1b→ex1_ex2 cone.
    //
    // FLUSH RULE: ex1b_ex2_reg_q holds the REDIRECTING instruction itself
    // (the branch/JALR/trap that caused ex_pc_redirect).  It must NOT be flushed
    // by flush_ex1_ex2 (which fires one cycle after ex_pc_redirect fires, i.e.
    // on ex_pc_redirect_r).  Doing so would kill the branch before it commits.
    //
    // Only flush on mem_trap_redirect_r (MEM-stage misalign trap), which takes
    // priority over every in-flight instruction including the redirector.
    // The stall signal is unchanged (mem_cache_stall global freeze still applies).
    always_ff @(posedge clk) begin
        if (!rst_n || mem_trap_redirect_r)
            ex1b_ex2_reg_q <= ex1_ex2_nop();
        else if (!stall_ex1_ex2)
            ex1b_ex2_reg_q <= ex1b_comb;
    end

    // =========================================================================
    // FENCE.I invalidate signal (from EX1b stage → I-cache)
    // =========================================================================
    logic fence_i_pulse;

    // =========================================================================
    // I-cache CPU-side interface
    // =========================================================================
    logic [31:0] ic_addr;
    logic        ic_valid;
    logic [31:0] ic_rdata;
    logic        ic_stall;

    // =========================================================================
    // D-cache CPU-side interface
    // =========================================================================
    logic [31:0] dc_addr;
    logic        dc_valid;
    logic        dc_we;
    logic [31:0] dc_wdata;
    logic [3:0]  dc_wstrb;
    logic [31:0] dc_rdata;
    logic        dc_stall;

    // =========================================================================
    // I-cache AXI side (to arbiter)
    // =========================================================================
    logic [31:0] ic_axi_araddr;
    logic        ic_axi_arvalid;
    logic        ic_axi_arready;
    logic [31:0] ic_axi_rdata;
    logic [1:0]  ic_axi_rresp;  // TODO(phase4): propagate RRESP[1] as instruction-fetch
                                  // access fault (trap cause 1) into the pipeline MEM stage.
                                  // Requires adding ic_error_o port to rv32i_icache and
                                  // wiring it through rv32i_pipeline_if → rv32i_pipeline_mem.
    logic        ic_axi_rvalid;
    logic        ic_axi_rready;

    // =========================================================================
    // D-cache AXI side (to arbiter)
    // =========================================================================
    logic [31:0] dc_axi_araddr;
    logic        dc_axi_arvalid;
    logic        dc_axi_arready;
    logic [31:0] dc_axi_rdata;
    logic [1:0]  dc_axi_rresp;  // TODO(phase4): propagate RRESP[1] as load-access fault
                                  // (trap cause 5) and BRESP[1] as store-access fault
                                  // (trap cause 7) into the pipeline MEM stage.
    logic        dc_axi_rvalid;
    logic        dc_axi_rready;

    logic [31:0] dc_axi_awaddr;
    logic        dc_axi_awvalid;
    logic        dc_axi_awready;
    logic [31:0] dc_axi_wdata;
    logic [3:0]  dc_axi_wstrb;
    logic        dc_axi_wvalid;
    logic        dc_axi_wready;
    logic        dc_axi_bvalid;
    logic [1:0]  dc_axi_bresp;  // See dc_axi_rresp note above.
    logic        dc_axi_bready;

    // =========================================================================
    // Hazard Unit
    // =========================================================================
    rv32i_hazard_unit u_hazard (
        .id_ex_rs1_addr    (id_ex_reg.rs1_addr),
        .id_ex_rs2_addr    (id_ex_reg.rs2_addr),
        .id_ex_rd_addr     (id_ex_reg.rd_addr),
        .id_ex_mem_rd      (id_ex_reg.mem_rd),
        .id_ex_reg_wr_en   (id_ex_reg.reg_wr_en),
        // ex1b_ ports = ex1a_ex1b_reg_q (1 cycle behind EX1a)
        .ex1b_rd_addr      (ex1a_ex1b_reg_q.rd_addr),
        .ex1b_reg_wr_en    (ex1a_ex1b_reg_q.reg_wr_en),
        .ex1b_mem_rd       (ex1a_ex1b_reg_q.mem_rd),
        // ex1c_ ports = ex1c_ex1b_reg_q (retiming FF, 2 cycles behind EX1a)
        .ex1c_rd_addr      (ex1c_ex1b_reg_q.rd_addr),
        .ex1c_reg_wr_en    (ex1c_ex1b_reg_q.reg_wr_en),
        .ex1c_mem_rd       (ex1c_ex1b_reg_q.mem_rd),
        // ex1b2_ ports = ex1b_ex2_reg_q (producer in EX2, 3 cycles behind EX1a; Run-23)
        .ex1b2_rd_addr     (ex1b_ex2_reg_q.rd_addr),
        .ex1b2_reg_wr_en   (ex1b_ex2_reg_q.reg_wr_en),
        .ex1b2_mem_rd      (ex1b_ex2_reg_q.mem_rd),
        .ex_mem_rd_addr    (ex_mem_reg.rd_addr),
        .ex_mem_reg_wr_en  (ex_mem_reg.reg_wr_en),
        .ex_mem_mem_rd     (ex_mem_reg.mem_rd),
        .mem_wb_rd_addr    (mem_wb_reg.rd_addr),
        .mem_wb_reg_wr_en  (mem_wb_reg.reg_wr_en),
        .if_id_rs1_addr    (if_id_reg.instruction[19:15]),
        .if_id_rs2_addr    (if_id_reg.instruction[24:20]),
        .if_cache_stall    (if_cache_stall),
        .mem_cache_stall   (mem_cache_stall),
        .ex_pc_redirect    (ex_pc_redirect_r),
        .mem_trap_redirect (mem_trap_redirect_r),
        .id_jal_taken      (jal_redirect),
        .stall_pc          (stall_pc),
        .stall_if_id       (stall_if_id),
        .stall_id_ex       (stall_id_ex),
        .stall_ex_mem      (stall_ex_mem),
        .stall_ex1_ex2_o   (stall_ex1_ex2),
        .stall_ex1a_ex1b_o (stall_ex1a_ex1b),
        .stall_ex1c_ex1b_o (stall_ex1c_ex1b),
        .flush_if_id       (flush_if_id),
        .flush_id_ex       (flush_id_ex),
        .flush_ex_mem      (flush_ex_mem),
        .flush_ex1_ex2_o   (flush_ex1_ex2),
        .flush_ex1a_ex1b_o (flush_ex1a_ex1b),
        .flush_ex1c_ex1b_o (flush_ex1c_ex1b),
        .fwd_a_sel         (fwd_a_sel),
        .fwd_b_sel         (fwd_b_sel),
        .fwd_store_sel     (fwd_store_sel),
        .fwd_a_ex1c        (fwd_a_ex1c),
        .fwd_b_ex1c        (fwd_b_ex1c),
        .fwd_store_ex1c    (fwd_store_ex1c),
        .fwd_a_ex1b2       (fwd_a_ex1b2),
        .fwd_b_ex1b2       (fwd_b_ex1b2),
        .fwd_store_ex1b2   (fwd_store_ex1b2),
        .fwd_a_sel_pre     (fwd_a_sel_pre_w),
        .fwd_a_ex1c_pre    (fwd_a_ex1c_pre_w),
        .fwd_a_ex1b2_pre   (fwd_a_ex1b2_pre_w),
        .fwd_b_sel_pre     (fwd_b_sel_pre_w),
        .fwd_b_ex1c_pre    (fwd_b_ex1c_pre_w),
        .fwd_b_ex1b2_pre   (fwd_b_ex1b2_pre_w)
    );

    // =========================================================================
    // Pipeline registers for pre-decoded forwarding selects (ID→EX1a boundary)
    //
    // No clock enable — must update every cycle including during stalls so that
    // load-use stall sequences see the correct registered selects on resume.
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            fwd_a_sel_r       <= 2'b00;
            fwd_a_ex1c_r      <= 1'b0;
            fwd_a_ex1b2_r     <= 1'b0;
            fwd_b_sel_r       <= 2'b00;
            fwd_b_ex1c_r      <= 1'b0;
            fwd_b_ex1b2_r     <= 1'b0;
            fwd_store_sel_r   <= 2'b00;
            fwd_store_ex1c_r  <= 1'b0;
            fwd_store_ex1b2_r <= 1'b0;
        end else begin
            fwd_a_sel_r       <= fwd_a_sel_pre_w;
            fwd_a_ex1c_r      <= fwd_a_ex1c_pre_w;
            fwd_a_ex1b2_r     <= fwd_a_ex1b2_pre_w;
            fwd_b_sel_r       <= fwd_b_sel_pre_w;
            fwd_b_ex1c_r      <= fwd_b_ex1c_pre_w;
            fwd_b_ex1b2_r     <= fwd_b_ex1b2_pre_w;
            fwd_store_sel_r   <= fwd_b_sel_pre_w;
            fwd_store_ex1c_r  <= fwd_b_ex1c_pre_w;
            fwd_store_ex1b2_r <= fwd_b_ex1b2_pre_w;
        end
    end

    // =========================================================================
    // Forwarding Unit
    // =========================================================================
    rv32i_forwarding_unit u_fwd (
        .fwd_a_sel          (fwd_a_sel_r),
        .fwd_b_sel          (fwd_b_sel_r),
        .fwd_store_sel      (fwd_store_sel_r),
        .fwd_a_ex1c         (fwd_a_ex1c_r),
        .fwd_b_ex1c         (fwd_b_ex1c_r),
        .fwd_store_ex1c     (fwd_store_ex1c_r),
        // Run-23: new EX1b2 forwarding tier (ex1b_ex2_reg_q, 3 cycles behind EX1a)
        .fwd_a_ex1b2        (fwd_a_ex1b2_r),
        .fwd_b_ex1b2        (fwd_b_ex1b2_r),
        .fwd_store_ex1b2    (fwd_store_ex1b2_r),
        .id_ex_rs1_data     (id_ex_reg.rs1_data),
        .id_ex_rs2_data     (id_ex_reg.rs2_data),
        // ex1b_ ports = ex1a_ex1b_reg_q (1 cycle behind EX1a)
        .ex1b_alu_result    (ex1a_ex1b_reg_q.alu_result),
        .ex1b_csr_rdata     (ex1a_ex1b_reg_q.csr_rdata),
        .ex1b_pc            (ex1a_ex1b_reg_q.pc),
        .ex1b_csr_access    (ex1a_ex1b_reg_q.csr_access),
        .ex1b_jump          (ex1a_ex1b_reg_q.jump),
        // ex1c_ ports = ex1c_ex1b_reg_q (retiming FF, 2 cycles behind EX1a)
        .ex1c_alu_result    (ex1c_ex1b_reg_q.alu_result),
        .ex1c_csr_rdata     (ex1c_ex1b_reg_q.csr_rdata),
        .ex1c_pc            (ex1c_ex1b_reg_q.pc),
        .ex1c_csr_access    (ex1c_ex1b_reg_q.csr_access),
        .ex1c_jump          (ex1c_ex1b_reg_q.jump),
        // ex1b2_ ports = ex1b_ex2_reg_q (producer completed EX1b, now in EX2; Run-23)
        .ex1b2_alu_result   (ex1b_ex2_reg_q.alu_result),
        .ex1b2_csr_rdata    (ex1b_ex2_reg_q.csr_rdata),
        .ex1b2_pc           (ex1b_ex2_reg_q.pc),
        .ex1b2_csr_access   (ex1b_ex2_reg_q.csr_access),
        .ex1b2_jump         (ex1b_ex2_reg_q.jump),
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
    assign csr_rd_access = id_ex_reg.csr_access && id_ex_reg.valid && !flush_ex_mem;

    rv32i_csr_file u_csr (
        .clk              (clk),
        .rst_n            (rst_n),
        .csr_access       (csr_rd_access),
        .csr_addr         (csr_addr_ex),
        .csr_op           (csr_op_ex),
        .csr_wdata        (csr_wdata_ex),
        .rs1_addr         (csr_rs1_addr_ex),
        .trap_entry       (trap_entry_merged),
        .trap_pc          (trap_pc_merged),
        .trap_cause       (trap_cause_merged),
        .mret             (mret_ex && !flush_ex_mem),
        .ext_irq_i        (ext_irq_pending),
        .timer_irq_i      (timer_irq_pending),
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
        .mstatus_mie       (mstatus_mie_eff),
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
    // Register File
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
    // IF Stage (Phase 3: cache interface)
    // =========================================================================
    rv32i_pipeline_if u_if (
        .clk              (clk),
        .rst_n            (rst_n),
        .stall_pc         (stall_pc),
        .stall_if_id      (stall_if_id),
        .flush_if_id      (flush_if_id),
        .pc_redirect      (pc_redirect_combined),
        .pc_target        (pc_target_combined),
        .jal_redirect     (jal_redirect),
        .jal_target       (jal_target),
        .dbg_halt_req     (dbg_halt_combined),
        .dbg_step_pending (dbg_step_req),
        .dbg_pc_wr_en     (dbg_pc_wr_en),
        .dbg_pc_wr_data   (dbg_pc_wr_data),
        .dbg_halted       (dbg_halted_if),
        // I-cache interface
        .ic_addr_o        (ic_addr),
        .ic_valid_o       (ic_valid),
        .ic_rdata_i       (ic_rdata),
        .ic_stall_i       (ic_stall),
        .if_cache_stall_o (if_cache_stall),
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
    // EX1a Stage: outputs ex1a_ex1b_t (with trap_type + byte-align encoded here).
    // Registered into ex1a_ex1b_reg_q, then retimed into ex1c_ex1b_reg_q → EX1b.
    // =========================================================================
    rv32i_pipeline_ex u_ex (
        .clk              (clk),
        .rst_n            (rst_n),
        .flush_ex_mem     (flush_ex_mem),
        .id_ex_reg_i      (id_ex_reg),
        .fwd_rs1          (fwd_rs1),
        .fwd_rs2          (fwd_rs2),
        .fwd_store        (fwd_store),
        .csr_rdata_i      (csr_rdata),
        .irq_valid_i      (irq_valid),
        .irq_cause_i      (irq_cause),
        .mtvec_i          (mtvec),
        .mret_pc_i        (mret_pc_val),
        .csr_wr_en_o      (csr_wr_en),
        .csr_wdata_o      (csr_wdata_ex),
        .csr_addr_o       (csr_addr_ex),
        .csr_op_o         (csr_op_ex),
        .rs1_addr_o       (csr_rs1_addr_ex),
        .ex1a_ex1b_o      (ex1a_ex1b_comb)
    );

    // =========================================================================
    // EX1b Stage (Run-17/20: now consumes ex1c_ex1b_reg_q, purely combinational)
    // Bypass mux: if flush_ex1c_ex1b is asserted this cycle, EX1b sees a NOP
    // so it cannot produce a spurious ex_pc_redirect from a ghost instruction
    // that is being squashed (the FF clears only at the NEXT rising edge).
    // =========================================================================
    ex1a_ex1b_t ex1b_input;
    always_comb begin
        ex1b_input = flush_ex1c_ex1b ? ex1a_ex1b_nop() : ex1c_ex1b_reg_q;
    end

    // Run-23: EX1b output now drives ex1b_comb (wire) which is registered into
    // ex1b_ex2_reg_q before reaching u_ex2.  ex_pc_redirect / trap signals are
    // still captured combinationally and registered separately (ex_pc_redirect_r,
    // mem_trap_redirect_r) — their timing is unaffected by this change.
    rv32i_pipeline_ex1b u_ex1b (
        .ex1a_i           (ex1b_input),
        .ex1_ex2_reg_o    (ex1b_comb),
        .ex_pc_redirect_o (ex_pc_redirect),
        .ex_pc_target_o   (ex_pc_target),
        .trap_entry_o     (trap_entry),
        .trap_pc_o        (trap_pc_val),
        .trap_cause_o     (trap_cause_val),
        .mret_o           (mret_ex),
        .dbg_halt_req_o   (dbg_ebreak_from_ex),
        .fence_i_o        (fence_i_pulse)
    );

    // =========================================================================
    // EX2 Stage — owns the EX1/EX2 → EX/MEM pipeline register
    // Run-23: input is now ex1b_ex2_reg_q (registered EX1b output) rather than
    // the raw EX1b combinational output, breaking the critical 800 ps cone.
    //
    // FLUSH RULE: u_ex2 must NOT flush on ex_pc_redirect_r (flush_ex1_ex2).
    // At the cycle flush_ex1_ex2 fires (ex_pc_redirect_r), ex1b_ex2_reg_q holds
    // the redirecting instruction (branch/JALR) that must reach MEM/WB to commit.
    // Flushing u_ex2 here would kill that instruction before it commits.
    //
    // Before Run-23, flush_ex1_ex2 on ex_pc_redirect_r was correct because the
    // redirecting instruction had already been captured into ex_mem_reg one cycle
    // earlier (no ex1b_ex2_reg_q buffer existed).  With the extra FF, it arrives
    // one cycle later — so u_ex2 must be transparent to the redirect flush.
    //
    // Only mem_trap_redirect_r requires flushing u_ex2 (a higher-priority trap
    // from MEM overrides everything including the instruction in ex1b_ex2_reg_q).
    // =========================================================================
    rv32i_pipeline_ex2 u_ex2 (
        .clk_i            (clk),
        .rst_n_i          (rst_n),
        .stall_ex1_ex2_i  (stall_ex1_ex2),
        .flush_ex1_ex2_i  (mem_trap_redirect_r),   // Run-23: use mem_trap only, not ex_pc_redirect
        .ex1_ex2_reg_i    (ex1b_ex2_reg_q),
        .ex_mem_reg_o     (ex_mem_reg)
    );

    // =========================================================================
    // MEM Stage (Phase 3: D-cache interface)
    // =========================================================================
    rv32i_pipeline_mem u_mem (
        .clk                 (clk),
        .rst_n               (rst_n),
        .ex_mem_reg_i        (ex_mem_reg_to_mem),
        .mtvec_i             (mtvec),
        // D-cache interface
        .dc_addr_o           (dc_addr),
        .dc_valid_o          (dc_valid),
        .dc_we_o             (dc_we),
        .dc_wdata_o          (dc_wdata),
        .dc_wstrb_o          (dc_wstrb),
        .dc_rdata_i          (dc_rdata),
        .dc_stall_i          (dc_stall),
        .mem_cache_stall_o   (mem_cache_stall),
        .mem_trap_redirect_o (mem_trap_redirect),
        .mem_trap_target_o   (mem_trap_target),
        .mem_trap_entry_o    (mem_trap_entry),
        .mem_trap_pc_o       (mem_trap_pc_val),
        .mem_trap_cause_o    (mem_trap_cause_val),
        .mem_wb_reg_o        (mem_wb_reg)
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
    // I-Cache (Phase 3)
    // =========================================================================
    rv32i_icache u_icache (
        .clk              (clk),
        .rst_n            (rst_n),
        .ic_addr_i        (ic_addr),
        .ic_valid_i       (ic_valid),
        .ic_rdata_o       (ic_rdata),
        .ic_stall_o       (ic_stall),
        .ic_invalidate_i  (fence_i_pulse),
        .axi_araddr_o     (ic_axi_araddr),
        .axi_arvalid_o    (ic_axi_arvalid),
        .axi_arready_i    (ic_axi_arready),
        .axi_rdata_i      (ic_axi_rdata),
        .axi_rresp_i      (ic_axi_rresp),
        .axi_rvalid_i     (ic_axi_rvalid),
        .axi_rready_o     (ic_axi_rready)
    );

    // =========================================================================
    // D-Cache (Phase 3)
    // =========================================================================
    rv32i_dcache u_dcache (
        .clk              (clk),
        .rst_n            (rst_n),
        .dc_addr_i        (dc_addr),
        .dc_valid_i       (dc_valid),
        .dc_we_i          (dc_we),
        .dc_wdata_i       (dc_wdata),
        .dc_wstrb_i       (dc_wstrb),
        .dc_rdata_o       (dc_rdata),
        .dc_stall_o       (dc_stall),
        .axi_araddr_o     (dc_axi_araddr),
        .axi_arvalid_o    (dc_axi_arvalid),
        .axi_arready_i    (dc_axi_arready),
        .axi_rdata_i      (dc_axi_rdata),
        .axi_rresp_i      (dc_axi_rresp),
        .axi_rvalid_i     (dc_axi_rvalid),
        .axi_rready_o     (dc_axi_rready),
        .axi_awaddr_o     (dc_axi_awaddr),
        .axi_awvalid_o    (dc_axi_awvalid),
        .axi_awready_i    (dc_axi_awready),
        .axi_wdata_o      (dc_axi_wdata),
        .axi_wstrb_o      (dc_axi_wstrb),
        .axi_wvalid_o     (dc_axi_wvalid),
        .axi_wready_i     (dc_axi_wready),
        .axi_bvalid_i     (dc_axi_bvalid),
        .axi_bresp_i      (dc_axi_bresp),
        .axi_bready_o     (dc_axi_bready)
    );

    // =========================================================================
    // Cache Arbiter (Phase 3): D$ priority over I$
    // =========================================================================
    rv32i_cache_arbiter u_cache_arb (
        .clk              (clk),
        .rst_n            (rst_n),
        // I-cache read
        .ic_araddr_i      (ic_axi_araddr),
        .ic_arvalid_i     (ic_axi_arvalid),
        .ic_arready_o     (ic_axi_arready),
        .ic_rdata_o       (ic_axi_rdata),
        .ic_rresp_o       (ic_axi_rresp),
        .ic_rvalid_o      (ic_axi_rvalid),
        .ic_rready_i      (ic_axi_rready),
        // D-cache read (refill)
        .dc_araddr_i      (dc_axi_araddr),
        .dc_arvalid_i     (dc_axi_arvalid),
        .dc_arready_o     (dc_axi_arready),
        .dc_rdata_o       (dc_axi_rdata),
        .dc_rresp_o       (dc_axi_rresp),
        .dc_rvalid_o      (dc_axi_rvalid),
        .dc_rready_i      (dc_axi_rready),
        // D-cache write (writeback)
        .dc_awaddr_i      (dc_axi_awaddr),
        .dc_awvalid_i     (dc_axi_awvalid),
        .dc_awready_o     (dc_axi_awready),
        .dc_wdata_i       (dc_axi_wdata),
        .dc_wstrb_i       (dc_axi_wstrb),
        .dc_wvalid_i      (dc_axi_wvalid),
        .dc_wready_o      (dc_axi_wready),
        .dc_bvalid_o      (dc_axi_bvalid),
        .dc_bresp_o       (dc_axi_bresp),
        .dc_bready_i      (dc_axi_bready),
        // AXI master (to external memory)
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
        .axi_bready_o     (axi_bready)
    );

    // =========================================================================
    // Phase 1 debug compatibility outputs
    // =========================================================================
    assign debug_rs1_data         = 32'h0;
    assign debug_rs2_data         = 32'h0;
    assign debug_branch_taken     = 1'b0;
    assign debug_take_branch_jump = pc_redirect_combined;
    assign debug_pc_src           = pc_redirect_combined;
    assign debug_state            = 4'h0;
    assign debug_ebreak           = dbg_ebreak_from_ex;

    // CSR debug output assignments
    assign dbg_csr_mtvec_o = mtvec;
    assign dbg_csr_mepc_o  = mret_pc_val;
    assign dbg_csr_mip_o   = mip;

    // IF-stage PC output
    assign pc_if_o = pc_if_out;

    // Unused signals suppression
    /* verilator lint_off UNUSEDSIGNAL */
    logic _unused_resume    = dbg_resume_req;
    logic _unused_csr_wr_en = csr_wr_en;
    logic _unused_csr_illegal = csr_illegal;  // CSR illegal now pre-computed in ID stage
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
