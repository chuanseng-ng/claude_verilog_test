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
    input  logic        dbg_halt_req,       // Stop issuing new fetches
    input  logic        dbg_step_pending,   // Single-step in progress (allow exactly 1 fetch)
    input  logic        dbg_pc_wr_en,       // Write PC when halted
    input  logic [31:0] dbg_pc_wr_data,
    output logic        dbg_halted,         // Pipeline fully drained and halted

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
        end else if (if_arvalid_o && if_arready_i) begin
            // PC advances only when the current fetch is accepted by the arbiter.
            // This prevents pc_q from incrementing before the handler can read the
            // current address — which would cause Verilator/cocotb co-sim to fetch
            // the wrong address on the very first cycle after reset.
            pc_q <= pc_next;
        end
    end

    // pc_next: advance by 4 unless an AXI fetch is pending
    // (When a fetch is in flight the IF stage doesn't issue a new one, so
    // the next sequential PC is always current PC + 4.)
    assign pc_next = pc_q + 32'd4;
    assign pc_out  = pc_q;

    // =========================================================================
    // Fetch state: track in-flight request, pending_flush, and step fetch
    // =========================================================================
    logic fetch_pending_q;    // AR handshake done, waiting for rvalid
    logic pending_flush_q;    // A redirect happened while fetch was in flight
    logic step_done_q;        // One fetch accepted during single-step; block more

    // if_axi_stall: 1 while we're waiting for a response, 0 when it arrives
    // Deasserted in the SAME cycle rvalid arrives so the hazard unit
    // releases stall_if_id and IF/ID can be loaded.
    assign if_axi_stall_o = fetch_pending_q && !(if_rvalid_i && if_rready_o);

    // rready: we always accept the response when it comes
    assign if_rready_o = 1'b1;

    // AR valid: issue a new fetch when not stalled, not halted, not already pending,
    // and NOT in the same cycle a PC redirect fires.  Suppressing arvalid during a
    // redirect prevents the IF stage from presenting the stale (pre-redirect) address
    // to the arbiter.  The pending_flush_q mechanism handles any fetch that was already
    // in-flight before the redirect arrived.
    //
    // Single-step: when dbg_step_pending=1, only ONE fetch is allowed.  After
    // the first AR handshake completes, step_done_q is set, blocking further
    // fetches until step_pending deasserts (after the step instruction commits
    // and halt_req is re-asserted from cpu_top).
    assign if_arvalid_o = !stall_pc && !dbg_halt_req && !fetch_pending_q
                          && !pc_redirect && !jal_redirect
                          && !(dbg_step_pending && step_done_q);
    assign if_araddr_o  = pc_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fetch_pending_q <= 1'b0;
            pending_flush_q <= 1'b0;
            step_done_q     <= 1'b0;
        end else begin
            // Single-step fetch tracker: set when the first AR handshake fires
            // during a step; cleared when the step completes (pending deasserts).
            if (!dbg_step_pending) begin
                step_done_q <= 1'b0;
            end else if (if_arvalid_o && if_arready_i) begin
                step_done_q <= 1'b1;
            end

            // AR accepted by arbiter → transaction in flight
            if (if_arvalid_o && if_arready_i) begin
                fetch_pending_q <= 1'b1;
            end

            // Response received → transaction complete
            if (if_rvalid_i && if_rready_o) begin
                fetch_pending_q <= 1'b0;
            end

            // If a redirect happens while a fetch is in flight OR is being accepted this
            // very cycle, the response will carry the wrong (pre-redirect) address and
            // must be discarded when it arrives. Mark pending_flush in both cases.
            // Without the `if_arvalid_o && if_arready_i` term, a redirect that fires
            // in the SAME cycle that a new AR handshake completes (fetch_pending_q was 0)
            // would not set pending_flush, and the stale instruction would be loaded
            // into IF/ID the following cycle (e.g. taken-branch + simultaneous fetch).
            if ((pc_redirect || jal_redirect)
                    && (fetch_pending_q || (if_arvalid_o && if_arready_i))
                    && !(if_rvalid_i && if_rready_o)) begin
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
        end else if (dbg_halt_req) begin
            // Halt requested: unconditionally flush IF/ID to drain the pipeline.
            // The !stall_if_id guard was too conservative: when an AXI fetch is in
            // flight (stall_if_id=1), the old instruction would stay in IF/ID forever,
            // preventing the pipeline from ever reaching the fully-drained halt state.
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
        end else begin
            // Not stalling and no new instruction arriving this cycle.
            // Clear to bubble so the ID stage does not re-process the same
            // instruction — if_axi_stall only stalls stall_pc/stall_if_id,
            // leaving stall_id_ex=0, so IF/ID must present a NOP while the
            // next fetch is in flight.
            if_id_reg_o <= if_id_nop();
        end
    end

    // =========================================================================
    // Debug halt
    // The pipeline is "halted" when halt is requested, no AXI fetch is in
    // flight, AND IF/ID is empty (valid=0).
    //
    // Without the !if_id_reg_o.valid guard, dbg_halted can spuriously assert
    // for one cycle immediately after halt_req fires: IF/ID still holds the
    // last fetched instruction (e.g. JAL x0,0), downstream stages are all NOP,
    // and fetch_pending_q just cleared — so all existing conditions are met.
    // One cycle later the JAL propagates from IF/ID into ID/EX (valid=1),
    // dropping dbg_halted to 0.  This 1→0 transition triggers the auto-clear
    // in cpu_top, wiping dbg_ctrl_reg[0] and permanently losing the halt
    // request.  Adding !if_id_reg_o.valid prevents the spurious assertion and
    // lets dbg_halted rise only once all stages (including IF/ID) are drained.
    // =========================================================================
    assign dbg_halted = dbg_halt_req && !fetch_pending_q && !if_id_reg_o.valid;

endmodule
