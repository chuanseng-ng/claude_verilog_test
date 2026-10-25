// sram_macros_gpu_bbox.sv - port-only black box of the GPU shared-memory bank macro.
// rtl/gpu/shared_memory.sv instantiates sram_1rw_128x32_asap7 in every arm that is not FPGA
// (the GPU stays ASAP7-indicative, CLAUDE.md "Sky130 real DRC/LVS sign-off"); its sim model is
// sim/sram_1rw_128x32_asap7.v. See sram_macros_bbox.sv for why SRAM macros are black boxes.
module sram_1rw_128x32_asap7 (
    input  logic        clk0,
    input  logic        csb0,
    input  logic        web0,
    input  logic [6:0]  addr0,
    input  logic [31:0] din0,
    output logic [31:0] dout0
);
endmodule
