// sram_1rw_256x32_freepdk45.sv
// Black-box stub for Verilator lint — not synthesised
// Real macro provided by FreePDK45 / ASAP7 SRAM library at P&R time.
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNDRIVEN */
module sram_1rw_256x32_freepdk45 (
    input  logic        clk0,
    input  logic        csb0,
    input  logic        web0,
    input  logic [7:0]  addr0,
    input  logic [31:0] din0,
    output logic [31:0] dout0
);
    // Behavioural model for lint/simulation purposes only.
    logic [31:0] mem [0:255];
    always_ff @(posedge clk0) begin
        if (!csb0) begin
            if (!web0) mem[addr0] <= din0;
            dout0 <= mem[addr0];
        end
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
/* verilator lint_on UNDRIVEN */
