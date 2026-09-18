// Behavioural functional model for sram_1rw_256x32_asap7, the compiled
// 1RW 256x32 SRAM macro instantiated by the I$/D$ data arrays inside the
// rv32i_cpu_top hard macro (bead claude_verilog_test-b0t part B CPU/GPU
// macro extension, 2026-09-18) and by gpu_top's shared_memory (see bead
// gcd's/part A's note: this same macro is the source of the 256 unproven
// EQY points on shared_memory -- "exactly the SRAM-macro read-data bits
// blocked by the blackbox's missing SAT model").
//
// The tracked pnr/asap7/sram_1rw_256x32_asap7_stub.v is a TRUE (* blackbox
// *) stub with an empty body, used only to preserve connectivity for
// LibreLane synthesis -- its own header says so explicitly ("Replace with
// OpenRAM-compiled sram_1rw_256x32_asap7.v once ... available"). ASAP7 is a
// predictive PDK with no vendor-supplied gate-level or behavioural SRAM
// model at all. Reading the blackbox stub (or nothing) for gate-level `sim`
// leaves dout0 permanently X -- confirmed to be the root cause of an X
// cascade through the CPU macro's I$ fetch path within ~2 cache-line
// refills of a from-reset gate-level run (the first fetch's data still
// reads back correctly because -zinit gives dout0 a defined 0 at time 0;
// the SECOND read is the first one that actually depends on dout0 being
// driven by real write-then-read logic, which is where X first appears).
//
// This model implements the documented port semantics (header comment of
// the stub file, "identical to sram_1rw_256x32_freepdk45"): clk0 posedge,
// csb0 active-low chip select, web0 active-low write enable, addr0[7:0],
// din0[31:0], dout0[31:0] REGISTERED (available the cycle after the access,
// standard 1RW read latency) -- a reasonable, standard synchronous-SRAM
// behavioural model, not a vendor-verified one (none exists for this PDK).
module sram_1rw_256x32_asap7 (
    input  wire        clk0,
    input  wire        csb0,
    input  wire        web0,
    input  wire [ 7:0] addr0,
    input  wire [31:0] din0,
    output reg  [31:0] dout0
);
  reg [31:0] mem [0:255];
  always @(posedge clk0) begin
    if (!csb0) begin
      if (!web0)
        mem[addr0] <= din0;
      dout0 <= mem[addr0];
    end
  end
endmodule
