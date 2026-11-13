// npu_mac_array - weight-stationary 4 x 4 INT8 MAC grid for the NPU.
//
// Function: Row i (0..3) holds the four INT8 weights W[i][0..3] of one tile row. Column j is one output lane.
//   Per chunk, npu_top loads the four tile rows one at a time. w_row_we_i[i] pulses with w_word_i,
//   one SRAM word, and byte j goes to PE[i][j]. Then npu_top presents a[0..3] (byte i of a_i) and pulses acc_en_i once.
//     prod[i][j] = W[i][j] * a[i]   (INT8 x INT8 to INT16, one per PE)
//     sum[j] = (prod[0][j] + prod[1][j]) + (prod[2][j] + prod[3][j])   (per-column adder tree)
//     acc[j] += sum[j]   (INT32 accumulator per column)
//   So y[j] is the sum over rows i of W[i][j] * a[i], summed over every chunk of the inference.
//   Every PE and every column is a genvar-indexed instance. The file has no runtime-indexed mux.
// Parameters: GRID (must be 4; any other value is an elaboration error).
// Ports: w_row_we_i, w_word_i (byte j to column j), a_i (byte i to row i), acc_clr_i, acc_en_i,
//   acc_o (four INT32 lanes, lane j in [32*j +: 32]).
//   acc_clr_i zeroes the four accumulators. Clear wins over enable. npu_top fires it at START.
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous. The module has no CDC.
//   Only the accumulators reset. The PE weight flops have no reset.
// Caller rules:
//   - Load every tile row with w_row_we_i before the first accumulate of a chunk. Reset state is never observed.
//   - Lanes are little-endian: element 0 is bits [7:0]. Each byte is a two's-complement INT8.
//   - The accumulator is a plain 32-bit add with no saturation. The worst reachable magnitude is below 2**22,
//     so overflow is unreachable. Do not read the missing saturation logic as a bug.
// Doc: ds:mod:npu-mac-array, tm:mod:npu-mac-array

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
