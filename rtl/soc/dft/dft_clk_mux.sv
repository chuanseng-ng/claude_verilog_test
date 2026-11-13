// dft_clk_mux - test-clock bypass for one clock root.
//
// Function: clk_o is scan_clk_i when sel_i is 1. Otherwise clk_o is func_clk_i. The module is a plain 2:1 mux.
//   It is not a glitch-free switch.
//   With USE_SKY130_CLKCELLS the instance is hand-built: a mux2_4 cell (u_mux) and a buf_16 root buffer (u_root_buf).
//   The root buffer is a plain buf_16, not a clkbuf_16, so that CTS builds a tree on the net.
// Caller rules:
//   - sel_i must be quasi-static. Set it while neither clock runs. Do not toggle it while either clock runs.
//   - In functional mode (sel_i = 0) clk_o follows func_clk_i with no other logic.
//   - Keep the instance names u_mux and u_root_buf. RSZ_DONT_TOUCH_RX lists them.
// Doc: ds:mod:dft-clk-mux, cr:mod:dft-clk-mux

module dft_clk_mux (
    input  logic func_clk_i,
    input  logic scan_clk_i,
    input  logic sel_i,        // 1 = scan/test mode: use scan_clk_i
    output logic clk_o
);

`ifdef USE_SKY130_CLKCELLS
    logic mux_clk;
    sky130_fd_sc_hd__mux2_4    u_mux      (.A0(func_clk_i), .A1(scan_clk_i), .S(sel_i), .X(mux_clk));
    sky130_fd_sc_hd__buf_16    u_root_buf (.A(mux_clk), .X(clk_o));
`else
    assign clk_o = sel_i ? scan_clk_i : func_clk_i;
`endif

endmodule : dft_clk_mux
