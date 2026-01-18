// Simple counter module for cocotb demonstration
// This shows cocotb working before Phase 1 RTL exists

module example_counter #(
    parameter WIDTH = 8
)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire             enable,
    output reg [WIDTH-1:0]  count
);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= '0;
        end else if (enable) begin
            count <= count + 1'b1;
        end
    end

endmodule
