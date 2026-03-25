// sram_1rw_256x32_verilator.v
// Simulation-only behavioral model for sram_1rw_256x32_freepdk45.
// Compatible with Verilator (no negedge triggers, no mixed assignments, no #delays).
//
// Functional behavior matches the OpenRAM model:
//   - Inputs (addr0, csb0, web0, din0) are registered on posedge clk0.
//   - Read data appears on dout0 one cycle after address presentation.
//   - Write data is committed one cycle after address/data presentation.
//
// Cache FSM compatibility:
//   Address presented in CS_IDLE → dout0 valid at start of CS_SRAM_LATCH.

module sram_1rw_256x32_freepdk45 (
    input         clk0,   // clock
    input         csb0,   // active-low chip select
    input         web0,   // active-low write enable
    input  [7:0]  addr0,  // 8-bit address (256 words)
    input  [31:0] din0,   // write data
    output [31:0] dout0   // read data (registered, available cycle after address)
);
    reg [31:0] mem [0:255];
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
