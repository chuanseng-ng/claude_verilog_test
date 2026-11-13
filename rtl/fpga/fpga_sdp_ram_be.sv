// fpga_sdp_ram_be - Simple-dual-port, byte-enabled, block-RAM-inferable memory for the FPGA build.
//
// Function: Stand-in for sky130_sram_4kbyte_1rw1r_32x1024_8 used as write port 0 plus read port 1.
//   sram_controller instantiates it only under `FPGA.
//   Write port: we_i[b] writes byte b of wdata_i to waddr_i at the posedge of clk.
//   Read port: re_i captures mem[raddr_i] into rdata_o at the posedge. The read takes one registered cycle. rdata_o holds when re_i is low.
//   A read and a write to the same address in one cycle return the old word (read-first).
//   Inference rules: synchronous read, no reset on the array or the output register, no `initial`.
//   The byte write is a for-loop over constant byte slices of one array element. The array is indexed only by waddr_i and raddr_i.
// Parameters: WORDS (depth in words, a power of two, default 1024). AW is a localparam, $clog2(WORDS).
// Clocks and resets: clk is the only clock. The array and rdata_o have no reset.
// Caller rules:
//   - Masters of sram_controller must not rely on the same-address read and write window.
//     The Sky130 macro arm races there too. Read-first is the native block-RAM mode.
// Doc: ds:mod:fpga-sdp-ram-be, tm:mod:fpga-sdp-ram-be, cr:mod:fpga-sdp-ram-be

module fpga_sdp_ram_be #(
    parameter int unsigned WORDS = 1024,         // power of two
    localparam int unsigned AW   = $clog2(WORDS)
) (
    input  logic          clk,

    input  logic [3:0]    we_i,
    input  logic [AW-1:0] waddr_i,
    input  logic [31:0]   wdata_i,

    input  logic          re_i,
    input  logic [AW-1:0] raddr_i,
    output logic [31:0]   rdata_o
);

    logic [31:0] mem [0:WORDS-1];
    logic [31:0] rdata_q;

    always_ff @(posedge clk) begin
        for (int b = 0; b < 4; b++) begin
            if (we_i[b]) begin
                mem[waddr_i][b*8 +: 8] <= wdata_i[b*8 +: 8];
            end
        end
        if (re_i) begin
            rdata_q <= mem[raddr_i];
        end
    end

    assign rdata_o = rdata_q;

endmodule : fpga_sdp_ram_be
