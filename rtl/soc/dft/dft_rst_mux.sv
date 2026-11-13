// dft_rst_mux - reset override for one reset net.
//
// Function: rst_n_o is scan_rst_ni when scan_mode_i is 1. Otherwise rst_n_o is func_rst_n_i.
//   The module adds no other logic. It sits at the net that feeds the flops, not at a synchroniser input.
// Caller rules:
//   - scan_mode_i must be quasi-static.
//   - In scan mode the tester owns the timing of scan_rst_ni. The module does not re-time it.
// Doc: ds:mod:dft-rst-mux

module dft_rst_mux (
    input  logic func_rst_n_i,
    input  logic scan_rst_ni,
    input  logic scan_mode_i,   // 1 = scan/test mode: use scan_rst_ni
    output logic rst_n_o
);

    assign rst_n_o = scan_mode_i ? scan_rst_ni : func_rst_n_i;

endmodule : dft_rst_mux
