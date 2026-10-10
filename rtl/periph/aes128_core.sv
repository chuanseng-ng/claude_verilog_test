// aes128_core.sv
// Phase 6b -- AES-128 encrypt-only block core, iterative 128-bit datapath (bead
// claude_verilog_test-f7vs.10, docs/PHASE6_IP_EXPANSION_PLAN.md Sec.6b "6b -- CRYPTO"). Sub-core of
// crypto_accel.sv: it has no APB, no register storage visible to software and no clock-domain
// crossing. The parent owns the key shadow, the message shadow, the sticky done flag and the
// result register (the register bank word IS the result register).
//
// INSECURE-BY-SCOPE: no side-channel or DPA resistance (the S-box is a data-dependent case
// network), no fault-injection hardening, not certified, not validated against any scheme. The
// full non-goals paragraph is in crypto_accel.sv; it applies to this file unchanged.
//
// BYTE ORDER. FIPS-197 big-endian throughout: for a 128-bit block B[0..15], byte B0 is bits
// [127:120] and B15 is bits [7:0]. The state is column-major, so s[127:96] is column 0 (bytes 0..3).
// Encrypt-only: CTR mode makes this a complete cipher in both directions (S ^ (S ^ P) = P), so no
// inverse S-box and no inverse key schedule exist anywhere.
//
// NO RUNTIME-INDEXED MUX (bead ma7 acceptance criterion; the proven Synlig OPT_MUXTREE miscompile).
//   * The S-box is `function sbox` = `unique case (b)` over 256 CONSTANT labels returning
//     literals -- NOT an indexed read of a 256-entry localparam array.
//   * The round constant is `rcon_q <= xtime(rcon_q)`, reset 8'h01, advanced once per round: no
//     table and no select.
//   * ShiftRows is fixed wiring; MixColumns and SubBytes use constant slices only; the one
//     select left in the datapath is the 1-bit mix_en 2:1 (round 10 skips MixColumns).
//
// KEY SCHEDULE: ON-THE-FLY. rk_q is ONE 128-bit register holding the current round key, advanced
// once per round: w0' = w0 ^ SubWord(RotWord(w3)) ^ {rcon,24'h0}, w1' = w0'^w1, w2' = w1'^w2,
// w3' = w2'^w3. Precomputed-and-stored (11 round keys = 1408 flops) is FORBIDDEN here twice over:
// the flop count, and because fetching round key r is exactly the forbidden runtime-indexed read.
//
// MIXCOLUMNS per column a0..a3, t = a0^a1^a2^a3: b_i = a_i ^ t ^ xtime(a_i ^ a_(i+1 mod 4)).
// Identity: a0 ^ t ^ xtime(a0^a1) = 2a0 ^ 3a1 ^ a2 ^ a3. 4 xtimes per column (16 total) against 8 for
// the naive 2a_i ^ 3a_(i+1) ^ a_(i+2) ^ a_(i+3) expansion.
//
// SBOX_PARALLEL (16 or 4; any other value is a g_sbox_parallel_check elaboration $fatal).
//   Physical S-box count = CALL-SITE count of the pure function sbox().
//   16: 16 datapath + 4 key-schedule SubWord = 20 S-boxes; 1 whitening cycle + 10 round cycles =
//       11 CYCLES/BLOCK (start edge to completion edge). The key schedule's 4 cannot be folded into
//       the datapath's 16: both are consumed the same cycle from different operands, so sharing
//       would need a select -- the forbidden construct.
//    4: 4 datapath + 4 key-schedule = 8 S-boxes; 1 + 10*4 = 41 CYCLES/BLOCK. The datapath folds by
//       a byte-lane CAROUSEL, not a case(phase): phases 0..2 rotate s_q right by 32 through the
//       fixed window s_q[31:0] -> sbox4 -> top word; phase 3 does the same rotate and applies the
//       round tail (ShiftRows, MixColumns when mix_en, AddRoundKey). Trace with s = {w3,w2,w1,w0}:
//       {S(w0),w3,w2,w1} -> {S(w1),S(w0),w3,w2} -> {S(w2),S(w1),S(w0),w3} -> {S(w3),...,S(w0)}.
//       The only select in the fold is the phase_q==3 2:1 on whether to apply the round tail.
//       The key schedule's 4 S-boxes are live in 1 phase of 4 (rk_q only commits on phase 3);
//       they are deliberately NOT time-shared with the datapath's 4 -- that needs a 2:1 operand
//       mux and a fifth phase (51 cycles/block). A parameter change, not a redesign.
//
// Port contract with crypto_accel.sv (the parent). Single clock (clk); no CDC in this module.
//   start_i       1-cycle strobe. Ignored (silently) unless the core is idle; the parent never
//                 asserts it while busy_o.
//   key_i         128-bit AES key; the value present on the accepted start edge is the one used
//                 (the datapath pre-loads from it every idle cycle, see the A_IDLE branch, but only
//                 the start-edge sample is ever consumed). The on-the-fly
//                 schedule does NOT need key_i held during the operation. The parent's busy-time
//                 key-write rejection is a spec/determinism requirement, not a datapath one: do
//                 not "optimise" it away as redundant, and do not add a key hold register here.
//   block_i       128-bit plaintext (ECB) or counter block (CTR); the value present on the
//                 accepted start edge is the one used (pre-loaded every idle cycle, as key_i).
//   busy_o        state != A_IDLE (flop output).
//   done_set_o    one-cycle COMBINATIONAL pulse asserted in the final round cycle (round 10, and
//                 phase 3 at SBOX_PARALLEL=4). The parent owns the sticky flop and the W1C.
//   dout_o        COMBINATIONAL next-state ciphertext; valid ONLY in the done_set_o cycle. It
//                 exists so the parent can hw_wen the register bank on the same edge the last
//                 round lands -- zero extra 128-bit result register.
//
// Fmax note: SBOX_PARALLEL=16 critical path is S-box -> ShiftRows wiring -> 2 XOR levels of
// MixColumns -> AddRoundKey in one cycle; comfortable at 40 MHz Sky130. AREA (20 x 256x8) is the
// Gate A question, not the period.
//
// Reset: synchronous, active-low (always_ff @(posedge clk) + if (!rst_n)), matching rtl/periph/.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module aes128_core
#(
    parameter int unsigned SBOX_PARALLEL = 16   // 16 or 4 only; see g_sbox_parallel_check
) (
    input  logic         clk,
    input  logic         rst_n,

    // DFT scan mode (bead j41m.2): 1 forces the rk_q READ net to 0 (rk_q is excluded from scan and
    // inverts to the master key, so it must not reach any scanned flop through capture).
    input  logic         scan_mode_i,

    input  logic         start_i,
    input  logic [127:0] key_i,
    input  logic [127:0] block_i,

    output logic         busy_o,
    output logic         done_set_o,
    output logic [127:0] dout_o
);

    // Elaboration guard: a generate-scope $fatal (not wrapped in `initial`) fires at ELABORATION
    // time, under `verilator --lint-only` too (same idiom as i2c_controller.sv's g_addr_w_check).
    if (SBOX_PARALLEL != 16 && SBOX_PARALLEL != 4) begin : g_sbox_parallel_check
        $fatal(1, "aes128_core: SBOX_PARALLEL (%0d) must be 16 or 4", SBOX_PARALLEL);
    end

    localparam int unsigned LAST_ROUND = 10;

    // =========================================================================
    // Pure functions (declaration before use: yosys-slang strict mode, bead q7n)
    // =========================================================================

    // AES S-box: 256 CONSTANT case labels, never an indexed array read (bead ma7).
    function automatic logic [7:0] sbox(input logic [7:0] b);
        unique case (b)
            8'h00: sbox = 8'h63;
            8'h01: sbox = 8'h7c;
            8'h02: sbox = 8'h77;
            8'h03: sbox = 8'h7b;
            8'h04: sbox = 8'hf2;
            8'h05: sbox = 8'h6b;
            8'h06: sbox = 8'h6f;
            8'h07: sbox = 8'hc5;
            8'h08: sbox = 8'h30;
            8'h09: sbox = 8'h01;
            8'h0a: sbox = 8'h67;
            8'h0b: sbox = 8'h2b;
            8'h0c: sbox = 8'hfe;
            8'h0d: sbox = 8'hd7;
            8'h0e: sbox = 8'hab;
            8'h0f: sbox = 8'h76;
            8'h10: sbox = 8'hca;
            8'h11: sbox = 8'h82;
            8'h12: sbox = 8'hc9;
            8'h13: sbox = 8'h7d;
            8'h14: sbox = 8'hfa;
            8'h15: sbox = 8'h59;
            8'h16: sbox = 8'h47;
            8'h17: sbox = 8'hf0;
            8'h18: sbox = 8'had;
            8'h19: sbox = 8'hd4;
            8'h1a: sbox = 8'ha2;
            8'h1b: sbox = 8'haf;
            8'h1c: sbox = 8'h9c;
            8'h1d: sbox = 8'ha4;
            8'h1e: sbox = 8'h72;
            8'h1f: sbox = 8'hc0;
            8'h20: sbox = 8'hb7;
            8'h21: sbox = 8'hfd;
            8'h22: sbox = 8'h93;
            8'h23: sbox = 8'h26;
            8'h24: sbox = 8'h36;
            8'h25: sbox = 8'h3f;
            8'h26: sbox = 8'hf7;
            8'h27: sbox = 8'hcc;
            8'h28: sbox = 8'h34;
            8'h29: sbox = 8'ha5;
            8'h2a: sbox = 8'he5;
            8'h2b: sbox = 8'hf1;
            8'h2c: sbox = 8'h71;
            8'h2d: sbox = 8'hd8;
            8'h2e: sbox = 8'h31;
            8'h2f: sbox = 8'h15;
            8'h30: sbox = 8'h04;
            8'h31: sbox = 8'hc7;
            8'h32: sbox = 8'h23;
            8'h33: sbox = 8'hc3;
            8'h34: sbox = 8'h18;
            8'h35: sbox = 8'h96;
            8'h36: sbox = 8'h05;
            8'h37: sbox = 8'h9a;
            8'h38: sbox = 8'h07;
            8'h39: sbox = 8'h12;
            8'h3a: sbox = 8'h80;
            8'h3b: sbox = 8'he2;
            8'h3c: sbox = 8'heb;
            8'h3d: sbox = 8'h27;
            8'h3e: sbox = 8'hb2;
            8'h3f: sbox = 8'h75;
            8'h40: sbox = 8'h09;
            8'h41: sbox = 8'h83;
            8'h42: sbox = 8'h2c;
            8'h43: sbox = 8'h1a;
            8'h44: sbox = 8'h1b;
            8'h45: sbox = 8'h6e;
            8'h46: sbox = 8'h5a;
            8'h47: sbox = 8'ha0;
            8'h48: sbox = 8'h52;
            8'h49: sbox = 8'h3b;
            8'h4a: sbox = 8'hd6;
            8'h4b: sbox = 8'hb3;
            8'h4c: sbox = 8'h29;
            8'h4d: sbox = 8'he3;
            8'h4e: sbox = 8'h2f;
            8'h4f: sbox = 8'h84;
            8'h50: sbox = 8'h53;
            8'h51: sbox = 8'hd1;
            8'h52: sbox = 8'h00;
            8'h53: sbox = 8'hed;
            8'h54: sbox = 8'h20;
            8'h55: sbox = 8'hfc;
            8'h56: sbox = 8'hb1;
            8'h57: sbox = 8'h5b;
            8'h58: sbox = 8'h6a;
            8'h59: sbox = 8'hcb;
            8'h5a: sbox = 8'hbe;
            8'h5b: sbox = 8'h39;
            8'h5c: sbox = 8'h4a;
            8'h5d: sbox = 8'h4c;
            8'h5e: sbox = 8'h58;
            8'h5f: sbox = 8'hcf;
            8'h60: sbox = 8'hd0;
            8'h61: sbox = 8'hef;
            8'h62: sbox = 8'haa;
            8'h63: sbox = 8'hfb;
            8'h64: sbox = 8'h43;
            8'h65: sbox = 8'h4d;
            8'h66: sbox = 8'h33;
            8'h67: sbox = 8'h85;
            8'h68: sbox = 8'h45;
            8'h69: sbox = 8'hf9;
            8'h6a: sbox = 8'h02;
            8'h6b: sbox = 8'h7f;
            8'h6c: sbox = 8'h50;
            8'h6d: sbox = 8'h3c;
            8'h6e: sbox = 8'h9f;
            8'h6f: sbox = 8'ha8;
            8'h70: sbox = 8'h51;
            8'h71: sbox = 8'ha3;
            8'h72: sbox = 8'h40;
            8'h73: sbox = 8'h8f;
            8'h74: sbox = 8'h92;
            8'h75: sbox = 8'h9d;
            8'h76: sbox = 8'h38;
            8'h77: sbox = 8'hf5;
            8'h78: sbox = 8'hbc;
            8'h79: sbox = 8'hb6;
            8'h7a: sbox = 8'hda;
            8'h7b: sbox = 8'h21;
            8'h7c: sbox = 8'h10;
            8'h7d: sbox = 8'hff;
            8'h7e: sbox = 8'hf3;
            8'h7f: sbox = 8'hd2;
            8'h80: sbox = 8'hcd;
            8'h81: sbox = 8'h0c;
            8'h82: sbox = 8'h13;
            8'h83: sbox = 8'hec;
            8'h84: sbox = 8'h5f;
            8'h85: sbox = 8'h97;
            8'h86: sbox = 8'h44;
            8'h87: sbox = 8'h17;
            8'h88: sbox = 8'hc4;
            8'h89: sbox = 8'ha7;
            8'h8a: sbox = 8'h7e;
            8'h8b: sbox = 8'h3d;
            8'h8c: sbox = 8'h64;
            8'h8d: sbox = 8'h5d;
            8'h8e: sbox = 8'h19;
            8'h8f: sbox = 8'h73;
            8'h90: sbox = 8'h60;
            8'h91: sbox = 8'h81;
            8'h92: sbox = 8'h4f;
            8'h93: sbox = 8'hdc;
            8'h94: sbox = 8'h22;
            8'h95: sbox = 8'h2a;
            8'h96: sbox = 8'h90;
            8'h97: sbox = 8'h88;
            8'h98: sbox = 8'h46;
            8'h99: sbox = 8'hee;
            8'h9a: sbox = 8'hb8;
            8'h9b: sbox = 8'h14;
            8'h9c: sbox = 8'hde;
            8'h9d: sbox = 8'h5e;
            8'h9e: sbox = 8'h0b;
            8'h9f: sbox = 8'hdb;
            8'ha0: sbox = 8'he0;
            8'ha1: sbox = 8'h32;
            8'ha2: sbox = 8'h3a;
            8'ha3: sbox = 8'h0a;
            8'ha4: sbox = 8'h49;
            8'ha5: sbox = 8'h06;
            8'ha6: sbox = 8'h24;
            8'ha7: sbox = 8'h5c;
            8'ha8: sbox = 8'hc2;
            8'ha9: sbox = 8'hd3;
            8'haa: sbox = 8'hac;
            8'hab: sbox = 8'h62;
            8'hac: sbox = 8'h91;
            8'had: sbox = 8'h95;
            8'hae: sbox = 8'he4;
            8'haf: sbox = 8'h79;
            8'hb0: sbox = 8'he7;
            8'hb1: sbox = 8'hc8;
            8'hb2: sbox = 8'h37;
            8'hb3: sbox = 8'h6d;
            8'hb4: sbox = 8'h8d;
            8'hb5: sbox = 8'hd5;
            8'hb6: sbox = 8'h4e;
            8'hb7: sbox = 8'ha9;
            8'hb8: sbox = 8'h6c;
            8'hb9: sbox = 8'h56;
            8'hba: sbox = 8'hf4;
            8'hbb: sbox = 8'hea;
            8'hbc: sbox = 8'h65;
            8'hbd: sbox = 8'h7a;
            8'hbe: sbox = 8'hae;
            8'hbf: sbox = 8'h08;
            8'hc0: sbox = 8'hba;
            8'hc1: sbox = 8'h78;
            8'hc2: sbox = 8'h25;
            8'hc3: sbox = 8'h2e;
            8'hc4: sbox = 8'h1c;
            8'hc5: sbox = 8'ha6;
            8'hc6: sbox = 8'hb4;
            8'hc7: sbox = 8'hc6;
            8'hc8: sbox = 8'he8;
            8'hc9: sbox = 8'hdd;
            8'hca: sbox = 8'h74;
            8'hcb: sbox = 8'h1f;
            8'hcc: sbox = 8'h4b;
            8'hcd: sbox = 8'hbd;
            8'hce: sbox = 8'h8b;
            8'hcf: sbox = 8'h8a;
            8'hd0: sbox = 8'h70;
            8'hd1: sbox = 8'h3e;
            8'hd2: sbox = 8'hb5;
            8'hd3: sbox = 8'h66;
            8'hd4: sbox = 8'h48;
            8'hd5: sbox = 8'h03;
            8'hd6: sbox = 8'hf6;
            8'hd7: sbox = 8'h0e;
            8'hd8: sbox = 8'h61;
            8'hd9: sbox = 8'h35;
            8'hda: sbox = 8'h57;
            8'hdb: sbox = 8'hb9;
            8'hdc: sbox = 8'h86;
            8'hdd: sbox = 8'hc1;
            8'hde: sbox = 8'h1d;
            8'hdf: sbox = 8'h9e;
            8'he0: sbox = 8'he1;
            8'he1: sbox = 8'hf8;
            8'he2: sbox = 8'h98;
            8'he3: sbox = 8'h11;
            8'he4: sbox = 8'h69;
            8'he5: sbox = 8'hd9;
            8'he6: sbox = 8'h8e;
            8'he7: sbox = 8'h94;
            8'he8: sbox = 8'h9b;
            8'he9: sbox = 8'h1e;
            8'hea: sbox = 8'h87;
            8'heb: sbox = 8'he9;
            8'hec: sbox = 8'hce;
            8'hed: sbox = 8'h55;
            8'hee: sbox = 8'h28;
            8'hef: sbox = 8'hdf;
            8'hf0: sbox = 8'h8c;
            8'hf1: sbox = 8'ha1;
            8'hf2: sbox = 8'h89;
            8'hf3: sbox = 8'h0d;
            8'hf4: sbox = 8'hbf;
            8'hf5: sbox = 8'he6;
            8'hf6: sbox = 8'h42;
            8'hf7: sbox = 8'h68;
            8'hf8: sbox = 8'h41;
            8'hf9: sbox = 8'h99;
            8'hfa: sbox = 8'h2d;
            8'hfb: sbox = 8'h0f;
            8'hfc: sbox = 8'hb0;
            8'hfd: sbox = 8'h54;
            8'hfe: sbox = 8'hbb;
            8'hff: sbox = 8'h16;
            default: sbox = 8'h00;
        endcase
    endfunction

    function automatic logic [7:0] xtime(input logic [7:0] b);
        xtime = {b[6:0], 1'b0} ^ (b[7] ? 8'h1B : 8'h00);
    endfunction

    function automatic logic [31:0] sub_word(input logic [31:0] w);
        sub_word = {sbox(w[31:24]), sbox(w[23:16]), sbox(w[15:8]), sbox(w[7:0])};
    endfunction

    // Constant-bound unrolled loop (the bank's own strb_expand idiom): 16 sbox() call sites.
    function automatic logic [127:0] sub_bytes(input logic [127:0] x);
        for (int unsigned i = 0; i < 16; i++)
            sub_bytes[8*i +: 8] = sbox(x[8*i +: 8]);
    endfunction

    // ShiftRows: fixed rewiring of the column-major vector. New byte n = 4c+r takes old byte
    // 4*((c+r) mod 4)+r; byte k lives at bits [127-8k -: 8].
    function automatic logic [127:0] shift_rows(input logic [127:0] x);
        shift_rows = {x[127:120], x[87:80],  x[47:40],  x[7:0],     // new bytes  0.. 3 <- 0, 5,10,15
                      x[95:88],   x[55:48],  x[15:8],   x[103:96],  // new bytes  4.. 7 <- 4, 9,14, 3
                      x[63:56],   x[23:16],  x[111:104], x[71:64],  // new bytes  8..11 <- 8,13, 2, 7
                      x[31:24],   x[119:112], x[79:72], x[39:32]};  // new bytes 12..15 <- 12, 1, 6,11
    endfunction

    function automatic logic [31:0] mix_col(input logic [31:0] c);
        logic [7:0] a0, a1, a2, a3, t;
        a0 = c[31:24];
        a1 = c[23:16];
        a2 = c[15:8];
        a3 = c[7:0];
        t  = a0 ^ a1 ^ a2 ^ a3;
        mix_col = {a0 ^ t ^ xtime(a0 ^ a1),
                   a1 ^ t ^ xtime(a1 ^ a2),
                   a2 ^ t ^ xtime(a2 ^ a3),
                   a3 ^ t ^ xtime(a3 ^ a0)};
    endfunction

    function automatic logic [127:0] mix_columns(input logic [127:0] x);
        mix_columns = {mix_col(x[127:96]), mix_col(x[95:64]), mix_col(x[63:32]), mix_col(x[31:0])};
    endfunction

    // Round tail on an already-SubBytes'd state: ShiftRows -> MixColumns (skipped in round 10 by
    // ONE mix_en select, not a separate final-round datapath) -> AddRoundKey.
    function automatic logic [127:0] round_tail(input logic [127:0] sub, input logic [127:0] rk,
                                                input logic mix_en);
        logic [127:0] sr;
        sr = shift_rows(sub);
        round_tail = (mix_en ? mix_columns(sr) : sr) ^ rk;
    endfunction

    // One step of the on-the-fly key schedule.
    function automatic logic [127:0] key_step(input logic [127:0] rk, input logic [7:0] rcon);
        logic [31:0] w0, w1, w2, w3, n0, n1, n2, n3;
        w0 = rk[127:96];
        w1 = rk[95:64];
        w2 = rk[63:32];
        w3 = rk[31:0];
        n0 = w0 ^ sub_word({w3[23:0], w3[31:24]}) ^ {rcon, 24'h0};
        n1 = n0 ^ w1;
        n2 = n1 ^ w2;
        n3 = n2 ^ w3;
        key_step = {n0, n1, n2, n3};
    endfunction

    // =========================================================================
    // State
    // =========================================================================
    typedef enum logic {
        A_IDLE  = 1'b0,
        A_ROUND = 1'b1
    } aes_state_e;

    aes_state_e   state_q;
    logic [3:0]   round_q;       // 1..10
    logic [7:0]   rcon_q;        // 8'h01 at round 1, xtime() per round
    logic [127:0] s_q;           // AES state
    logic [127:0] rk_q;          // current round key (on-the-fly schedule); excluded from scan
    logic [127:0] rk_eff_w;      // rk_q as read by the datapath: 0 in scan mode (DFT key mask)

    logic [127:0] rk_next_w;     // round key for the round in flight
    logic         mix_en_w;      // 0 in the final round
    logic         rnd_end_w;     // the round in flight completes this cycle
    logic [127:0] s_adv_w;       // next s_q while in A_ROUND
    logic [127:0] tail_w;        // round_tail result: the ciphertext in the final round

    // rk_q has exactly one reader: key_step. Masking here covers every use of it.
    assign rk_eff_w  = rk_q & {128{~scan_mode_i}};
    assign rk_next_w = key_step(rk_eff_w, rcon_q);
    assign mix_en_w  = (round_q != 4'(LAST_ROUND));

    // =========================================================================
    // Datapath arms
    // =========================================================================
    if (SBOX_PARALLEL == 16) begin : g_sbox16
        // One round per cycle: SubBytes on all 16 bytes, then the round tail.
        assign rnd_end_w = 1'b1;
        assign tail_w    = round_tail(sub_bytes(s_q), rk_next_w, mix_en_w);
        assign s_adv_w   = tail_w;
    end else begin : g_sbox4
        // Four cycles per round: rotate through a fixed 32-bit substitution window (no select on
        // which byte group is substituted), apply the round tail on phase 3.
        logic [1:0]   phase_q;
        logic [127:0] rot_w;

        assign rot_w     = {sub_word(s_q[31:0]), s_q[127:32]};
        assign rnd_end_w = (phase_q == 2'd3);
        assign tail_w    = round_tail(rot_w, rk_next_w, mix_en_w);
        assign s_adv_w   = rnd_end_w ? tail_w : rot_w;

        always_ff @(posedge clk) begin
            if (!rst_n || state_q == A_IDLE) phase_q <= 2'd0;
            else                             phase_q <= phase_q + 2'd1;
        end
    end

    // =========================================================================
    // FSM / registers
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q <= A_IDLE;
            round_q <= 4'd0;
            rcon_q  <= 8'h01;
            s_q     <= 128'h0;
            rk_q    <= 128'h0;
        end else if (state_q == A_IDLE) begin
            // PRE-LOAD WHILE IDLE (bead f7vs.15, Gate B). The whitening value and the round-1
            // key/counters are loaded on EVERY idle cycle; start_i only advances state_q. The
            // values captured on the start edge are exactly the ones the old `if (start_i)` load
            // captured (same block_i ^ key_i, key_i, 8'h01, 4'd1 sampled at that same edge), so the
            // cycle count and every result are unchanged: 11 / 41 clk from the start edge. What
            // changes is the cone: start_i is the APB decode (paddr -> start_pulse_w) and used to
            // gate the D-input of all 128 + 128 + 8 + 4 datapath flops, and yosys' sbox ROM
            // inference (proc_rom + memory_dff) merged the S-box address flops, so that decode
            // also sat in front of an 8-bit S-box network. Now it fans out to state_q only.
            // None of s_q/rk_q/rcon_q/round_q is observable while idle (busy_o, done_set_o need
            // state_q == A_ROUND; dout_o is consumed only with done_set_o), and they hold no secret
            // that block_i/key_i do not already hold in the parent's msg_q/key_q.
            s_q     <= block_i ^ key_i;    // initial AddRoundKey (whitening)
            rk_q    <= key_i;
            rcon_q  <= 8'h01;
            round_q <= 4'd1;
            if (start_i) state_q <= A_ROUND;
        end else begin
            s_q <= s_adv_w;
            if (rnd_end_w) begin
                rk_q    <= rk_next_w;
                rcon_q  <= xtime(rcon_q);
                round_q <= round_q + 4'd1;
                if (round_q == 4'(LAST_ROUND)) state_q <= A_IDLE;
            end
        end
    end

    assign busy_o     = (state_q != A_IDLE);
    assign done_set_o = (state_q == A_ROUND) && (round_q == 4'(LAST_ROUND)) && rnd_end_w;
    assign dout_o     = tail_w;

endmodule : aes128_core
