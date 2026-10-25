// sky130_sram_1kbyte_1rw1r_32x256_8.sv
// Behavioral simulation model for the Sky130 1 KB SRAM macro (compatible with Verilator).
//
// Functionally equivalent to the PDK Liberty model:
//   - Port 0 inputs (addr/csb/web/wmask/din) are registered at posedge clk0.
//   - Write and read operations execute at negedge clk0 using those registered inputs.
//   - dout0 is therefore stable before the next posedge, matching the
//     "negedge-launched" Liberty characterisation: the cache RTL must
//     capture dout0 one full cycle after issuing the read address
//     (the CS_SRAM_LATCH pipeline register state does exactly this).
//
// Differences from the PDK verilog model (for Verilator compatibility):
//   - No `#delay` timing annotations (Verilator --no-timing drops these anyway).
//   - All blocking assignments removed; only nonblocking `<=` used.
//   - Write and read combined in one always@(negedge) block to avoid
//     multiple-driver lint errors on `mem`.
//   - No $display diagnostics.
//   - dout0/dout1 power up as 32'd0 (an `initial` block, not declaration
//     initialisers: Verilator >= 5.04x flags a declaration initialiser on a
//     procedurally written variable as PROCASSINIT), not X: before a
//     port's first read the output register otherwise differs between a 4-state
//     simulator (X) and Verilator (0), and a consumer that samples dout before
//     its first read would see simulator-dependent data. This matches the 4 KB
//     sibling (sky130_sram_4kbyte_1rw1r_32x1024_8.sv) and the fault-injecting
//     test model (tb/cocotb/soc/sram_fi_core.sv), which also reset their outputs
//     to 0. The memory ARRAY is deliberately left uninitialised (a real SRAM
//     powers up with undefined contents; X is the honest value): a read of a
//     never-written word returns X.
//
// This file is SIMULATION ONLY. Do not use for synthesis.

/* verilator lint_off UNUSEDSIGNAL */
module sky130_sram_1kbyte_1rw1r_32x256_8 (
    // Port 0: RW
    input         clk0,
    input         csb0,     // active-low chip select
    input         web0,     // active-low write enable
    input  [3:0]  wmask0,   // byte write mask
    input  [7:0]  addr0,
    input  [31:0] din0,
    output reg [31:0] dout0,
    // Port 1: R (unused in this design — port 1 tied off at instantiation sites)
    input         clk1,
    input         csb1,
    input  [7:0]  addr1,
    output reg [31:0] dout1
);

    // Power-up value of the output registers (see header). Plain always blocks
    // write them below, so an initial block is legal (IEEE 1800 9.2.2.4 restricts
    // only always_ff targets).
    initial begin
        dout0 = 32'd0;
        dout1 = 32'd0;
    end

    // Memory array: 256 words × 32 bits
    reg [31:0] mem [0:255];

    // -------------------------------------------------------------------------
    // Port 0: register inputs at posedge clk0
    // -------------------------------------------------------------------------
    reg        csb0_r, web0_r;
    reg [3:0]  wmask0_r;
    reg [7:0]  addr0_r;
    reg [31:0] din0_r;

    always @(posedge clk0) begin
        csb0_r   <= csb0;
        web0_r   <= web0;
        wmask0_r <= wmask0;
        addr0_r  <= addr0;
        din0_r   <= din0;
    end

    // Write and read at negedge clk0 using registered inputs.
    // Due to nonblocking semantics, the dout0 read sees the pre-write mem
    // content when both a write and read occur in the same cycle (acceptable;
    // the cache never simultaneously reads and writes the same SRAM address).
    always @(negedge clk0) begin
        if (!csb0_r && !web0_r) begin
            // Byte-masked write
            if (wmask0_r[0]) mem[addr0_r][7:0]   <= din0_r[7:0];
            if (wmask0_r[1]) mem[addr0_r][15:8]  <= din0_r[15:8];
            if (wmask0_r[2]) mem[addr0_r][23:16] <= din0_r[23:16];
            if (wmask0_r[3]) mem[addr0_r][31:24] <= din0_r[31:24];
        end
        if (!csb0_r && web0_r) begin
            // Read
            dout0 <= mem[addr0_r];
        end
    end

    // -------------------------------------------------------------------------
    // Port 1: read-only (unused — csb1 is tied high at all instantiation sites)
    // -------------------------------------------------------------------------
    reg        csb1_r;
    reg [7:0]  addr1_r;

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
