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
//        test_clk_o             = serial ? tck_scan_gated : pin_scan_clk
//
// With the TAP idle (IR != SCAN, which includes reset and Test-Logic-Reset) every
// term collapses to the 1a pin value, bit for bit. The TAP never gates the pin
// path.
//
// test_clk_o select contract (section 15.5, open question Q-CLK): the select
// `serial` is a falling-edge TCK flop that changes only in an Update state, where
// tck_scan_gated is provably low (the gate is closed in every state but Capture
// and Shift), so the TAP side of the mux cannot glitch. The pin side
// (scan_clk_i) must be held low by the tester while IR or SCAN_SEL.PARALLEL
// changes. This is a plain 2:1 select, not an enable-before-switch glitch-free
// mux (that needs a clock in the deselected domain and deadlocks with a stopped
// functional clock); entering scan mode destroys functional state anyway.
//
// The scan_mode/test_en/scan_rst/scan_en controls are TCK-launched quasi-static
// levels that deliberately cross into the functional domains unsynchronised
// (section 15.5 crossing 2; accepted-risk waiver in tools/cdc/cdc_config.yml).
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
    output logic test_clk_o
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
        .chain_grp_o    (tap_chain_grp)
    );

    // ── TCK scan-clock gate ──────────────────────────────────────────────────
    logic tck_scan_gated;

    rv32i_clock_gate u_tck_cg (
        .en      (tap_shift_clk_en),
        .test_en (1'b0),
        .clk     (tck_i),
        .gclk    (tck_scan_gated)
    );

    // ── Combiner (section 15.4) ──────────────────────────────────────────────
    assign scan_mode_o = pin_scan_mode | tap_scan;
    assign test_en_o   = pin_test_en   | tap_scan;
    assign scan_rst_no = pin_scan_rst_n & ~tap_rst_assert;
    assign scan_en_o   = tap_serial ? tap_scan_en    : pin_scan_en;
    assign test_clk_o  = tap_serial ? tck_scan_gated : pin_test_clk;

endmodule : dft_ctrl
