// npu_mac_array.sv
// Phase 6c -- NPU weight-stationary 4 x 4 INT8 MAC grid (bead claude_verilog_test-f7vs.11,
// docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6c -- NPU"; arithmetic spec: tb/models/npu_model.py).
//
// STRUCTURE. Row i (0..3) of the grid holds the four INT8 weights W[i][0..3] of one tile row;
// column j (0..3) is one output lane. Per chunk, npu_top loads the four tile rows one at a time
// (w_row_we_i[i] pulses with w_word_i = one SRAM word, byte j -> PE[i][j]), then presents the four
// activations a[0..3] (byte i of a_i) and pulses acc_en_i once:
//
//     prod[i][j] = W[i][j] * a[i]                        INT8 x INT8 -> INT16, one per PE
//     sum[j]     = (prod[0][j] + prod[1][j]) + (prod[2][j] + prod[3][j])   per-column adder tree
//     acc[j]    += sum[j]                                 INT32 accumulator per column
//
// i.e. y[j] = SUM_i W[i][j] * a[i], summed over every chunk of the inference -- the model's
// mac_chunk(). acc_clr_i zeroes the four accumulators (npu_top fires it at START; clear wins over
// enable, though they never coincide).
//
// BYTE LANES: little-endian, lane / element 0 is bits [7:0] of the 32-bit word, each byte a
// two's-complement INT8 (one rule for weights, activations and results; see the model).
//
// ACCUMULATOR WIDTH AND SATURATION. The accumulator is INT32. The model defines it as saturating,
// but the worst reachable magnitude is 63 chunks x 4 products x 16384 = 4,128,768 < 2**22 (and
// 2**22 even at the model's 64), so overflow is UNREACHABLE and a plain 32-bit add is observably
// identical to saturation. No saturation logic is built; do not read its absence as a bug.
//
// FULLY STRUCTURAL: every PE and every column is a genvar-indexed instance of the same code, every
// array index is a genvar or a literal. There is no runtime-indexed mux anywhere in this file
// (bead ma7). The PE weight flops carry no reset: they are always loaded (w_row_we_i) before the
// first accumulate of a chunk, so reset state is never observed. Control and accumulators are
// reset synchronously, active low, like the rest of periph/.
//
// GRID is fixed at 4 (the adder tree is written for four rows and the APB word packs four lanes);
// anything else is an elaboration error. Single clock domain, no CDC.
//
// Lint target: verilator --lint-only -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module npu_mac_array #(
    parameter int unsigned GRID = 4
) (
    input  logic                clk,
    input  logic                rst_n,

    // Weight load: row i captures w_word_i (byte j -> column j) when w_row_we_i[i] is high
    input  logic [GRID-1:0]     w_row_we_i,
    input  logic [8*GRID-1:0]   w_word_i,

    // Activations (byte i -> row i), accumulator control
    input  logic [8*GRID-1:0]   a_i,
    input  logic                acc_clr_i,
    input  logic                acc_en_i,

    // The four INT32 column accumulators, lane j in [32*j +: 32]
    output logic [32*GRID-1:0]  acc_o
);

    if (GRID != 4) begin : g_grid_check
        $fatal(1, "npu_mac_array: GRID (%0d) must be 4 (the column adder tree and the 32-bit APB word are written for four rows/lanes)", GRID);
    end

    logic signed [7:0]  w_q    [GRID][GRID];   // [row i][column j] stationary weights
    logic signed [15:0] prod_w [GRID][GRID];   // INT8 x INT8 -> INT16
    logic signed [17:0] sum_w  [GRID];         // 4 x INT16 fits in 18 bits signed
    logic signed [31:0] acc_q  [GRID];

    genvar i, j;
    generate
        for (i = 0; i < GRID; i++) begin : g_row
            for (j = 0; j < GRID; j++) begin : g_pe
                always_ff @(posedge clk) begin
                    if (w_row_we_i[i]) w_q[i][j] <= w_word_i[8*j +: 8];
                end
                assign prod_w[i][j] = 16'(w_q[i][j]) * 16'($signed(a_i[8*i +: 8]));
            end
        end

        for (j = 0; j < GRID; j++) begin : g_col
            assign sum_w[j] = (18'(prod_w[0][j]) + 18'(prod_w[1][j]))
                            + (18'(prod_w[2][j]) + 18'(prod_w[3][j]));

            always_ff @(posedge clk) begin
                if (!rst_n)          acc_q[j] <= 32'sd0;
                else if (acc_clr_i)  acc_q[j] <= 32'sd0;
                else if (acc_en_i)   acc_q[j] <= acc_q[j] + 32'(sum_w[j]);
            end

            assign acc_o[32*j +: 32] = acc_q[j];
        end
    endgenerate

endmodule : npu_mac_array
