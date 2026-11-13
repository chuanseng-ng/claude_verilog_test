// dft_clk_switch - glitch-free enable-before-switch clock selector for the TAP clock and the pin test clock.
//
// Function: clk_o = (clk_a_i & en_a_q & tck_i) | (clk_b_i & en_b_q).
//   A is the gated TCK of the TAP. B is the pin test clock. Each enable is a latch that is open while its own raw clock is low.
//   A source is enabled only after the other latch is seen off through a 2-FF synchroniser in the enabling clock domain.
//   A source is disabled directly by its own select term.
// Clocks and resets: rst_n_i is a level. While it is low, B is selected and A is off.
//   After reset en_a_q is 0. en_b_q becomes 1 once clk_b_i is low. In the pins-only mode clk_o is clk_b_i.
// Caller rules:
//   - clk_b_i must idle low. clk_a_i must idle low and derive from tck_i.
//   - tck_i must run whenever sel_a_i changes. sel_a_i must change while clk_a_i is low.
//   - Serial to parallel: the first clk_b_i pulse comes at once if clk_b_i was stopped.
//     If clk_b_i toggled, it comes about 3 clk_b_i cycles later.
//   - Parallel to serial: no clk_b_i edge is needed if clk_b_i idles low. If clk_b_i stops high, the switch cannot complete.
//   - Do not shorten the TAP path Update, Select-DR, Capture-DR. It gives zero spare TCK edges.
//   - sel_a_i must not reverse faster than one full handshake.
//   - An asynchronous fall of rst_n_i in the middle of an A pulse can merge pulses. It never shortens one.
// Doc: ds:mod:dft-clk-switch, tm:mod:dft-clk-switch

module dft_clk_switch (
    input  logic tck_i,     // raw TCK: A-domain handshake clock, A's latch phase and output guard
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
    // Transparent while the OWN raw clock is low, hold while it is high. The A latch
    // is deliberately tck_i-only (DFT TAP clock rule); the race with the later fall
    // of the gated clk_a_i is closed by the tck_i term in the output. See tm:mod:dft-clk-switch.
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
    assign clk_o = (clk_a_i & en_a_q & tck_i) | (clk_b_i & en_b_q);

endmodule : dft_clk_switch
