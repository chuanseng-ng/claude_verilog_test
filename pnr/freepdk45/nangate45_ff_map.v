/*
 * Lighter DFF map for NangateOpenCellLibrary (FreePDK45 / nangate45)
 *
 * Adapted from the sky130_fd_sc_hd map shipped with yosys-lighter.
 * Replaces Yosys internal enabled-FF cells with CLKGATE_Xn + plain DFF.
 *
 * NanGate45 ICG cells:
 *   CLKGATE_X1 (.E(enable), .CK(clk), .GCK(gated_clk))  -- latch_posedge
 *   CLKGATE_X2, CLKGATE_X4, CLKGATE_X8
 *
 * Width thresholds (same as sky130 map):
 *   WIDTH <  5  --> CLKGATE_X1
 *   WIDTH < 17  --> CLKGATE_X2
 *   WIDTH >= 17 --> CLKGATE_X4
 */

// ---------------------------------------------------------------------------
// $dffe  -- simple enabled DFF (no reset)
// ---------------------------------------------------------------------------
module \$dffe (CLK, D, EN, Q);
    parameter CLK_POLARITY = 1'b1;
    parameter EN_POLARITY  = 1'b1;
    parameter WIDTH = 1;

    input  CLK, EN;
    input  [WIDTH-1:0] D;
    output [WIDTH-1:0] Q;

    wire GCLK;
    wire cg_enb;
    wire cg_clk;
    wire cg_gclk;

    generate
        if (EN_POLARITY == 0)
            assign cg_enb = ~EN;
        else
            assign cg_enb = EN;
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_clk = ~CLK;
        else
            assign cg_clk = CLK;
    endgenerate

    generate
        if (WIDTH < 5)
            CLKGATE_X1 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else if (WIDTH < 17)
            CLKGATE_X2 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else
            CLKGATE_X4 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_gclk = ~GCLK;
        else
            assign cg_gclk = GCLK;
    endgenerate

    \$dff #(
        .WIDTH(WIDTH),
        .CLK_POLARITY(CLK_POLARITY)
    ) flipflop (
        .CLK(cg_gclk),
        .D(D),
        .Q(Q)
    );
endmodule

// ---------------------------------------------------------------------------
// $adffe  -- enabled DFF with async reset
// ---------------------------------------------------------------------------
module \$adffe (ARST, CLK, D, EN, Q);
    parameter ARST_POLARITY = 1'b1;
    parameter ARST_VALUE    = 1'b0;
    parameter CLK_POLARITY  = 1'b1;
    parameter EN_POLARITY   = 1'b1;
    parameter WIDTH = 1;

    input  ARST, CLK, EN;
    input  [WIDTH-1:0] D;
    output [WIDTH-1:0] Q;

    wire GCLK;
    wire cg_enb;
    wire cg_clk;
    wire cg_gclk;

    generate
        if (EN_POLARITY == 0)
            assign cg_enb = ~EN;
        else
            assign cg_enb = EN;
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_clk = ~CLK;
        else
            assign cg_clk = CLK;
    endgenerate

    generate
        if (WIDTH < 5)
            CLKGATE_X1 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else if (WIDTH < 17)
            CLKGATE_X2 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else
            CLKGATE_X4 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_gclk = ~GCLK;
        else
            assign cg_gclk = GCLK;
    endgenerate

    \$adff #(
        .WIDTH(WIDTH),
        .CLK_POLARITY(CLK_POLARITY),
        .ARST_POLARITY(ARST_POLARITY),
        .ARST_VALUE(ARST_VALUE)
    ) flipflop (
        .CLK(cg_gclk),
        .ARST(ARST),
        .D(D),
        .Q(Q)
    );
endmodule

