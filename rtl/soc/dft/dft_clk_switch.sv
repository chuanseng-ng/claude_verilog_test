// dft_clk_switch.sv
// DFT Stage 1b (bead claude_verilog_test-j41m.3, GH #244).
//
// Glitch-free ENABLE-BEFORE-SWITCH clock selector between the TAP's scan clock
// (A, a gated TCK) and the tester's pin test clock (B, scan_clk_i). It resolves
// open question Q-CLK of docs/design/DFT_ARCHITECTURE.md section 15.5: the plain
// 2:1 mux `serial ? tck_scan_gated : scan_clk_i` is replaced by this module.
//
//   clk_o = (clk_a_i & en_a_q) | (clk_b_i & en_b_q)
//
// en_a_q and en_b_q are enable LATCHES, each transparent while ITS OWN raw clock
// is low (A's phase reference is the raw tck_i, not the gated clk_a_i, which
// idles low whether or not TCK runs) and holding while it is high. An enable
// therefore changes only while the clock it gates is low, so the AND term is 0
// before, during and after every enable change: no runt pulse and no extra edge
// on either source, whatever the phase relation between A and B.
//
// This differs from the usual flop-only enable-before-switch mux ON PURPOSE. A
// flop retires the old selection only on an edge of the deselected clock, so a
// stopped deselected clock deadlocks the switch (the reason section 15.5 first
// rejected the idea: scan_clk_i is normally STOPPED by the tester). A latch is
// open for the whole low phase, so a source that idles low can be switched OFF
// with no clock edge at all. The price is that the latch needs the clock to be
// low, which is the contract below.
//
// Handshake (cross-coupled enables, both enables never high together):
//
//   en_a_d = ~rst_active &  sel_a_i & b_off_in_a     (b_off_in_a = ~en_b_q seen by tck_i)
//   en_b_d =  rst_active | (~sel_a_i & ~a_on_in_b)   (a_on_in_b  =  en_a_q seen by clk_b_i)
//
// A source is enabled only after the other source's latch has been seen OFF
// through a 2-FF synchroniser in the enabling source's own clock domain. A
// source is disabled directly (no synchroniser) by its own select term, which is
// what lets the deselected source drop with no edge on it.
//
// Polarity of the B->A crossing. The B-to-A synchroniser carries ~en_b_q ("B is
// off"), not en_b_q. cdc_sync resets to 0, and 0 must mean the TRUE reset
// state: B is ON at reset, so "B off" resets to 0. Carrying en_b_q would reset to
// "B off" while B is on and let A enable over a running B if sel_a_i were already
// high at reset release. The A->B crossing carries en_a_q (A is OFF at reset, so
// 0 is exact). Both synchronisers are cleared by rst_n_i asynchronously, so the
// post-reset state is defined: en_a_q = 0, en_b_q = 1, b_off_in_a = a_on_in_b = 0.
//
// Reset. rst_n_i is a LEVEL: while low, en_a_d = 0 and en_b_d = 1, i.e. the pin
// clock B is selected and the TAP clock A is off. No reset edge is needed (a run
// that starts with rst_n_i = 0 comes up with en_b_q = 1 once clk_b_i is low). The
// Stage 1a pins-only operation (TAP held in reset, TCK stopped, scan_clk_i
// toggling) therefore passes scan_clk_i through unchanged: clk_o = clk_b_i. The
// first clk_b_i pulse after power-up is passed only if clk_b_i was low once
// before it (the latch must have opened); a clk_b_i that powers up HIGH loses
// nothing but that first partial pulse.
//
// Contract and consequences (all four matter to the tester, none is a hazard to
// the SoC):
//
//   1. serial -> parallel (sel_a_i falls, select B). en_a_q drops at once (TCK is
//      low in Update). en_b_q rises when the A->B synchroniser reports A off AND
//      clk_b_i is in a low phase. That synchroniser only advances on clk_b_i
//      edges, so: if clk_b_i was TOGGLING while A was selected, it has seen A on
//      and needs TWO clk_b_i rising edges (then the next low phase) to see A off:
//      the first pulse reaches clk_o about 3 clk_b_i cycles after sel_a_i falls,
//      and until then clk_o stays LOW (safe, no extra edge). If clk_b_i was
//      STOPPED (idle low) while A was selected, the synchroniser still holds its
//      pre-A "A off" value and B is enabled at the very next low phase, so the
//      first clk_b_i pulse after the switch passes at once. Both are glitch-free:
//      the new enable is raised only in a low phase of its own clock, and A is
//      low (sel_a_i falls on a TCK falling edge, the gate is closed in Update).
//      If clk_b_i never runs the enable may never rise and clk_o stays low.
//   2. parallel -> serial (sel_a_i rises, select A). en_b_d falls the instant
//      sel_a_i rises, and en_b_q follows during any low phase of clk_b_i: NO edge
//      on clk_b_i is needed provided clk_b_i idles LOW (the usual tester state).
//      If clk_b_i is stopped HIGH, its latch stays opaque, en_b_q stays 1 and the
//      switch cannot complete. en_a_q rises after the B->A synchroniser has seen
//      B off, which takes TWO tck_i rising edges after sel_a_i rises, then the
//      next low phase of tck_i. The TAP provides exactly that: sel_a_i is the
//      falling-edge `serial_o` flop, set after the rising edge that entered an
//      Update state; Update -> Select-DR -> Capture-DR gives the two TCK rising
//      edges, en_a_q rises in the low phase of the Capture-DR cycle and the third
//      rising edge, the one that ends Capture-DR and is the capture edge, passes.
//      That is zero spare edges; do not shorten the Update -> Capture-DR path.
//   3. Dwell. sel_a_i must not reverse faster than one full handshake (two clk
//      cycles of the clock being enabled plus two of the clock being retired).
//      The TAP cannot reverse it faster than an IR or SCAN_SEL scan (>= 10 TCK).
//   4. An asynchronous TRST_n (rst_n_i falling) in the middle of an A pulse can
//      raise en_b_q while the A pulse is still high; clk_o is then the OR of two
//      high levels, so pulses can MERGE but never get shorter, and no extra edge
//      is produced. The scan state is destroyed by the reset anyway.
//
// Assumptions: clk_b_i idles LOW; clk_a_i idles LOW (a gated TCK always does) and
// is derived from tck_i, which is RUNNING whenever sel_a_i changes (the TAP's
// select is a TCK flop, so this holds by construction); sel_a_i changes while
// clk_a_i is low (true for the TAP: falling TCK edge, gate closed in Update). If
// a generic user changes sel_a_i while clk_a_i is high the A pulse completes
// (latch opaque), and a B pulse may MERGE with it, never shorten it.
//
// Combinational-clock note: the output OR/AND is a clock-path structure.
// Synthesis and CTS see two clock roots into one cell and STA sees the enable
// latches as clock-gating checks (not run in this stage, see DFT_ARCHITECTURE.md
// section 15). The two 2-FF synchronisers carry the magic_cdc attribute through
// cdc_sync. The latches are written with always_latch.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module dft_clk_switch (
    input  logic tck_i,     // raw TCK: A-domain handshake clock and A's latch phase
    input  logic clk_a_i,   // A: gated TCK, idles low
    input  logic clk_b_i,   // B: scan_clk_i pin clock, assumed to idle low
    input  logic sel_a_i,   // 1 = select A (TAP serial), 0 = select B (pins)
    input  logic rst_n_i,   // active-low level, async assert (TCK-synchronous release)
    output logic clk_o
);

    // ── Handshake state ──────────────────────────────────────────────────────
    logic rst_active;
    logic en_a_d;
    logic en_b_d;
    logic en_a_q;           // enable latch of A, transparent while tck_i is low
    logic en_b_q;           // enable latch of B, transparent while clk_b_i is low
    logic b_off_in_a;       // ~en_b_q resynchronised into tck_i
    logic a_on_in_b;        // en_a_q resynchronised into clk_b_i

    assign rst_active = ~rst_n_i;

    assign en_a_d = ~rst_active & sel_a_i & b_off_in_a;
    assign en_b_d =  rst_active | (~sel_a_i & ~a_on_in_b);

    // ── Enable latches ───────────────────────────────────────────────────────
    // Transparent while the OWN raw clock is low, hold while it is high.
    always_latch begin
        if (!tck_i) begin
            en_a_q = en_a_d;
        end
    end

    always_latch begin
        if (!clk_b_i) begin
            en_b_q = en_b_d;
        end
    end

    // ── Cross-domain handshake synchronisers ─────────────────────────────────
    cdc_sync #(
        .WIDTH (1)
    ) u_sync_a (
        .clk_i   (tck_i),
        .rst_n_i (rst_n_i),
        .d_i     (~en_b_q),
        .q_o     (b_off_in_a)
    );

    cdc_sync #(
        .WIDTH (1)
    ) u_sync_b (
        .clk_i   (clk_b_i),
        .rst_n_i (rst_n_i),
        .d_i     (en_a_q),
        .q_o     (a_on_in_b)
    );

    // ── Output ───────────────────────────────────────────────────────────────
    assign clk_o = (clk_a_i & en_a_q) | (clk_b_i & en_b_q);

endmodule : dft_clk_switch
