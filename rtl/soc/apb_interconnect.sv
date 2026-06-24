// apb_interconnect.sv
// Phase 5 (APB migration PR-7) — 1-APB-master-in → N-APB-slaves-out decoder/fanout.
//
// Address decode: psel_o[i] is asserted when the incoming paddr_i falls within
// [SLV_BASE[i], SLV_LIMIT[i]] (inclusive) and psel_i is asserted.  Address
// ranges must be non-overlapping (behaviour is undefined otherwise).
//
// Response mux: prdata_o / pready_o / pslverr_o are muxed from the selected
// slave.  When psel_i=1 but no slave is addressed, the module returns
// pslverr_o=1, pready_o=1, prdata_o='0 (DECERR equivalent on APB).
//
// All logic is combinational — APB timing handshake (SETUP/ACCESS/pready) is
// the responsibility of each downstream slave.

`default_nettype none

module apb_interconnect #(
    parameter int unsigned N_SLAVES = 1,
    parameter int unsigned ADDR_W   = 32,
    parameter int unsigned DW       = 32,
    parameter int unsigned SW       = 4,
    parameter logic [ADDR_W-1:0] SLV_BASE  [N_SLAVES] = '{default: '0},
    parameter logic [ADDR_W-1:0] SLV_LIMIT [N_SLAVES] = '{default: '0}
) (
    // ── APB master input (from axil_to_apb bridge) ───────────────────────────
    input  logic              psel_i,
    input  logic              penable_i,
    input  logic              pwrite_i,
    input  logic [ADDR_W-1:0] paddr_i,
    input  logic [DW-1:0]     pwdata_i,
    input  logic [SW-1:0]     pstrb_i,

    // ── APB master response output (back to bridge) ──────────────────────────
    output logic [DW-1:0]     prdata_o,
    output logic              pready_o,
    output logic              pslverr_o,

    // ── APB slave output ports (to each downstream peripheral) ───────────────
    output logic              psel_o    [N_SLAVES],
    output logic              penable_o [N_SLAVES],
    output logic              pwrite_o  [N_SLAVES],
    output logic [ADDR_W-1:0] paddr_o   [N_SLAVES],
    output logic [DW-1:0]     pwdata_o  [N_SLAVES],
    output logic [SW-1:0]     pstrb_o   [N_SLAVES],

    // ── APB slave response input ports (from each downstream peripheral) ──────
    input  logic [DW-1:0]     prdata_i  [N_SLAVES],
    input  logic              pready_i  [N_SLAVES],
    input  logic              pslverr_i [N_SLAVES]
);

    // ── Address decode ───────────────────────────────────────────────────────
    // sel_idx: index of the selected slave, or N_SLAVES when no match.
    // First-match (lowest index wins) — iterate up and stop on first hit.
    logic [$clog2(N_SLAVES+1)-1:0] sel_idx;
    logic                          sel_valid;  // 1 when a slave matched

    always_comb begin
        sel_idx   = N_SLAVES[$clog2(N_SLAVES+1)-1:0];
        sel_valid = 1'b0;
        for (int unsigned i = 0; i < N_SLAVES; i++) begin
            if (!sel_valid &&
                paddr_i >= SLV_BASE[i] && paddr_i <= SLV_LIMIT[i]) begin
                sel_idx   = i[$clog2(N_SLAVES+1)-1:0];
                sel_valid = 1'b1;
            end
        end
    end

    // ── Per-slave output drive ───────────────────────────────────────────────
    // Broadcast addr/data/ctrl to all slaves; assert psel only for the winner.
    always_comb begin
        for (int unsigned i = 0; i < N_SLAVES; i++) begin
            psel_o   [i] = psel_i && sel_valid &&
                           (i[$clog2(N_SLAVES+1)-1:0] == sel_idx);
            penable_o[i] = penable_i;
            pwrite_o [i] = pwrite_i;
            paddr_o  [i] = paddr_i;
            pwdata_o [i] = pwdata_i;
            pstrb_o  [i] = pstrb_i;
        end
    end

    // ── Response mux ─────────────────────────────────────────────────────────
    always_comb begin
        if (!psel_i) begin
            // No transaction in progress — idle defaults.
            prdata_o  = '0;
            pready_o  = 1'b1;
            pslverr_o = 1'b0;
        end else if (!sel_valid) begin
            // psel_i=1 but address unmapped → DECERR equivalent.
            prdata_o  = '0;
            pready_o  = 1'b1;
            pslverr_o = 1'b1;
        end else begin
            // Mux from the selected slave.
            prdata_o  = prdata_i [sel_idx];
            pready_o  = pready_i [sel_idx];
            pslverr_o = pslverr_i[sel_idx];
        end
    end

endmodule : apb_interconnect

`default_nettype wire
