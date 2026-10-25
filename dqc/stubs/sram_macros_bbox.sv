// sram_macros_bbox.sv - port-only black-box declarations of the SRAM hard macros.
//
// DQC flow (dqc/): SpyGlass and HAL must NOT look inside an SRAM macro.
//   * In the real chip these are hard macros (OpenRAM Sky130 / FreePDK45 / ASAP7) whose contents are
//     a bit-cell array, not RTL. The behavioural models in sim/ and rtl/mem/ exist only to let a
//     simulator run; they contain an always_ff memory array that a lint tool would report as
//     thousands of reset-less flops with a negedge-launched output, none of which is a property of
//     the real macro.
//   * Port-only modules are read as black boxes: their outputs are undriven inside the stub, so a
//     finding that is only "the macro output is undriven" is a stub artifact and is waived as such
//     (dqc/waivers/*.awl, tag "sram-bbox").
// Port lists are copied from the models they replace:
//   sram_1rw_256x32_freepdk45            rtl/mem/sram_1rw_256x32_freepdk45.sv   (default arm)
//   sky130_sram_1kbyte_1rw1r_32x256_8    sim/sky130_sram_1kbyte_1rw1r_32x256_8.sv   (SRAM_SKY130 arm)
//   sky130_sram_4kbyte_1rw1r_32x1024_8   sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv  (SRAM_SKY130 arm)
// Only the stub file(s) of the selected arm are loaded (see dqc/Makefile ARM=).

module sram_1rw_256x32_freepdk45 (
    input  logic        clk0,
    input  logic        csb0,
    input  logic        web0,
    input  logic [7:0]  addr0,
    input  logic [31:0] din0,
    output logic [31:0] dout0
);
endmodule
