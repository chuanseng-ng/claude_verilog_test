// sha256_core.sv
// Phase 6b -- SHA-256 single-block compression core, one round per cycle (bead
// claude_verilog_test-f7vs.10, docs/PHASE6_IP_EXPANSION_PLAN.md Sec.6b "6b -- CRYPTO"). Sub-core of
// crypto_accel.sv: no APB, no sticky flags, no clock-domain crossing. The parent owns the message
// shadow, the chaining register (the DIGEST bank words) and the sticky done flag.
//
// INSECURE-BY-SCOPE: no side-channel or DPA resistance, no fault-injection hardening, not
// certified, not validated against any scheme. SHA-256 here is unkeyed, but the full non-goals
// paragraph in crypto_accel.sv applies to this file unchanged.
//
// SCOPE. ONE 512-bit block compress: h_o = H(block_i, h_i). PADDING, LENGTH ENCODING AND
// MULTI-BLOCK ITERATION ARE SOFTWARE'S JOB (FIPS 180-4); the core has no notion of message
// length. h_i / h_o make it a pure function of (block, H), which is what makes chaining
// software's job.
//
// BYTE ORDER. FIPS 180-4 big-endian. block_i word j (W[j], j = 0..15) is bits [511-32j -: 32], so
// M0 is bits [511:480]; h_i / h_o carry {H0..H7} with H0 at [255:224].
//
// NO RUNTIME-INDEXED MUX (bead ma7 acceptance criterion; the proven Synlig OPT_MUXTREE miscompile).
//   * The K constants are `function sha_k` = `unique case (t)` over 64 CONSTANT labels returning
//     literals -- NOT `K_TABLE[t]`. A case over constants collapses to a 6-input constant
//     function per output bit; an indexed array read is the $pmux form that miscompiled in ma7.
//   * The message schedule is a 16 x 32 SHIFT REGISTER with constant taps only (below).
//   * Sigma/sigma are constant rotations and shifts, i.e. wiring.
//
// W ROLLING SCHEDULE. Window convention: at the start of round t, w_q[j] = W[t+j]; the round
// consumes w_q[0]. Every round cycle
//     w_q[j]  <= w_q[j+1]                                       j = 0..14
//     w_q[15] <= sigma1(w_q[14]) + w_q[9] + sigma0(w_q[1]) + w_q[0]
// which is exactly W[t+16] = s1(W[t+14]) + W[t+9] + s0(W[t+1]) + W[t]. W[16] is therefore produced
// during round 0. Rounds 48..63 compute words that are never consumed; they are left to run
// (gating them saves nothing and adds a condition).
//
// FSM / CYCLE COUNT. S_IDLE, S_ROUND, S_FINAL; t_q counts 0..63.
//   accepted start_i edge : w_q <= block_i, {a..h}_q <= h_i, hin_q <= h_i, t_q <= 0   (1 cycle)
//   S_ROUND               : 64 cycles, one round each
//   S_FINAL               : 1 cycle; h_o = hin_q + {a..h}_q (eight 32-bit adds), done_set_o = 1
//   TOTAL = 66 CYCLES/BLOCK (1 load + 64 rounds + 1 final add).
//   The 65-cycle variant -- folding the eight final adds onto the round-63 next-state -- is
//   REJECTED: the round path already carries Sigma0, Sigma1, Ch, Maj and two 32-bit adder chains,
//   and stacking another 32-bit add there is the one place in this peripheral that could move
//   Fmax. Do not "optimise" it in later.
//
// Port contract with crypto_accel.sv (the parent). Single clock (clk); no CDC in this module.
//   start_i       1-cycle strobe. Ignored (silently) unless idle; the parent never asserts it
//                 while busy_o.
//   block_i       512-bit message block; sampled ONLY on the accepted start edge.
//   h_i           256-bit chaining value in; sampled ONLY on the accepted start edge (the core
//                 keeps its own copy in hin_q for the final feed-forward add).
//   busy_o        state != S_IDLE (flop output).
//   done_set_o    one-cycle COMBINATIONAL pulse asserted in S_FINAL. The parent owns the sticky
//                 flop and the W1C.
//   h_o           COMBINATIONAL next chaining value; valid ONLY in the done_set_o cycle, so the
//                 parent can hw_wen the DIGEST bank words on the same edge with no result register.
//
// Reset: synchronous, active-low (always_ff @(posedge clk) + if (!rst_n)), matching rtl/periph/.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module sha256_core (
    input  logic         clk,
    input  logic         rst_n,

    input  logic         start_i,
    input  logic [511:0] block_i,
    input  logic [255:0] h_i,

    output logic         busy_o,
    output logic         done_set_o,
    output logic [255:0] h_o
);

    // =========================================================================
    // Pure functions (declaration before use: yosys-slang strict mode, bead q7n)
    // =========================================================================

    // FIPS 180-4 Sec.4.2.2 round constants: 64 CONSTANT case labels, never an indexed array read.
    function automatic logic [31:0] sha_k(input logic [5:0] t);
        unique case (t)
            6'd0: sha_k = 32'h428a2f98;
            6'd1: sha_k = 32'h71374491;
            6'd2: sha_k = 32'hb5c0fbcf;
            6'd3: sha_k = 32'he9b5dba5;
            6'd4: sha_k = 32'h3956c25b;
            6'd5: sha_k = 32'h59f111f1;
            6'd6: sha_k = 32'h923f82a4;
            6'd7: sha_k = 32'hab1c5ed5;
            6'd8: sha_k = 32'hd807aa98;
            6'd9: sha_k = 32'h12835b01;
            6'd10: sha_k = 32'h243185be;
            6'd11: sha_k = 32'h550c7dc3;
            6'd12: sha_k = 32'h72be5d74;
            6'd13: sha_k = 32'h80deb1fe;
            6'd14: sha_k = 32'h9bdc06a7;
            6'd15: sha_k = 32'hc19bf174;
            6'd16: sha_k = 32'he49b69c1;
            6'd17: sha_k = 32'hefbe4786;
            6'd18: sha_k = 32'h0fc19dc6;
            6'd19: sha_k = 32'h240ca1cc;
            6'd20: sha_k = 32'h2de92c6f;
            6'd21: sha_k = 32'h4a7484aa;
            6'd22: sha_k = 32'h5cb0a9dc;
            6'd23: sha_k = 32'h76f988da;
            6'd24: sha_k = 32'h983e5152;
            6'd25: sha_k = 32'ha831c66d;
            6'd26: sha_k = 32'hb00327c8;
            6'd27: sha_k = 32'hbf597fc7;
            6'd28: sha_k = 32'hc6e00bf3;
            6'd29: sha_k = 32'hd5a79147;
            6'd30: sha_k = 32'h06ca6351;
            6'd31: sha_k = 32'h14292967;
            6'd32: sha_k = 32'h27b70a85;
            6'd33: sha_k = 32'h2e1b2138;
            6'd34: sha_k = 32'h4d2c6dfc;
            6'd35: sha_k = 32'h53380d13;
            6'd36: sha_k = 32'h650a7354;
            6'd37: sha_k = 32'h766a0abb;
            6'd38: sha_k = 32'h81c2c92e;
            6'd39: sha_k = 32'h92722c85;
            6'd40: sha_k = 32'ha2bfe8a1;
            6'd41: sha_k = 32'ha81a664b;
            6'd42: sha_k = 32'hc24b8b70;
            6'd43: sha_k = 32'hc76c51a3;
            6'd44: sha_k = 32'hd192e819;
            6'd45: sha_k = 32'hd6990624;
            6'd46: sha_k = 32'hf40e3585;
            6'd47: sha_k = 32'h106aa070;
            6'd48: sha_k = 32'h19a4c116;
            6'd49: sha_k = 32'h1e376c08;
            6'd50: sha_k = 32'h2748774c;
            6'd51: sha_k = 32'h34b0bcb5;
            6'd52: sha_k = 32'h391c0cb3;
            6'd53: sha_k = 32'h4ed8aa4a;
            6'd54: sha_k = 32'h5b9cca4f;
            6'd55: sha_k = 32'h682e6ff3;
            6'd56: sha_k = 32'h748f82ee;
            6'd57: sha_k = 32'h78a5636f;
            6'd58: sha_k = 32'h84c87814;
            6'd59: sha_k = 32'h8cc70208;
            6'd60: sha_k = 32'h90befffa;
            6'd61: sha_k = 32'ha4506ceb;
            6'd62: sha_k = 32'hbef9a3f7;
            6'd63: sha_k = 32'hc67178f2;
            default: sha_k = 32'h0000_0000;
        endcase
    endfunction

    function automatic logic [31:0] big_sigma0(input logic [31:0] x);   // ror2 ^ ror13 ^ ror22
        big_sigma0 = {x[1:0], x[31:2]} ^ {x[12:0], x[31:13]} ^ {x[21:0], x[31:22]};
    endfunction

    function automatic logic [31:0] big_sigma1(input logic [31:0] x);   // ror6 ^ ror11 ^ ror25
        big_sigma1 = {x[5:0], x[31:6]} ^ {x[10:0], x[31:11]} ^ {x[24:0], x[31:25]};
    endfunction

    function automatic logic [31:0] small_sigma0(input logic [31:0] x); // ror7 ^ ror18 ^ shr3
        small_sigma0 = {x[6:0], x[31:7]} ^ {x[17:0], x[31:18]} ^ {3'b000, x[31:3]};
    endfunction

    function automatic logic [31:0] small_sigma1(input logic [31:0] x); // ror17 ^ ror19 ^ shr10
        small_sigma1 = {x[16:0], x[31:17]} ^ {x[18:0], x[31:19]} ^ {10'h000, x[31:10]};
    endfunction

    function automatic logic [31:0] ch(input logic [31:0] e, input logic [31:0] f,
                                       input logic [31:0] g);
        ch = (e & f) ^ (~e & g);
    endfunction

    function automatic logic [31:0] maj(input logic [31:0] a, input logic [31:0] b,
                                        input logic [31:0] c);
        maj = (a & b) ^ (a & c) ^ (b & c);
    endfunction

    // =========================================================================
    // State
    // =========================================================================
    typedef enum logic [1:0] {
        S_IDLE  = 2'd0,
        S_ROUND = 2'd1,
        S_FINAL = 2'd2
    } sha_state_e;

    sha_state_e   state_q;
    logic [6:0]   t_q;                  // round counter 0..63
    logic [31:0]  w_q [16];             // rolling schedule window, w_q[j] = W[t+j]
    logic [31:0]  a_q, b_q, c_q, d_q, e_q, f_q, g_q, h_q;
    logic [255:0] hin_q;                // chaining value captured at start

    logic [31:0]  t1_w, t2_w, w_new_w;

    assign t1_w    = h_q + big_sigma1(e_q) + ch(e_q, f_q, g_q) + sha_k(t_q[5:0]) + w_q[0];
    assign t2_w    = big_sigma0(a_q) + maj(a_q, b_q, c_q);
    assign w_new_w = small_sigma1(w_q[14]) + w_q[9] + small_sigma0(w_q[1]) + w_q[0];

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q <= S_IDLE;
            t_q     <= 7'd0;
            hin_q   <= 256'h0;
            a_q     <= 32'h0;
            b_q     <= 32'h0;
            c_q     <= 32'h0;
            d_q     <= 32'h0;
            e_q     <= 32'h0;
            f_q     <= 32'h0;
            g_q     <= 32'h0;
            h_q     <= 32'h0;
            for (int unsigned j = 0; j < 16; j++) w_q[j] <= 32'h0;
        end else begin
            unique case (state_q)
                S_IDLE: begin
                    if (start_i) begin
                        for (int unsigned j = 0; j < 16; j++) w_q[j] <= block_i[32*(15-j) +: 32];
                        a_q     <= h_i[255:224];
                        b_q     <= h_i[223:192];
                        c_q     <= h_i[191:160];
                        d_q     <= h_i[159:128];
                        e_q     <= h_i[127:96];
                        f_q     <= h_i[95:64];
                        g_q     <= h_i[63:32];
                        h_q     <= h_i[31:0];
                        hin_q   <= h_i;
                        t_q     <= 7'd0;
                        state_q <= S_ROUND;
                    end
                end
                S_ROUND: begin
                    for (int unsigned j = 0; j < 15; j++) w_q[j] <= w_q[j+1];
                    w_q[15] <= w_new_w;
                    h_q     <= g_q;
                    g_q     <= f_q;
                    f_q     <= e_q;
                    e_q     <= d_q + t1_w;
                    d_q     <= c_q;
                    c_q     <= b_q;
                    b_q     <= a_q;
                    a_q     <= t1_w + t2_w;
                    t_q     <= t_q + 7'd1;
                    if (t_q == 7'd63) state_q <= S_FINAL;
                end
                S_FINAL: state_q <= S_IDLE;
                default: state_q <= S_IDLE;
            endcase
        end
    end

    assign busy_o     = (state_q != S_IDLE);
    assign done_set_o = (state_q == S_FINAL);

    // Feed-forward add. Eight 32-bit adds, H0 at [255:224].
    assign h_o = {hin_q[255:224] + a_q, hin_q[223:192] + b_q, hin_q[191:160] + c_q,
                  hin_q[159:128] + d_q, hin_q[127:96]  + e_q, hin_q[95:64]   + f_q,
                  hin_q[63:32]   + g_q, hin_q[31:0]    + h_q};

endmodule : sha256_core
