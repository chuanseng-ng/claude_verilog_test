// sram_1rw_128x32_asap7.v
// Simulation-only behavioral model for the hand-crafted ASAP7 128x32 1RW SRAM
// macro used by the GPU shared-memory banks (rtl/gpu/shared_memory.sv).
//
// Verilator-friendly (no negedge, no #delays). Behaviour matches the FakeRAM /
// OpenRAM 1RW convention and the blackbox stub pnr/asap7/sram_1rw_128x32_asap7_stub.v:
//   - addr0/csb0/web0/din0 sampled on posedge clk0
//   - read data appears on dout0 ONE cycle after address presentation
//   - write commits one cycle after address/data presentation
//   - csb0 active-low chip select; web0 active-low write enable (low=write)
//
// For synthesis/P&R the blackbox stub + LEF + Liberty are used instead; this
// file is compiled only for cocotb simulation.

module sram_1rw_128x32_asap7 (
    input         clk0,   // clock
    input         csb0,   // active-low chip select
    input         web0,   // active-low write enable (low = write, high = read)
    input  [6:0]  addr0,  // 7-bit address (128 words)
    input  [31:0] din0,   // write data
    output [31:0] dout0   // read data (registered, available cycle after address)
);
    reg [31:0] mem [0:127];
    reg [31:0] dout0_r;

    always @(posedge clk0) begin
        if (!csb0) begin
            if (!web0)
                mem[addr0] <= din0;
            else
                dout0_r <= mem[addr0];
        end
    end

    assign dout0 = dout0_r;

endmodule
