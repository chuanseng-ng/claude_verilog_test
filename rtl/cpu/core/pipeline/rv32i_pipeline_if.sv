// rv32i_pipeline_if.sv
// RV32I Pipeline — Instruction Fetch (IF) Stage (Phase 2)
//
// Responsibilities:
//   - Maintain the Program Counter (PC) register
//   - Issue AXI-IF read requests to the arbiter
//   - Track in-flight fetch; discard response on pending_flush
//   - Maintain the IF/ID pipeline register
//   - Generate if_axi_stall to hazard unit

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
    input  logic        dbg_halt_req,  // Stop issuing new fetches
    input  logic        dbg_pc_wr_en,  // Write PC when halted
    input  logic [31:0] dbg_pc_wr_data,
    output logic        dbg_halted,    // Pipeline fully drained and halted

    // ── AXI-IF read channel (to arbiter) ──────────────────────────────────────
    output logic [31:0] if_araddr_o,
    output logic        if_arvalid_o,
    input  logic        if_arready_i,

    input  logic [31:0] if_rdata_i,
    input  logic [1:0]  if_rresp_i,
    input  logic        if_rvalid_i,
    output logic        if_rready_o,

    // ── AXI stall output to hazard unit ───────────────────────────────────────
    output logic        if_axi_stall_o,

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
            pc_q <= dbg_pc_wr_data;
        end else if (pc_redirect) begin
            pc_q <= pc_target;
        end else if (jal_redirect) begin
            pc_q <= jal_target;
        end else if (!stall_pc) begin
            pc_q <= pc_next;
        end
    end

    // pc_next: advance by 4 unless an AXI fetch is pending
    // (When a fetch is in flight the IF stage doesn't issue a new one, so
    // the next sequential PC is always current PC + 4.)
    assign pc_next = pc_q + 32'd4;
    assign pc_out  = pc_q;

    // =========================================================================
    // Fetch state: track in-flight request and pending_flush
    // =========================================================================
    logic fetch_pending_q;    // AR handshake done, waiting for rvalid
    logic pending_flush_q;    // A redirect happened while fetch was in flight

    // if_axi_stall: 1 while we're waiting for a response, 0 when it arrives
    // Deasserted in the SAME cycle rvalid arrives so the hazard unit
    // releases stall_if_id and IF/ID can be loaded.
    assign if_axi_stall_o = fetch_pending_q && !(if_rvalid_i && if_rready_o);

    // rready: we always accept the response when it comes
    assign if_rready_o = 1'b1;

    // AR valid: issue a new fetch when not stalled, not halted, not already pending
    assign if_arvalid_o = !stall_pc && !dbg_halt_req && !fetch_pending_q;
    assign if_araddr_o  = pc_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fetch_pending_q <= 1'b0;
            pending_flush_q <= 1'b0;
        end else begin
            // AR accepted by arbiter → transaction in flight
            if (if_arvalid_o && if_arready_i) begin
                fetch_pending_q <= 1'b1;
            end

            // Response received → transaction complete
            if (if_rvalid_i && if_rready_o) begin
                fetch_pending_q <= 1'b0;
            end

            // If a redirect happens while a fetch is in flight, mark pending_flush
            if ((pc_redirect || jal_redirect) && fetch_pending_q && !(if_rvalid_i && if_rready_o)) begin
                pending_flush_q <= 1'b1;
            end else if (if_rvalid_i && if_rready_o) begin
                // Response received: clear flag regardless
                pending_flush_q <= 1'b0;
            end
        end
    end

    // =========================================================================
    // IF/ID Pipeline Register
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            if_id_reg_o <= if_id_nop();
        end else if (flush_if_id || pc_redirect || jal_redirect) begin
            if_id_reg_o <= if_id_nop();
        end else if (if_rvalid_i && if_rready_o && !stall_if_id) begin
            // Instruction arrived from AXI — but discard it if a redirect was pending
            if (pending_flush_q) begin
                if_id_reg_o <= if_id_nop();
            end else begin
                if_id_reg_o.pc          <= pc_q - 32'd4; // PC of the fetched instruction
                if_id_reg_o.instruction <= if_rdata_i;
                if_id_reg_o.valid       <= 1'b1;
            end
        end else if (stall_if_id) begin
            // Hold current value (do nothing)
        end
        // else: no new instruction this cycle, hold value
    end

    // =========================================================================
    // Debug halt
    // The pipeline is "halted" when the halt is requested and there is no
    // in-flight fetch (the fetch stage is idle).
    // The full pipeline-drain check is done in the WB stage; this flag
    // signals that IF has stopped issuing requests.
    // =========================================================================
    assign dbg_halted = dbg_halt_req && !fetch_pending_q;

endmodule
