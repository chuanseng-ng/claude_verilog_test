// trng_ro_sky130.sv
// Phase 6a-4 -- Sky130 ring-oscillator entropy arm of the TRNG (bead claude_verilog_test-f7vs.8,
// docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6a-4 -- TRNG"). Selected by `ifdef TRNG_RO_SKY130 inside
// trng.sv; the default build uses trng_lfsr_entropy.sv instead.
//
// BLACKBOX STUB -- NOT SYNTHESISABLE, NOT SIMULATABLE. This file exists only to pin the port
// contract of the swappable entropy arm (same ports as trng_lfsr_entropy.sv) so a Sky130-only
// build can hand the real ring-oscillator implementation to the analog flow (reusing
// analog/pll_clkgen/circuit/ring_vco.sp). That analog/PD deliverable is deferred out of Phase 6a.
// Same pattern as pnr/sky130/soc/sky130_sram_4kbyte_1rw1r_32x1024_8_stub.sv and
// rv32i_cpu_top_stub.sv: Yosys treats (* blackbox *) modules as externally defined cells.
//
// It is NOT in any file list and is not compiled in the default build
// (tools/verif/check_periph_filelists.py EXEMPT map). Never add it to one: an ASAP7/FreePDK45 flow
// that pulled it in would elaborate a peripheral whose entropy source does not exist there.
//
// Port contract (identical to trng_lfsr_entropy.sv):
//   load_i / seed_i   session start; a ring oscillator ignores the seed
//   flush_i           discard any partly assembled word (after a health failure)
//   run_i             consume one raw sample this clock; low = stall (backpressure, not a drop)
//   sample_valid_o / sample_o   raw (pre-debias) stream for the repetition-count health test
//   word_valid_o / word_o       debiased, assembled 32-bit words (combinational strobe on the
//                               clock the completing sample is consumed)
//
// Lint target: not linted -- excluded from every default build.

(* blackbox *)
module trng_ro_sky130 (
    input  logic        clk,
    input  logic        rst_n,

    input  logic        load_i,
    input  logic [31:0] seed_i,
    input  logic        flush_i,
    input  logic        run_i,

    output logic        sample_valid_o,
    output logic        sample_o,
    output logic        word_valid_o,
    output logic [31:0] word_o
);

endmodule : trng_ro_sky130
