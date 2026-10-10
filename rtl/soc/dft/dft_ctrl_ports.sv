// dft_ctrl_ports.sv
// DFT Stage 1a (bead claude_verilog_test-j41m.2, GH #244).
//
// THE seam between "who generates the test controls" and "who consumes them".
// soc_top wires every scan/test consumer to the outputs of ONE instance of a
// module with this port list. In Stage 1a the controls come straight from
// top-level ports, so this module is a pass-through. Stage 1b (bead j41m.3)
// replaces this module with the JTAG-TAP-driven dft_ctrl that generates the
// same five signals from the TAP's TDRs (OR-ing the TAP control with the raw
// ports as decided); no consumer changes, no re-plumbing of soc_top.
//
//   scan_mode_o   1 = test mode: test clock in, scan reset in, clock gates forced open,
//                 secret-dependent nets masked. Quasi-static.
//   scan_en_o     1 = shift, 0 = capture. Consumed only by the scan flops that Stage 2
//                 inserts (no RTL consumer in 1a; the net is kept so insertion has
//                 one named driver to connect to -- see docs/design/DFT_ARCHITECTURE.md
//                 section 14, "Scan port contract").
//   scan_rst_no   scan reset, active low. Delivered to the flops by the dft_rst_mux
//                 instances and the cdc_reset_sync output muxes while scan_mode_o = 1.
//   test_en_o     clock-gate test enable (scan_mode | mbist_en once MBIST exists, Stage 4).
//   test_clk_o    the shared shift/capture clock for all scanned domains.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module dft_ctrl_ports (
    input  logic scan_mode_i,
    input  logic scan_en_i,
    input  logic scan_rst_ni,
    input  logic scan_clk_i,

    output logic scan_mode_o,
    output logic scan_en_o,
    output logic scan_rst_no,
    output logic test_en_o,
    output logic test_clk_o
);

    assign scan_mode_o = scan_mode_i;
    assign scan_en_o   = scan_en_i;
    assign scan_rst_no = scan_rst_ni;
    assign test_en_o   = scan_mode_i;   // + mbist_en in Stage 4
    assign test_clk_o  = scan_clk_i;

endmodule : dft_ctrl_ports
