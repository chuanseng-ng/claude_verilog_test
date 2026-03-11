// rv32i_pipeline_if.sv
// RV32I Pipeline — Instruction Fetch (IF) Stage (Phase 3)
//
// Phase 3 changes vs Phase 2:
//   - AXI-IF read channels replaced by I-cache interface
//   - if_axi_stall_o replaced by if_cache_stall_o
//   - Simpler stall logic: ic_stall_i directly drives stall output
//
// Responsibilities:
//   - Maintain the Program Counter (PC) register
//   - Request instruction from I-cache each cycle (when not stalled/halted)
//   - Generate if_cache_stall_o to hazard unit on I-cache miss
//   - Maintain the IF/ID pipeline register
//   - Handle PC redirect (branch/jump/trap) and JAL early resolve

import rv32i_pipeline_pkg::*;

module rv32i_pipeline_if (
    input  logic        clk,
    input  logic        rst_n,

    // ── Hazard unit controls ──────────────────────────────────────────────────
    input  logic        stall_pc,      // Hold PC register
    input  logic        stall_if_id,   // Hold IF/ID register
    input  logic        flush_if_id,   // Clear IF/ID (insert NOP bubble)

    // ── PC redirect (from EX stage) ───────────────────────────────────────────
    input  logic        pc_redirect,   // Redirect PC to pc_target
    input  logic [31:0] pc_target,     // Redirect target address

    // ── JAL redirect (from ID stage) ──────────────────────────────────────────
    input  logic        jal_redirect,  // JAL resolved in ID → redirect PC
    input  logic [31:0] jal_target,    // JAL target (PC_id + offset)

    // ── Debug interface ───────────────────────────────────────────────────────
    input  logic        dbg_halt_req,       // Stop issuing new fetches
    input  logic        dbg_step_pending,   // Single-step in progress (allow exactly 1 fetch)
    input  logic        dbg_pc_wr_en,       // Write PC when halted
    input  logic [31:0] dbg_pc_wr_data,
    output logic        dbg_halted,         // Pipeline fully drained and halted

    // ── I-Cache interface (replaces AXI-IF channels) ──────────────────────────
    output logic [31:0] ic_addr_o,     // Fetch address (= current PC)
    output logic        ic_valid_o,    // Fetch request valid
    input  logic [31:0] ic_rdata_i,    // Instruction word (valid when !ic_stall_i)
    input  logic        ic_stall_i,    // I-cache miss — stall the pipeline

    // ── Cache stall output to hazard unit ─────────────────────────────────────
    output logic        if_cache_stall_o,

    // ── IF/ID pipeline register output ────────────────────────────────────────
    output if_id_reg_t  if_id_reg_o,

    // ── PC observable (for debug DBG_PC register) ─────────────────────────────
    output logic [31:0] pc_out
);

    // =========================================================================
    // PC Register
    // =========================================================================
    logic [31:0] pc_q, pc_next;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pc_q <= 32'h0000_0000;
        end else if (dbg_pc_wr_en && dbg_halted) begin
            // Debug PC write (only when halted)
            pc_q <= dbg_pc_wr_data;
        end else if (pc_redirect) begin
            // Branch/jump/trap redirect — not gated by stall_pc
            pc_q <= pc_target;
        end else if (jal_redirect) begin
            // JAL early resolve in ID — not gated by stall_pc
            pc_q <= jal_target;
        end else if (!stall_pc && ic_valid_o && !ic_stall_i) begin
            // Cache hit: instruction received this cycle → advance PC
            pc_q <= pc_next;
        end
        // else: stall_pc or cache miss — hold PC
    end

    assign pc_next = pc_q + 32'd4;
    assign pc_out  = pc_q;

    // =========================================================================
    // Fetch enable and step tracker
    // =========================================================================
    // Single-step: only one fetch allowed per step event.
    // step_done_q is set after the first accepted fetch during a step,
    // cleared when step_pending deasserts (step instruction committed).
    logic step_done_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            step_done_q <= 1'b0;
        end else begin
            if (!dbg_step_pending) begin
                step_done_q <= 1'b0; // Clear when not stepping
            end else if (ic_valid_o && !ic_stall_i) begin
                step_done_q <= 1'b1; // Instruction received → step fetch done
            end
        end
    end

    // Fetch valid: request instruction from I-cache when not halted, not redirecting,
    // and not in a completed single-step.
    assign ic_valid_o = !dbg_halt_req
                      && !pc_redirect
                      && !jal_redirect
                      && !(dbg_step_pending && step_done_q);

    // Present current PC to I-cache
    assign ic_addr_o = pc_q;

    // Cache stall to hazard unit: pipeline must stall when I-cache signals a miss
    assign if_cache_stall_o = ic_valid_o && ic_stall_i;

    // =========================================================================
    // IF/ID Pipeline Register
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            if_id_reg_o <= if_id_nop();
        end else if (flush_if_id || pc_redirect || jal_redirect) begin
            // Control hazard: flush and insert NOP
            if_id_reg_o <= if_id_nop();
        end else if (dbg_halt_req) begin
            // Halt requested: drain pipeline
            if_id_reg_o <= if_id_nop();
        end else if (!stall_if_id && ic_valid_o && !ic_stall_i) begin
            // Cache hit: load instruction into IF/ID
            if_id_reg_o.pc          <= pc_q;      // PC of this instruction
            if_id_reg_o.instruction <= ic_rdata_i;
            if_id_reg_o.valid       <= 1'b1;
        end else if (stall_if_id) begin
            // Hold current IF/ID (downstream stall)
        end else begin
            // No valid instruction this cycle (e.g. cache miss, halt, redirect)
            if_id_reg_o <= if_id_nop();
        end
    end

    // =========================================================================
    // Debug halt detection
    // Halted when: halt requested AND no cache miss in progress AND IF/ID empty
    // =========================================================================
    assign dbg_halted = dbg_halt_req && !ic_stall_i && !if_id_reg_o.valid;

endmodule
