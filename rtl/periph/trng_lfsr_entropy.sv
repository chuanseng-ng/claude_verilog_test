// trng_lfsr_entropy - default LFSR entropy arm of the TRNG.
//
// Function: trng.sv selects this arm unless TRNG_RO_SKY130 is defined.
//   The arm is a deterministic pseudo-random generator, NOT a source of entropy. Every word is a function of the seed.
//   trng.sv forces TRNG_STATUS.INSECURE = 1 whenever this arm is compiled in.
//   The arm takes one raw sample per clock in which run_i is high:
//   1. load_i loads three Fibonacci LFSRs from seed_i: lfsr31 = seed[30:0], lfsr29 = seed[28:0], lfsr23 = seed[22:0].
//      Seed bit 31 is unused. An all-zero slice locks up and is not rescued. The health test in trng.sv reports it.
//   2. For register width n and tap t (1-based): out = state[n-1], fb = state[n-1] ^ state[t-1],
//      state <= {state[n-2:0], fb}. The taps are (31,28), (29,27) and (23,18).
//   3. Raw sample = out31 ^ out29 ^ out23, from the current state. Sample 0 is the freshly loaded state.
//      All three registers then step once.
//   4. A von Neumann debiaser takes non-overlapping raw pairs: 01 gives 0, 10 gives 1, 00 and 11 are discarded.
//   5. Emitted bits pack LSB-first into a 32-bit word. word_valid_o is a combinational strobe in the clock
//      that consumes the completing pair.
// Ports:
//   load_i loads the LFSRs and clears the debiaser and assembler. flush_i clears only the debiaser and assembler.
//   load_i and flush_i win over a same-cycle run_i.
//   sample_valid_o and sample_o carry the raw (pre-debias) stream to the health test in trng.sv.
//   word_valid_o and word_o carry the debiased, assembled words.
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous. The arm has no CDC.
// Caller rules:
//   - Backpressure is a stall. Drop run_i. The arm never discards a sample for lack of room.
//   - The port contract is shared with trng_ro_sky130.sv.
// Doc: ds:mod:trng-lfsr-entropy, tm:mod:trng-lfsr-entropy

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
