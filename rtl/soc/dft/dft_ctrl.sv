// dft_ctrl.sv
// DFT Stage 1b (bead claude_verilog_test-j41m.3, GH #244).
//
// The TAP-driven DFT controller. Same five outputs and the same four test inputs
// as dft_ctrl_ports (Stage 1a), plus the JTAG pins, so soc_top swaps one module
// for the other and no consumer changes (docs/design/DFT_ARCHITECTURE.md
// section 15). Contents:
//   * u_tap          jtag_tap, TCK domain, all outputs falling-edge flops
//   * u_pins         the UNCHANGED 1a pin leg (dft_ctrl_ports)
//   * u_tck_cg       rv32i_clock_gate on TCK: tck_scan_gated, open only in
//                    Capture-DR and Shift-DR while the TAP is in serial scan, so
//                    the scanned flops see the capture edge and the shift edges
//                    and no edge in Run-Test/Idle, Pause or Update (no spurious
//                    capture). test_en is tied 0: the gate is opened by the TAP's
//                    state, never by scan_mode.
//   * the combiner of section 15.4:
//
//        scan_mode_o, test_en_o = pin | tap_scan
//        scan_rst_no            = pin_scan_rst_n & ~rst_assert
//        scan_en_o              = serial ? tap_scan_en   : pin_scan_en
//        test_clk_o             = glitch-free switch (serial ? tck_scan_gated
//                                                              : pin_scan_clk)
//
// With the TAP idle (IR != SCAN, which includes reset and Test-Logic-Reset) every
// term collapses to the 1a pin value, bit for bit. The TAP never gates the pin
// path.
//
// test_clk_o select (section 15.5, open question Q-CLK, RESOLVED): u_clk_sw is a
// glitch-free enable-before-switch selector (dft_clk_switch) between
// tck_scan_gated (A) and the pin test clock (B). The select `serial` is the
// TAP's falling-edge flop; the enable latches inside the switch retire the old
// clock and enable the new one so that no runt pulse and no extra edge reaches
// test_clk_o whatever the A/B phase relation. Its handshake is reset by u_sw_rst,
// a second cdc_reset_sync on trst_ni in the TCK domain (kept here so jtag_tap
// is unchanged): reset selects the pin clock with the TAP clock off, so the 1a
// pins-only operation (TAP in reset, TCK stopped) passes scan_clk_i through.
// Tester contract (details in dft_clk_switch.sv): after serial -> parallel the
// first pin-clock pulse appears at once if scan_clk_i was stopped during scan, or
// about 3 pin-clock cycles later if it was toggling; parallel -> serial needs no
// pin-clock edge if scan_clk_i idles LOW (stopped HIGH, it cannot complete).
//
// The scan_mode/test_en/scan_rst/scan_en controls are TCK-launched quasi-static
// levels that deliberately cross into the functional domains unsynchronised
// (section 15.5 crossing 2). This is not a waiver: tck_i is listed under
// reset_domains in tools/cdc/cdc_config.yml, which only removes it from the CDC
// gate's domain count, and tools/dft/check_scan_clk_rst.py --tap-allowed-nets keeps
// the TCK-launched nets that may reach non-TAP logic enumerated and checked.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module dft_ctrl (
    // ── Stage 1a direct (parallel) pins ──────────────────────────────────────
    input  logic scan_mode_i,
    input  logic scan_en_i,
    input  logic scan_rst_ni,
    input  logic scan_clk_i,

    // ── JTAG pins ────────────────────────────────────────────────────────────
    input  logic tck_i,
    input  logic tms_i,
    input  logic tdi_i,
    input  logic trst_ni,
    output logic tdo_o,
    output logic tdo_oe_o,

    // ── Controls to the SoC (names identical to dft_ctrl_ports) ─────────────
    output logic scan_mode_o,
    output logic scan_en_o,
    output logic scan_rst_no,
    output logic test_en_o,
    output logic test_clk_o,

    // ── MBIST (Stage 4, section 16.5): TAP data registers and TCK-side crossing hooks ──────────
    output logic [28:0]  mbist_ctl_o,       // MBIST_CTRL update register
    output logic         mbist_wr_o,        // one-TCK-edge write strobe
    output logic         mbist_force_o,     // CPU clock-gate force (run & dom_cpu)
    output logic         mbist_rst_tck_n_o, // TCK-domain reset derived from trst_ni (FIFO write side)
    input  logic         mbist_wr_ready_i,
    input  logic [138:0] mbist_status_i
);

    // ── Pin leg (unchanged Stage 1a module) ──────────────────────────────────
    logic pin_scan_mode;
    logic pin_scan_en;
    logic pin_scan_rst_n;
    logic pin_test_en;
    logic pin_test_clk;

    dft_ctrl_ports u_pins (
        .scan_mode_i (scan_mode_i),
        .scan_en_i   (scan_en_i),
        .scan_rst_ni (scan_rst_ni),
        .scan_clk_i  (scan_clk_i),
        .scan_mode_o (pin_scan_mode),
        .scan_en_o   (pin_scan_en),
        .scan_rst_no (pin_scan_rst_n),
        .test_en_o   (pin_test_en),
        .test_clk_o  (pin_test_clk)
    );

    // ── TAP ──────────────────────────────────────────────────────────────────
    logic tap_scan;
    logic tap_serial;
    logic tap_rst_assert;
    logic tap_scan_en;
    logic tap_shift_clk_en;

    // Test visibility only (state_o), the parallel-select flag and chain_grp have
    // no consumer until Stage 2; kept as ports of jtag_tap for the unit suite.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [3:0] tap_state;
    logic       tap_parallel;
    logic [1:0] tap_chain_grp;
    /* verilator lint_on  UNUSEDSIGNAL */

    jtag_tap u_tap (
        .tck_i          (tck_i),
        .tms_i          (tms_i),
        .tdi_i          (tdi_i),
        .trst_ni        (trst_ni),
        .tdo_o          (tdo_o),
        .tdo_oe_o       (tdo_oe_o),
        .state_o        (tap_state),
        .scan_mode_o    (tap_scan),
        .serial_o       (tap_serial),
        .parallel_o     (tap_parallel),
        .rst_assert_o   (tap_rst_assert),
        .scan_en_o      (tap_scan_en),
        .shift_clk_en_o (tap_shift_clk_en),
        .chain_grp_o    (tap_chain_grp),
        .mbist_ctl_o      (mbist_ctl_o),
        .mbist_wr_o       (mbist_wr_o),
        .mbist_force_o    (mbist_force_o),
        .mbist_wr_ready_i (mbist_wr_ready_i),
        .mbist_status_i   (mbist_status_i)
    );

    // ── TCK scan-clock gate ──────────────────────────────────────────────────
    logic tck_scan_gated;

    rv32i_clock_gate u_tck_cg (
        .en      (tap_shift_clk_en),
        .test_en (1'b0),
        .clk     (tck_i),
        .gclk    (tck_scan_gated)
    );

    // ── Glitch-free test-clock select (section 15.5) ─────────────────────────
    // Own TCK-domain reset synchroniser from trst_ni (scanmode_i = 0,
    // scan_rst_ni = 1): the switch resets with the TAP but jtag_tap is untouched.
    logic sw_rst_n;

    cdc_reset_sync #(
        .STAGES(2)
    ) u_sw_rst (
        .clk_i       (tck_i),
        .rst_n_i     (trst_ni),
        .scanmode_i  (1'b0),
        .scan_rst_ni (1'b1),
        .rst_n_o     (sw_rst_n)
    );

    assign mbist_rst_tck_n_o = sw_rst_n;

    dft_clk_switch u_clk_sw (
        .tck_i   (tck_i),
        .clk_a_i (tck_scan_gated),
        .clk_b_i (pin_test_clk),
        .sel_a_i (tap_serial),
        .rst_n_i (sw_rst_n),
        .clk_o   (test_clk_o)
    );

    // ── Combiner (section 15.4) ──────────────────────────────────────────────
    assign scan_mode_o = pin_scan_mode | tap_scan;
    assign test_en_o   = pin_test_en   | tap_scan;
    assign scan_rst_no = pin_scan_rst_n & ~tap_rst_assert;
    assign scan_en_o   = tap_serial ? tap_scan_en    : pin_scan_en;

endmodule : dft_ctrl
