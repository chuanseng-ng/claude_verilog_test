// sha256_core - SHA-256 single-block compression core, one round per cycle.
//
// Function: The core computes h_o = H(block_i, h_i) for one 512-bit block. It takes 66 cycles per block.
//   The 66 cycles are 1 load, 64 rounds and 1 final add. The FSM states are S_IDLE, S_ROUND and S_FINAL.
//   The core has no APB, no sticky flag, no CDC and no notion of message length.
//   The K constants are a case function over 64 constant labels. The message schedule is a 16 x 32 shift register.
//   The core has no runtime-indexed mux.
// Ports:
//   start_i is a 1-cycle strobe. It is ignored unless the core is idle. The parent never asserts it while busy_o is 1.
//   block_i (512 bits) and h_i (256 bits) are sampled only on the accepted start edge. The core keeps h_i in hin_q.
//   busy_o is 1 when the state is not S_IDLE. done_set_o is a one-cycle combinational pulse in S_FINAL.
//   h_o is the combinational next chaining value. It is valid only in the done_set_o cycle.
//   wipe_i clears w_q, a_q..h_q, hin_q, t_q and state_q in one synchronous cycle.
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous. wipe_i has the same effect as !rst_n.
// Caller rules:
//   - Software does the padding, the length encoding and the multi-block loop (FIPS 180-4).
//   - Byte order is big-endian. W[j] is block_i bits [511-32j -: 32]. M0 is bits [511:480]. H0 is h_i bits [255:224].
//   - Do not fold the final adds onto the round-63 next state. The round path already carries two 32-bit adder chains.
//   - The core has no side-channel or fault-injection hardening and is not certified. See crypto_accel.
// Doc: ds:mod:sha256-core, tm:mod:sha256-core

module sha256_core (
    input  logic         clk,
    input  logic         rst_n,

    // wipe_i: 1-cycle synchronous clear of w_q, a_q..h_q, hin_q, t_q and state_q. It has the same effect as !rst_n.
    input  logic         wipe_i,

    input  logic         start_i,
    input  logic [511:0] block_i,
    input  logic [255:0] h_i,

    output logic         busy_o,
    output logic         done_set_o,
    output logic [255:0] h_o
);

    // Pure functions. Declare each function before use (yosys-slang strict mode).

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
        if (!rst_n || wipe_i) begin
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