// ---------------------------------------------------------------------------
// $sdffe  -- enabled DFF with sync reset (EN valid after reset)
// ---------------------------------------------------------------------------
module \$sdffe (CLK, EN, SRST, D, Q);
    parameter CLK_POLARITY  = 1'b1;
    parameter EN_POLARITY   = 1'b1;
    parameter SRST_POLARITY = 1'b1;
    parameter SRST_VALUE    = 1'b0;
    parameter WIDTH = 1;

    input  CLK, EN, SRST;
    input  [WIDTH-1:0] D;
    output [WIDTH-1:0] Q;

    wire GCLK;
    wire cg_enb;
    wire cg_rstenb;
    wire cg_clk;
    wire cg_gclk;

    // clock must be enabled during reset so the sync reset can take effect
    generate
        if (SRST_POLARITY == 0)
            assign cg_rstenb = ~SRST;
        else
            assign cg_rstenb = SRST;
    endgenerate

    generate
        if (EN_POLARITY == 0)
            assign cg_enb = (~EN) | cg_rstenb;
        else
            assign cg_enb = EN | cg_rstenb;
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_clk = ~CLK;
        else
            assign cg_clk = CLK;
    endgenerate

    generate
        if (WIDTH < 5)
            CLKGATE_X1 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else if (WIDTH < 17)
            CLKGATE_X2 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else
            CLKGATE_X4 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_gclk = ~GCLK;
        else
            assign cg_gclk = GCLK;
    endgenerate

    \$sdff #(
        .WIDTH(WIDTH),
        .CLK_POLARITY(CLK_POLARITY),
        .SRST_POLARITY(SRST_POLARITY),
        .SRST_VALUE(SRST_VALUE)
    ) flipflop (
        .CLK(cg_gclk),
        .SRST(SRST),
        .D(D),
        .Q(Q)
    );
endmodule

// ---------------------------------------------------------------------------
// $sdffce  -- enabled DFF with sync reset (EN gates reset too)
// ---------------------------------------------------------------------------
module \$sdffce (CLK, EN, SRST, D, Q);
    parameter CLK_POLARITY  = 1'b1;
    parameter EN_POLARITY   = 1'b1;
    parameter SRST_POLARITY = 1'b1;
    parameter SRST_VALUE    = 1'b0;
    parameter WIDTH = 1;

    input  CLK, EN, SRST;
    input  [WIDTH-1:0] D;
    output [WIDTH-1:0] Q;

    wire GCLK;
    wire cg_enb;
    wire cg_clk;
    wire cg_gclk;

    generate
        if (EN_POLARITY == 0)
            assign cg_enb = ~EN;
        else
            assign cg_enb = EN;
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_clk = ~CLK;
        else
            assign cg_clk = CLK;
    endgenerate

    generate
        if (WIDTH < 5)
            CLKGATE_X1 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else if (WIDTH < 17)
            CLKGATE_X2 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else
            CLKGATE_X4 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_gclk = ~GCLK;
        else
            assign cg_gclk = GCLK;
    endgenerate

    \$sdff #(
        .WIDTH(WIDTH),
        .CLK_POLARITY(CLK_POLARITY),
        .SRST_POLARITY(SRST_POLARITY),
        .SRST_VALUE(SRST_VALUE)
    ) flipflop (
        .CLK(cg_gclk),
        .SRST(SRST),
        .D(D),
        .Q(Q)
    );
endmodule

// ---------------------------------------------------------------------------
// $dffsre  -- enabled DFF with async set and reset
// ---------------------------------------------------------------------------
module \$dffsre (CLK, EN, CLR, SET, D, Q);
    parameter CLK_POLARITY = 1'b1;
    parameter EN_POLARITY  = 1'b1;
    parameter CLR_POLARITY = 1'b1;
    parameter SET_POLARITY = 1'b1;
    parameter WIDTH = 1;

    input  CLK, EN, CLR, SET;
    input  [WIDTH-1:0] D;
    output [WIDTH-1:0] Q;

    wire GCLK;
    wire cg_enb;
    wire cg_clk;
    wire cg_gclk;

    generate
        if (EN_POLARITY == 0)
            assign cg_enb = ~EN;
        else
            assign cg_enb = EN;
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_clk = ~CLK;
        else
            assign cg_clk = CLK;
    endgenerate

    generate
        if (WIDTH < 5)
            CLKGATE_X1 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else if (WIDTH < 17)
            CLKGATE_X2 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
        else
            CLKGATE_X4 clk_gate (.GCK(GCLK), .CK(cg_clk), .E(cg_enb));
    endgenerate

    generate
        if (CLK_POLARITY == 0)
            assign cg_gclk = ~GCLK;
        else
            assign cg_gclk = GCLK;
    endgenerate

    \$dffsr #(
        .WIDTH(WIDTH),
        .CLK_POLARITY(CLK_POLARITY),
        .CLR_POLARITY(CLR_POLARITY),
        .SET_POLARITY(SET_POLARITY)
    ) flipflop (
        .CLK(cg_gclk),
        .CLR(CLR),
        .SET(SET),
        .D(D),
        .Q(Q)
    );
endmodule
