// trng_ro_sky130 - Sky130 ring-oscillator entropy arm of the TRNG. Blackbox stub.
//
// Function: This file pins the port contract of the swappable entropy arm. It has the same ports as trng_lfsr_entropy.sv.
//   trng.sv selects it under `ifdef TRNG_RO_SKY130. The default build uses trng_lfsr_entropy.sv instead.
//   The file is a blackbox stub. It is NOT synthesisable and NOT simulatable.
//   The stub lets a Sky130-only build hand a real ring-oscillator implementation to the analog flow later.
//   That implementation does not exist yet. The analog deliverable is deferred out of Phase 6a.
// Ports (identical to trng_lfsr_entropy.sv):
//   load_i and seed_i start a session. A ring oscillator ignores the seed.
//   flush_i discards any partly assembled word, after a health failure.
//   run_i consumes one raw sample this clock. Low is a stall (backpressure, not a drop).
//   sample_valid_o and sample_o are the raw (pre-debias) stream for the repetition-count health test.
//   word_valid_o and word_o are the debiased 32-bit words.
//   word_valid_o is a combinational strobe in the clock that consumes the completing sample.
// Clocks and resets: clk and rst_n are ports of the contract. The stub has no behaviour.
// Caller rules:
//   - Never add this file to a file list. A flow that pulled it in would elaborate a peripheral without its entropy source.
//   - The file is in no file list, is not compiled in the default build and is not linted.
// Doc: ds:mod:trng-ro-sky130

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
