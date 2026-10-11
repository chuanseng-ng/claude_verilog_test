// dft_rst_mux.sv
// DFT Stage 1a (bead claude_verilog_test-j41m.2, GH #244).
//
// Reset override for one reset NET: in scan mode the reset delivered to the
// flops is the tester's scan reset, otherwise the functional (possibly
// internally generated) reset. Placed at the net that feeds the flops, not at a
// synchroniser input (docs/design/DFT_ARCHITECTURE.md sec.4 item 7), because a
// reset derived from flops, a register bit or a lock counter would otherwise
// toggle while the chains shift and clear or set scanned flops mid-shift.
//
// A module of its own for the same reason as dft_clk_mux: one greppable name for
// the Stage 2 insertion step and for tools/dft/check_scan_clk_rst.py, which
// proves that every async reset in the netlist is either a primary input or the
// output of one of these (or of a cdc_reset_sync's output mux).
//
// scan_mode_i is quasi-static. Functional mode (scan_mode_i = 0): rst_n_o ===
// func_rst_n_i, no logic other than the mux. In scan mode scan_rst_ni is not
// re-timed onto any clock; the tester owns its timing (Stage 2 scan-mode SDC).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module dft_rst_mux (
    input  logic func_rst_n_i,
    input  logic scan_rst_ni,
    input  logic scan_mode_i,   // 1 = scan/test mode: use scan_rst_ni
    output logic rst_n_o
);

    assign rst_n_o = scan_mode_i ? scan_rst_ni : func_rst_n_i;

endmodule : dft_rst_mux
