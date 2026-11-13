// aes128_core - AES-128 encrypt-only block core with an iterative 128-bit datapath.
//
// Function: The core encrypts one 128-bit block per start. It has no APB, no software-visible register and no CDC.
//   The parent crypto_accel owns the key shadow, the message shadow, the sticky done flag and the result register.
//   The round key is computed on the fly in one 128-bit register, rk_q. There is no inverse S-box.
//   The S-box is a case function over 256 constant labels. The core has no runtime-indexed mux.
// Parameters: SBOX_PARALLEL (16 or 4; any other value is an elaboration $fatal).
//   16: 20 S-boxes, 11 cycles per block. 4: 8 S-boxes, 41 cycles per block, with the same result.
// Ports:
//   start_i is a 1-cycle strobe. It is ignored unless the core is idle. The parent never asserts it while busy_o is 1.
//   The values of key_i and block_i on the accepted start edge are the ones used. The key need not stay held.
//   done_set_o is a one-cycle combinational pulse in the final round cycle.
//   dout_o is the combinational next-state ciphertext. It is valid only in the done_set_o cycle.
//   scan_mode_i = 1 forces the rk_q read net to 0. wipe_i clears the key- and plaintext-derived flops.
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous.
//   wipe_i is an additional one-cycle synchronous clear of s_q, rk_q, rcon_q, round_q and state_q.
//   With SBOX_PARALLEL = 4, phase_q is not in that list. It clears one cycle later, when state_q is A_IDLE.
// Caller rules:
//   - Byte order is big-endian. Byte B0 is bits [127:120]. Byte B15 is bits [7:0].
//   - The parent's key-write rejection while busy is a spec requirement. Do not remove it as redundant.
//   - Do not add a key hold register here.
//   - The core has no side-channel or fault-injection hardening and is not certified. See crypto_accel.
// Doc: ds:mod:aes128-core, tm:mod:aes128-core

module aes128_core
#(
    parameter int unsigned SBOX_PARALLEL = 16   // 16 or 4 only; see g_sbox_parallel_check
) (
    input  logic         clk,
    input  logic         rst_n,

    // rk_q inverts to the master key. It is excluded from scan, and this mask must stay so rk_q reaches no scanned flop.
    input  logic         scan_mode_i,

    // wipe_i: 1-cycle synchronous clear of s_q, rk_q, rcon_q, round_q and state_q. It has the same effect as !rst_n.
    input  logic         wipe_i,

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

    // Pure functions. Declare each function before use (yosys-slang strict mode).

    // AES S-box: 256 constant case labels, never an indexed array read.
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
        if (!rst_n || wipe_i) begin
            state_q <= A_IDLE;
            round_q <= 4'd0;
            rcon_q  <= 8'h01;
            s_q     <= 128'h0;
            rk_q    <= 128'h0;
        end else if (state_q == A_IDLE) begin
            // Pre-load while idle: the whitening value, key_i, 8'h01 and 4'd1 are loaded on every idle cycle.
            // start_i only advances state_q. The start edge captures the same values as an `if (start_i)` load.
            // The cycle counts do not change: 11 and 41 clk from the start edge.
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
