// trng_lfsr_entropy.sv
// Phase 6a-4 -- default (LFSR) entropy arm of the TRNG (bead claude_verilog_test-f7vs.8,
// docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6a-4 -- TRNG"). Selected by trng.sv unless
// TRNG_RO_SKY130 is defined. The bit-exact specification of everything in this file is
// tb/models/trng_lfsr_model.py; this RTL reproduces that model word for word.
//
// THIS IS NOT A SOURCE OF ENTROPY. It is a deterministic pseudo-random generator: every word it
// ever emits is a pure function of the 32-bit seed. trng.sv forces TRNG_STATUS.INSECURE = 1
// whenever this arm is compiled in, so software can tell it from real entropy.
//
// Pipeline (one raw sample per clock in which run_i is high):
//   1. load_i loads three Fibonacci LFSRs from seed_i by plain slicing -- lfsr31 = seed[30:0],
//      lfsr29 = seed[28:0], lfsr23 = seed[22:0]; seed bit 31 is unused. An all-zero slice is a
//      lock-up state and is deliberately NOT rescued (a dead source must be reported by the
//      health test in trng.sv, not silently replaced).
//   2. Register width n, tap t (1-based): out = state[n-1], fb = state[n-1] ^ state[t-1],
//      state <= {state[n-2:0], fb}. Polynomials x^31+x^28+1, x^29+x^27+1, x^23+x^18+1 -- taps
//      (31,28), (29,27), (23,18), all primitive, maximal length 2^n-1.
//   3. Raw sample = out31 ^ out29 ^ out23, taken from the CURRENT state (sample 0 is the freshly
//      loaded state, before any step); all three registers then step once.
//   4. Von Neumann debiaser over consecutive NON-overlapping raw pairs: 01 -> 0, 10 -> 1 (emit the
//      FIRST bit of the pair), 00 / 11 -> discard. ~75 % of raw samples are discarded.
//   5. Emitted bits pack LSB-first into a 32-bit word; the 32nd bit completes it. word_valid_o is
//      a COMBINATIONAL strobe in the clock the completing pair is consumed, so the consumer
//      registers the word on that same edge.
//   Backpressure is a STALL, not a drop: the consumer simply drops run_i. Nothing here ever
//   discards a sample for lack of room, which is what makes the word sequence a function of the
//   seed alone.
//
// Port contract shared with the ring-oscillator arm (trng_ro_sky130.sv): sample_valid_o/sample_o
// carry the RAW (pre-debias) stream to the health test in trng.sv; word_valid_o/word_o the
// debiased, assembled words. load_i also clears the debiaser/assembler; flush_i clears only the
// debiaser/assembler (used after a health failure, so bits from a failing source are never
// mixed into a later word). load_i and flush_i win over a same-cycle run_i.
//
// No CDC: single clock domain, no asynchronous inputs. Reset: synchronous active-low, matching
// the rest of rtl/periph/.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module trng_lfsr_entropy (
    input  logic        clk,
    input  logic        rst_n,

    input  logic        load_i,          // load LFSRs from seed_i, clear debiaser + assembler
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] seed_i,          // bit 31 is unused by design (see header)
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic        flush_i,         // clear debiaser + assembler only (LFSRs keep running)
    input  logic        run_i,           // consume one raw sample this clock

    output logic        sample_valid_o,  // a raw sample is consumed this clock
    output logic        sample_o,        // the raw (pre-debias) sample
    output logic        word_valid_o,    // a 32-bit word completes on this clock's edge
    output logic [31:0] word_o
);

    // =========================================================================
    // LFSR state
    // =========================================================================
    logic [30:0] lfsr31_q;
    logic [28:0] lfsr29_q;
    logic [22:0] lfsr23_q;

    // Feedback = MSB ^ tap bit (tap t is 1-based, so state index t-1).
    logic fb31_w, fb29_w, fb23_w;
    assign fb31_w = lfsr31_q[30] ^ lfsr31_q[27];   // taps (31, 28)
    assign fb29_w = lfsr29_q[28] ^ lfsr29_q[26];   // taps (29, 27)
    assign fb23_w = lfsr23_q[22] ^ lfsr23_q[17];   // taps (23, 18)

    assign sample_o       = lfsr31_q[30] ^ lfsr29_q[28] ^ lfsr23_q[22];
    assign sample_valid_o = run_i;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            lfsr31_q <= 31'h0;
            lfsr29_q <= 29'h0;
            lfsr23_q <= 23'h0;
        end else if (load_i) begin
            lfsr31_q <= seed_i[30:0];
            lfsr29_q <= seed_i[28:0];
            lfsr23_q <= seed_i[22:0];
        end else if (run_i) begin
            lfsr31_q <= {lfsr31_q[29:0], fb31_w};
            lfsr29_q <= {lfsr29_q[27:0], fb29_w};
            lfsr23_q <= {lfsr23_q[21:0], fb23_w};
        end
    end

    // =========================================================================
    // Von Neumann debiaser + LSB-first word assembler
    // =========================================================================
    logic        have_first_q;   // first bit of a raw pair is held in first_q
    logic        first_q;
    logic [30:0] acc_q;          // output bits 0..30 of the word under assembly
    logic [4:0]  cnt_q;          // output bits already in acc_q (0..31)

    logic        pair_done_w;    // this sample is the second of a pair
    logic        emit_w;         // ... and the pair survives (bits differ)
    assign pair_done_w = run_i & have_first_q;
    assign emit_w      = pair_done_w & (first_q ^ sample_o);

    // The emitted bit is the first bit of the pair. The 32nd emitted bit completes the word and
    // rides straight out on word_o[31] instead of being stored.
    assign word_valid_o = emit_w & (cnt_q == 5'd31);
    assign word_o       = {first_q, acc_q};

    always_ff @(posedge clk) begin
        if (!rst_n || load_i || flush_i) begin
            have_first_q <= 1'b0;
            first_q      <= 1'b0;
            acc_q        <= 31'h0;
            cnt_q        <= 5'd0;
        end else if (run_i) begin
            if (!have_first_q) begin
                have_first_q <= 1'b1;
                first_q      <= sample_o;
            end else begin
                have_first_q <= 1'b0;
                if (emit_w) begin
                    if (cnt_q == 5'd31) begin
                        acc_q <= 31'h0;
                        cnt_q <= 5'd0;
                    end else begin
                        for (int unsigned i = 0; i < 31; i++)
                            if (cnt_q == 5'(i)) acc_q[i] <= first_q;
                        cnt_q <= cnt_q + 5'd1;
                    end
                end
            end
        end
    end

endmodule : trng_lfsr_entropy
