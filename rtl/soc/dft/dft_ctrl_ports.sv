// dft_ctrl_ports - pass-through of the scan and test controls from the top-level ports.
//
// Function: soc_top wires every scan and test consumer to one instance of a module with this port list.
//   This module passes the ports through. dft_ctrl replaces it and makes the same five signals from the TAP.
//   scan_mode_o: 1 is test mode. It is quasi-static.
//   scan_en_o: 1 is shift and 0 is capture.
//   scan_rst_no: scan reset, active low.
//   test_en_o: clock-gate test enable.
//   test_clk_o: the shared shift and capture clock.
// Doc: ds:mod:dft-ctrl-ports

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
