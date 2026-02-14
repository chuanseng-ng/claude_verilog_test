// rv32i_pipeline_wb.sv
// RV32I Pipeline — Write Back (WB) Stage (Phase 2)
//
// Responsibilities:
//   - Compute write-back data mux (load / CSR / jump / ALU)
//   - Drive register file write port (regfile is at core level)
//   - Assert commit_valid / trap_taken observability signals
//   - Signal dbg_halted when pipeline is drained after halt request

import rv32i_pipeline_pkg::*;

module rv32i_pipeline_wb (
    input  logic        clk,
    input  logic        rst_n,

    // ── MEM/WB pipeline register input ───────────────────────────────────────
    input  mem_wb_reg_t mem_wb_reg_i,

    // ── Debug interface ───────────────────────────────────────────────────────
    input  logic        dbg_halt_req,      // Halt has been requested
    input  logic        if_stage_idle,     // IF stage has stopped fetching (fetch_pending=0)

    // ── Register file write port (wired to core-level regfile) ───────────────
    output logic        rf_wr_en_o,
    output logic [4:0]  rf_wr_addr_o,
    output logic [31:0] rf_wr_data_o,

    // ── dbg_halted output (pipeline fully drained) ────────────────────────────
    output logic        dbg_halted,

    // ── Commit interface (observability) ─────────────────────────────────────
    output logic        commit_valid_o,
    output logic [31:0] commit_pc_o,
    output logic [31:0] commit_insn_o,
    output logic        trap_taken_o,
    output logic [3:0]  trap_cause_o
);

    // =========================================================================
    // Write-back data mux
    // =========================================================================
    logic [31:0] rd_data;

    always_comb begin
        if (mem_wb_reg_i.mem_rd) begin
            rd_data = mem_wb_reg_i.mem_rdata;         // Load result
        end else if (mem_wb_reg_i.csr_access) begin
            rd_data = mem_wb_reg_i.csr_rdata;         // CSR read result
        end else if (mem_wb_reg_i.jump) begin
            rd_data = mem_wb_reg_i.pc + 32'd4;        // JAL/JALR return address
        end else begin
            rd_data = mem_wb_reg_i.alu_result;        // ALU result
        end
    end

    // =========================================================================
    // Register file write port
    // Write is suppressed for traps and bubbles.
    // =========================================================================
    assign rf_wr_en_o   = mem_wb_reg_i.valid
                       && mem_wb_reg_i.reg_wr_en
                       && !mem_wb_reg_i.trap_valid;
    assign rf_wr_addr_o = mem_wb_reg_i.rd_addr;
    assign rf_wr_data_o = rd_data;

    // =========================================================================
    // Commit interface
    // commit_valid: normal instruction retirement (not a trap, not a bubble)
    // trap_taken:   set when a trap (exception or interrupt) retires here
    // =========================================================================
    assign commit_valid_o = mem_wb_reg_i.valid && !mem_wb_reg_i.trap_valid;
    assign commit_pc_o    = mem_wb_reg_i.pc;
    assign commit_insn_o  = mem_wb_reg_i.instruction;
    assign trap_taken_o   = mem_wb_reg_i.valid && mem_wb_reg_i.trap_valid;
    assign trap_cause_o   = mem_wb_reg_i.trap_cause[3:0];

    // =========================================================================
    // Debug halt
    // The pipeline is halted when:
    //   1. A halt has been requested (dbg_halt_req)
    //   2. IF has stopped issuing new fetches (if_stage_idle)
    //   3. The WB stage has nothing valid (pipeline fully drained)
    // =========================================================================
    assign dbg_halted = dbg_halt_req && if_stage_idle && !mem_wb_reg_i.valid;

endmodule
