// RV32I Debug Controller - Manages breakpoints and debug state
module rv32i_debug
    import rv32i_pkg::*;
(
    input  logic             clk,
    input  logic             rst_n,

    // Current PC from CPU
    input  logic [XLEN-1:0]  pc,

    // Breakpoint configuration (from APB slave)
    input  logic [XLEN-1:0]  bp0_addr,
    input  logic             bp0_en,
    input  logic [XLEN-1:0]  bp1_addr,
    input  logic             bp1_en,

    // Breakpoint hit output
    output logic             bp_hit,
    output logic [1:0]       bp_index  // Which breakpoint was hit
);

    // Breakpoint comparison
    logic bp0_match, bp1_match;

    assign bp0_match = bp0_en && (pc == bp0_addr);
    assign bp1_match = bp1_en && (pc == bp1_addr);

    // Breakpoint hit detection
    assign bp_hit = bp0_match || bp1_match;

    // Breakpoint index (priority to BP0)
    always_comb begin
        if (bp0_match)
            bp_index = 2'b00;
        else if (bp1_match)
            bp_index = 2'b01;
        else
            bp_index = 2'b00;
    end

endmodule
