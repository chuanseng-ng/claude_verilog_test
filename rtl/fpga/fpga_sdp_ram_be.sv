// fpga_sdp_ram_be.sv
// FPGA Stage 0 (bead hlrm, GH #245) -- simple-dual-port, byte-enabled, block-RAM-inferable memory for
// sram_controller's `FPGA arm (stand-in for sky130_sram_4kbyte_1rw1r_32x1024_8 used as write-port-0 +
// read-port-1). Selected ONLY under `FPGA.
//
//   write port : we_i[b] writes byte b of wdata_i to waddr_i at the posedge
//   read port  : re_i captures mem[raddr_i] into rdata_o at the posedge (ONE registered-read cycle);
//                rdata_o holds when re_i is low
//   same-address read+write in one cycle returns the OLD word (read-first). sram_controller's masters
//   cannot rely on that window (the Sky130 macro arm races there too); this is the native block-RAM mode.
//
// Inference rules: synchronous read, no reset on array or output register, byte-write written as a for-loop
// over constant byte slices of one array element, array indexed only by waddr_i / raddr_i. No `initial`.

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
