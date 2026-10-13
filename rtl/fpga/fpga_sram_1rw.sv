// fpga_sram_1rw.sv
// FPGA Stage 0 (bead hlrm, GH #245) -- block-RAM-inferable stand-in for every 32-bit-wide 1RW SRAM hard macro
// (sram_1rw_256x32_*, sram_1rw_128x32_asap7). Selected ONLY under `FPGA; no other arm references it.
//
// Port contract is the macro/sim contract, so a site changes nothing but the module name:
//   - csb0 active-low chip select, web0 active-low write enable (low = write)
//   - write commits at the posedge; a READ captures mem[addr0] into the output register at the posedge
//   - dout0 HOLDS its last value on a write cycle and when csb0 is high -- identical to
//     sim/sram_1rw_256x32_verilator.v and sim/sram_1rw_128x32_asap7.v, the models every cocotb build
//     compiles. (rtl/mem/sram_1rw_256x32_freepdk45.sv, the lint stub, instead refreshes dout on a write;
//     it is not what the regression uses and is deliberately not copied.)
//
// Block-RAM inference rules honoured: synchronous read, NO reset on the array or the read register, ONE
// address shared by read and write, the array indexed only by that address (no runtime-indexed mux of
// flops). No `initial`, no vendor primitive: the same file is valid for yosys synth_xilinx / synth_ecp5 /
// vendor tools. Read-during-write cannot occur (one port, read and write are exclusive by web0).
//
// The "hold on a write" semantic is a read-enable (csb0 low AND web0 high) on the output register, which is
// the no-change / enable behaviour block RAMs have natively; if a toolchain cannot map it, it falls back to
// a read-first block RAM plus a feedback mux and the report must say so.

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
