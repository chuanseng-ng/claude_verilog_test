// fpga_sram_1rw - Block-RAM-inferable stand-in for the 32-bit-wide 1RW SRAM hard macros.
//
// Function: Replaces sram_1rw_256x32_* and sram_1rw_128x32_asap7. Only the `FPGA arm references it.
//   The port contract is the macro and simulation contract, so a site changes only the module name.
//   csb0 is an active-low chip select. web0 is an active-low write enable (low = write).
//   A write commits at the posedge of clk0. A read captures mem[addr0] into the output register at the posedge.
//   dout0 holds its last value on a write cycle and when csb0 is high.
//   This matches sim/sram_1rw_256x32_verilator.v and sim/sram_1rw_128x32_asap7.v, the models every cocotb build compiles.
//   rtl/mem/sram_1rw_256x32_freepdk45.sv (the lint stub) refreshes dout on a write. This module does not copy that.
//   Inference rules: synchronous read, no reset on the array or the read register, one address shared by read and write, no `initial`, no vendor primitive.
//   The array is indexed only by addr0.
//   A read during a write cannot occur, because one port makes read and write exclusive by web0.
// Parameters: AW (address bits, default 8; depth = 2**AW words).
// Clocks and resets: clk0 is the only clock. The array and dout0 have no reset.
// Caller rules:
//   - Instantiate it only under `FPGA.
//   - If a toolchain cannot map hold-on-write to a block RAM, it builds a read-first block RAM plus a feedback mux.
//     The synthesis report must say so.
// Doc: ds:mod:fpga-sram-1rw, tm:mod:fpga-sram-1rw, cr:mod:fpga-sram-1rw

module fpga_sram_1rw #(
    parameter int unsigned AW = 8               // address bits; depth = 2**AW words
) (
    input  logic          clk0,
    input  logic          csb0,
    input  logic          web0,
    input  logic [AW-1:0] addr0,
    input  logic [31:0]   din0,
    output logic [31:0]   dout0
);

    logic [31:0] mem [0:(1<<AW)-1];
    logic [31:0] dout_q;

    always_ff @(posedge clk0) begin
        if (!csb0) begin
            if (!web0) begin
                mem[addr0] <= din0;
            end else begin
                dout_q <= mem[addr0];
            end
        end
    end

    assign dout0 = dout_q;

endmodule : fpga_sram_1rw
