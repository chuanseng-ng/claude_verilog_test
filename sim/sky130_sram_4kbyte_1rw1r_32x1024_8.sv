// sky130_sram_4kbyte_1rw1r_32x1024_8.sv
// Behavioral simulation model for the Sky130 4 KB OpenRAM SRAM macro
// (sky130_sram_4kbyte_1rw1r_32x1024_8, 1024 words x 32 bits, 4x 8-bit write
// mask granularity) — GH #104 Sky130 SoC Stage-2.
//
// This is the 4 KB sibling of sim/sky130_sram_1kbyte_1rw1r_32x256_8.sv (used
// by the CPU I$/D$ tag+data arrays): same OpenRAM 1RW1R port convention, and
// the same lint-tool-safe rewrite of the OpenRAM-generated model, scaled from
// 256 words/8-bit address to 1024 words/10-bit address.
//
//   - Port 0 (RW) inputs (addr/csb/web/wmask/din) are registered at posedge
//     clk0. Write and read operations execute at negedge clk0 using those
//     registered inputs, so dout0 is stable before the next posedge —
//     matching the "negedge-launched" Liberty characterisation: 1-cycle
//     registered read latency from address to data.
//   - Port 1 (R-only) behaves identically for reads: dout1 valid the cycle
//     after addr1/csb1 are presented (registered output).
//
// Differences from the raw OpenRAM verilog model (for Verilator
// compatibility), same convention as the 1 KB model:
//   - No `#delay` timing annotations.
//   - Only nonblocking `<=` assignments; write+read combined in one
//     always@(negedge) block per port to avoid multiple-driver lint errors.
//   - No $display diagnostics.
//
// This file is SIMULATION ONLY. Do not use for synthesis — the real physical
// view is the OpenRAM-generated LEF/LIB/GDS at
// /nobackup/openram_sky130_4kb/macro/sky130_sram_4kbyte_1rw1r_32x1024_8/.

/* verilator lint_off UNUSEDSIGNAL */
module sky130_sram_4kbyte_1rw1r_32x1024_8 (
    // Port 0: RW
    input         clk0,
    input         csb0,     // active-low chip select
    input         web0,     // active-low write enable
    input  [3:0]  wmask0,   // byte write mask
    input  [9:0]  addr0,
    input  [31:0] din0,
    output reg [31:0] dout0,
    // Port 1: R (dedicated read port — used exclusively by the AXI read
    // channel in sram_controller.sv; port 0 is used exclusively for writes)
    input         clk1,
    input         csb1,
    input  [9:0]  addr1,
    output reg [31:0] dout1
);

    // Memory array: 1024 words x 32 bits (4 KB)
    reg [31:0] mem [0:1023];

    // -------------------------------------------------------------------------
    // Port 0: register inputs at posedge clk0
    // -------------------------------------------------------------------------
    reg        csb0_r, web0_r;
    reg [3:0]  wmask0_r;
    reg [9:0]  addr0_r;
    reg [31:0] din0_r;

    always @(posedge clk0) begin
        csb0_r   <= csb0;
        web0_r   <= web0;
        wmask0_r <= wmask0;
        addr0_r  <= addr0;
        din0_r   <= din0;
    end

    // Write and read at negedge clk0 using registered inputs.
    always @(negedge clk0) begin
        if (!csb0_r && !web0_r) begin
            // Byte-masked write
            if (wmask0_r[0]) mem[addr0_r][7:0]   <= din0_r[7:0];
            if (wmask0_r[1]) mem[addr0_r][15:8]  <= din0_r[15:8];
            if (wmask0_r[2]) mem[addr0_r][23:16] <= din0_r[23:16];
            if (wmask0_r[3]) mem[addr0_r][31:24] <= din0_r[31:24];
        end
        if (!csb0_r && web0_r) begin
            // Read (unused in sram_controller.sv — port 0 is write-only there)
            dout0 <= mem[addr0_r];
        end
    end

    // -------------------------------------------------------------------------
    // Port 1: read-only
    // -------------------------------------------------------------------------
    reg        csb1_r;
    reg [9:0]  addr1_r;

    always @(posedge clk1) begin
        csb1_r  <= csb1;
        addr1_r <= addr1;
    end

    always @(negedge clk1) begin
        if (!csb1_r)
            dout1 <= mem[addr1_r];
    end

endmodule
/* verilator lint_on UNUSEDSIGNAL */
