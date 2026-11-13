// crypto_accel - AES-128 and SHA-256 accelerator with one APB4 slot and one interrupt.
//
// Function: The module wraps aes128_core and sha256_core. EN_AES and EN_SHA drop a core from the build.
//   AES offers ECB and CTR, with no decrypt mode (CTR decrypt equals CTR encrypt). SHA-256 hashes one 512-bit block per start.
// Registers (word index; the full map is in ds:mod): CTRL 0, STATUS 1, KEY0-3 2-5, IV0-3 6-9, DIN0-3 10-13,
//   DOUT0-3 14-17, DIGEST0-7 18-25, IRQ_STAT 26, IRQ_CLR 27.
//   CTRL: [1:0] mode (0 ECB, 1 CTR, 2 SHA, 3 reserved), [2] start (W1P, reads 0), [3] IRQ enable, [4] SHA_CONT.
//   STATUS: [0] busy, [1] done, [2] key_valid, [3] key_write_rejected. KEY0-3 and DIN0-3 always read 0.
//   IRQ_STAT[0] is the done flag. IRQ_CLR is W1C: [0] clears done, [1] clears key_write_rejected.
//   done sets on completion or an illegal start and clears on IRQ_CLR[0] or reset. A new set beats a same-cycle clear.
//   STATUS[3] clears on reset, on IRQ_CLR[1] and on an accepted KEY write. A KEY write with pstrb = 0 never sets it.
// Parameters: ADDR_W (APB address width, default 12), EN_AES, EN_SHA (0 drops the core),
//   SBOX_PARALLEL (16 or 4, used when EN_AES = 1).
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous. Reset clears the key shadow.
//   scan_mode_i is quasi-static. scan_wipe_done_o is 0 from a scan_mode_i change until the wipe is applied.
// Caller rules:
//   - Write the mode and SHA_CONT first, and START in a later transfer. A write that carries START runs the old mode and SHA_CONT.
//   - SHA_CONT = 0 starts from the FIPS 180-4 H0. SHA_CONT = 1 continues from DIGEST. Software does padding and the block loop.
//   - DIN0-3 are one aperture onto a shift register. Write order matters, the address does not: 16 words for SHA (M0 first),
//     4 words for AES (B0 first). A partial-strobe DIN write is dropped. Byte order is big-endian.
//   - Write all four KEY words with pstrb=0xF on every switch between users.
//   - key_valid drops only on reset (core_rst_n, which includes a PLL unlock) or the scan wipe. There is no zeroisation command or lock bit.
//   - A START while busy is ignored. KEY and DIN writes while busy are rejected. A rejected KEY write sets STATUS[3].
//   - Check key_valid and the built modes. After an illegal start, done is 1 and DOUT holds the previous result.
//   - Do not write IV during a CTR operation. Do not run one counter past a 2^32-block wrap. IV resets to 0; software owns nonce uniqueness.
//   - DOUT and DIGEST are current or one operation stale, never partial. Gate reads on done.
//   - ECB leaks plaintext patterns. CTR is unauthenticated and malleable. There is no MAC and no AEAD mode.
//   - irq_o = done_q & CTRL[3]. It is level-held.
//   - This block is NOT production cryptography. It has no side-channel or fault-injection hardening and no certification.
//   - Any bus master can write and use the key and read the results. Treat the block as an unprotected shared oracle.
//   - Residual state (key, message, DOUT, DIGEST, IV) persists between users.
//   - The scan wipe takes 3 clk edges after a scan_mode_i change. soc_top gates scan_en with scan_wipe_done_o.
//     Before the first edge, scan_out shows the Q of each chain's last flop.
//   - The wipe does not clear CTRL, done or key_write_rejected. During it a START takes the illegal path, an operation
//     in flight ends with done and no data, and KEY and DIN writes are dropped.
//   - Treat any debug or scan path that observes flop state as key access.
// Full contract: ds:mod:crypto-accel
// Doc: ds:mod:crypto-accel, tm:mod:crypto-accel

module crypto_accel
#(
    parameter int unsigned ADDR_W        = 12,   // APB4 local address width
    parameter bit          EN_AES        = 1,    // 0 drops the AES core (mode 0/1 report done, no data)
    parameter bit          EN_SHA        = 1,    // 0 drops the SHA core (mode 2 reports done, no data)
    /* verilator lint_off UNUSEDPARAM */
    parameter int unsigned SBOX_PARALLEL = 16    // 16 or 4 (aes128_core); unused when EN_AES = 0
    /* verilator lint_on  UNUSEDPARAM */
) (
    input  logic clk,
    input  logic rst_n,

    // scan_mode_i = 1 forces the key_q and rk_q read nets to 0. Quasi-static.
    // Tie it to 1'b0 where there is no scan-aware parent. See ds:mod:crypto-accel.
    input  logic scan_mode_i,

    // scan_wipe_done_o is 0 from a scan_mode_i change until the wipe is applied. Leave it open
    // where there is no scan-aware parent. soc_top ANDs the scan enable with it.
    // See ds:mod:crypto-accel.
    output logic scan_wipe_done_o,

    // =========================================================================
    // APB4 slave -- control/status registers
    // SETUP  phase: psel=1, penable=0 (one cycle).
    // ACCESS phase: psel=1, penable=1; transfer complete when pready=1.
    // =========================================================================
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] paddr,   // byte address; [1:0] unused (word-aligned)
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,

    // Interrupt -- level-held, never a pulse
    output logic irq_o
);

    // Elaboration guards. A generate-scope $fatal (not wrapped in `initial`) fires at ELABORATION
    // time, under `verilator --lint-only` too (same idiom as i2c_controller.sv's g_addr_w_check).
    // 32 registers need word index 0..31 -> 5 word bits -> ADDR_W >= 7.
    if (ADDR_W < 7 || ADDR_W > 32) begin : g_addr_w_check
        $fatal(1, "crypto_accel: ADDR_W (%0d) must be in [7, 32]", ADDR_W);
    end
    // A peripheral that can do nothing is a build error, not a configuration.
    if (!EN_AES && !EN_SHA) begin : g_en_check
        $fatal(1, "crypto_accel: EN_AES and EN_SHA cannot both be 0");
    end

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned REG_CTRL     = 0;
    localparam int unsigned REG_STATUS   = 1;
    localparam int unsigned REG_KEY0     = 2;    // KEY0-3 = 2..5
    localparam int unsigned REG_IV0      = 6;    // IV0-3  = 6..9
    localparam int unsigned REG_DIN0     = 10;   // DIN0-3 = 10..13
    localparam int unsigned REG_DOUT0    = 14;   // DOUT0-3 = 14..17
    localparam int unsigned REG_DIGEST0  = 18;   // DIGEST0-7 = 18..25
    localparam int unsigned REG_IRQ_STAT = 26;
    localparam int unsigned REG_IRQ_CLR  = 27;
    localparam int unsigned N_REGS       = 32;

    // The message shadow holds a full SHA block only when SHA is built: EN_SHA=0 pays 128 flops.
    localparam int unsigned MSG_W = EN_SHA ? 512 : 128;

    // FIPS 180-4 Sec.5.3.3 initial hash value, H0 at [255:224].
    localparam logic [255:0] FIPS_H0 = {32'h6a09e667, 32'hbb67ae85, 32'h3c6ef372, 32'ha54ff53a,
                                        32'h510e527f, 32'h9b05688c, 32'h1f83d9ab, 32'h5be0cd19};

    // Word address width (mirrors apb4_register_bank's own WORDW).
    localparam int unsigned WORDW = ADDR_W - 2;

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  //  0 CRYPTO_CTRL
        32'h0000_0000,  //  1 CRYPTO_STATUS
        32'h0000_0000,  //  2 CRYPTO_KEY0
        32'h0000_0000,  //  3 CRYPTO_KEY1
        32'h0000_0000,  //  4 CRYPTO_KEY2
        32'h0000_0000,  //  5 CRYPTO_KEY3
        32'h0000_0000,  //  6 CRYPTO_IV0
        32'h0000_0000,  //  7 CRYPTO_IV1
        32'h0000_0000,  //  8 CRYPTO_IV2
        32'h0000_0000,  //  9 CRYPTO_IV3
        32'h0000_0000,  // 10 CRYPTO_DIN0
        32'h0000_0000,  // 11 CRYPTO_DIN1
        32'h0000_0000,  // 12 CRYPTO_DIN2
        32'h0000_0000,  // 13 CRYPTO_DIN3
        32'h0000_0000,  // 14 CRYPTO_DOUT0
        32'h0000_0000,  // 15 CRYPTO_DOUT1
        32'h0000_0000,  // 16 CRYPTO_DOUT2
        32'h0000_0000,  // 17 CRYPTO_DOUT3
        32'h0000_0000,  // 18 CRYPTO_DIGEST0
        32'h0000_0000,  // 19 CRYPTO_DIGEST1
        32'h0000_0000,  // 20 CRYPTO_DIGEST2
        32'h0000_0000,  // 21 CRYPTO_DIGEST3
        32'h0000_0000,  // 22 CRYPTO_DIGEST4
        32'h0000_0000,  // 23 CRYPTO_DIGEST5
        32'h0000_0000,  // 24 CRYPTO_DIGEST6
        32'h0000_0000,  // 25 CRYPTO_DIGEST7
        32'h0000_0000,  // 26 CRYPTO_IRQ_STAT
        32'h0000_0000,  // 27 CRYPTO_IRQ_CLR
        32'h0000_0000,  // 28 reserved
        32'h0000_0000,  // 29 reserved
        32'h0000_0000,  // 30 reserved
        32'h0000_0000   // 31 reserved
    };

    // WMASK: only CTRL (bit 2 = start is NOT stored) and IV are software-writable. KEY / DIN /
    // IRQ_CLR are WO-by-snoop: mask 0, never hardware-written, so they read 0 forever.
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_001B,  //  0 CRYPTO_CTRL   bits 0,1 mode; 3 irq_en; 4 SHA_CONT (2 masked out)
        32'h0000_0000,  //  1 CRYPTO_STATUS RO
        32'h0000_0000,  //  2 CRYPTO_KEY0   WO (snoop)
        32'h0000_0000,  //  3 CRYPTO_KEY1   WO (snoop)
        32'h0000_0000,  //  4 CRYPTO_KEY2   WO (snoop)
        32'h0000_0000,  //  5 CRYPTO_KEY3   WO (snoop)
        32'hFFFF_FFFF,  //  6 CRYPTO_IV0    RW
        32'hFFFF_FFFF,  //  7 CRYPTO_IV1    RW
        32'hFFFF_FFFF,  //  8 CRYPTO_IV2    RW
        32'hFFFF_FFFF,  //  9 CRYPTO_IV3    RW (hardware INC32 word)
        32'h0000_0000,  // 10 CRYPTO_DIN0   WO (snoop)
        32'h0000_0000,  // 11 CRYPTO_DIN1   WO (snoop)
        32'h0000_0000,  // 12 CRYPTO_DIN2   WO (snoop)
        32'h0000_0000,  // 13 CRYPTO_DIN3   WO (snoop)
        32'h0000_0000,  // 14 CRYPTO_DOUT0  RO
        32'h0000_0000,  // 15 CRYPTO_DOUT1  RO
        32'h0000_0000,  // 16 CRYPTO_DOUT2  RO
        32'h0000_0000,  // 17 CRYPTO_DOUT3  RO
        32'h0000_0000,  // 18 CRYPTO_DIGEST0 RO
        32'h0000_0000,  // 19 CRYPTO_DIGEST1 RO
        32'h0000_0000,  // 20 CRYPTO_DIGEST2 RO
        32'h0000_0000,  // 21 CRYPTO_DIGEST3 RO
        32'h0000_0000,  // 22 CRYPTO_DIGEST4 RO
        32'h0000_0000,  // 23 CRYPTO_DIGEST5 RO
        32'h0000_0000,  // 24 CRYPTO_DIGEST6 RO
        32'h0000_0000,  // 25 CRYPTO_DIGEST7 RO
        32'h0000_0000,  // 26 CRYPTO_IRQ_STAT RO
        32'h0000_0000,  // 27 CRYPTO_IRQ_CLR WO (snoop)
        32'h0000_0000,  // 28 reserved
        32'h0000_0000,  // 29 reserved
        32'h0000_0000,  // 30 reserved
        32'h0000_0000   // 31 reserved
    };

    logic [31:0] regs_o    [N_REGS];
    logic        hw_wen_i  [N_REGS];
    logic [31:0] hw_wdata_i[N_REGS];

    apb4_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .RESET_VAL (RESET_VAL),
        .WMASK     (WMASK)
    ) u_regbank (
        .pclk       (clk),
        .presetn    (rst_n),
        .psel       (psel),
        .penable    (penable),
        .pwrite     (pwrite),
        .paddr      (paddr),
        .pwdata     (pwdata),
        .pstrb      (pstrb),
        .prdata     (prdata),
        .pready     (pready),
        .pslverr    (pslverr),
        .regs_o     (regs_o),
        .hw_wen_i   (hw_wen_i),
        .hw_wdata_i (hw_wdata_i)
    );

    // Snoop front end, one copy for every snoop. One APB transfer completes per cycle.
    // The address compares zero-extend addr_word_w to 32 bits, so N_REGS == 2**WORDW cannot wrap an index.
    logic [WORDW-1:0] addr_word_w;
    assign addr_word_w = paddr[ADDR_W-1:2];

    logic [31:0] addr_ext_w;
    assign addr_ext_w = {{(32-WORDW){1'b0}}, addr_word_w};

    logic access_w;
    assign access_w = psel & penable;  // pready is a constant 1 from the bank

    logic wr_acc_w;
    assign wr_acc_w = access_w & pwrite;

    function automatic logic [31:0] strb_expand(input logic [3:0] strb);
        for (int unsigned b = 0; b < 4; b++)
            strb_expand[8*b +: 8] = strb[b] ? 8'hFF : 8'h00;
    endfunction

    // The expanded strobe MUST land in a named net before being sliced (a part-select applied
    // directly to a function-call result is not legal Verilog-2005; sv2v passes it through and yosys
    // rejects it -- see trng.sv / i2c_controller.sv / pwm_controller.sv, fixed in 2c5f351).
    logic [31:0] strb_mask_w;
    assign strb_mask_w = strb_expand(pstrb);

    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] wdata_m_w;   // pwdata with unselected byte lanes zeroed; only IRQ_CLR[1:0] used
    /* verilator lint_on  UNUSEDSIGNAL */
    assign wdata_m_w = pwdata & strb_mask_w;

    logic is_ctrl_addr_w, is_irq_clr_addr_w, is_din_addr_w;
    assign is_ctrl_addr_w    = (addr_ext_w == 32'(REG_CTRL));
    assign is_irq_clr_addr_w = (addr_ext_w == 32'(REG_IRQ_CLR));
    assign is_din_addr_w     = (addr_ext_w >= 32'(REG_DIN0)) && (addr_ext_w < 32'(REG_DIN0 + 4));

    logic [3:0] is_key_addr_w;
    always_comb begin
        for (int unsigned i = 0; i < 4; i++)
            is_key_addr_w[i] = (addr_ext_w == 32'(REG_KEY0 + i));
    end

    // IRQ_CLR write-snoop: one-cycle W1C mask, honouring pstrb.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] clr_w;   // only [1:0] defined
    /* verilator lint_on  UNUSEDSIGNAL */
    assign clr_w = (wr_acc_w && is_irq_clr_addr_w) ? wdata_m_w : 32'h0;

    // CTRL start: W1P write-snoop. NOT stored See ds:mod:crypto-accel.
    logic start_pulse_w;
    assign start_pulse_w = wr_acc_w & is_ctrl_addr_w & pwdata[2] & strb_mask_w[2];

    // =========================================================================
    // Register views
    // =========================================================================
    logic [1:0] mode_w;
    logic       irq_en_w, sha_cont_w, ctr_mode_w;

    assign mode_w     = regs_o[REG_CTRL][1:0];
    assign irq_en_w   = regs_o[REG_CTRL][3];
    assign sha_cont_w = regs_o[REG_CTRL][4];
    assign ctr_mode_w = (mode_w == 2'd1);

    // Unused register bits: reserved fields and the words whose value is carried by the bank
    // purely for readback (HW-written RO words, snoop-only WO words, never-stored start bit).
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_regs_w;
    assign unused_regs_w = ^{regs_o[REG_CTRL][31:5], regs_o[REG_CTRL][2],
                             regs_o[REG_STATUS],
                             regs_o[REG_KEY0], regs_o[REG_KEY0 + 1], regs_o[REG_KEY0 + 2],
                             regs_o[REG_KEY0 + 3],
                             regs_o[REG_DIN0], regs_o[REG_DIN0 + 1], regs_o[REG_DIN0 + 2],
                             regs_o[REG_DIN0 + 3],
                             regs_o[REG_DOUT0], regs_o[REG_DOUT0 + 1], regs_o[REG_DOUT0 + 2],
                             regs_o[REG_DOUT0 + 3],
                             regs_o[REG_IRQ_STAT], regs_o[REG_IRQ_CLR],
                             regs_o[28], regs_o[29], regs_o[30], regs_o[31]};
    /* verilator lint_on  UNUSEDSIGNAL */

    // =========================================================================
    // Wrapper FSM: C_IDLE -> C_BUSY -> C_IDLE (legal start), C_IDLE -> C_DONE -> C_IDLE (illegal)
    // =========================================================================
    typedef enum logic [1:0] {
        C_IDLE = 2'd0,
        C_BUSY = 2'd1,
        C_DONE = 2'd2
    } ctl_state_e;

    ctl_state_e state_q, state_d;
    logic       busy_q, busy_d;

    logic aes_done_set_w, sha_done_set_w;

    // Key shadow state is declared up here because busy_q gates it and op_legal_w reads it.
    logic [127:0] key_q;          // THE key shadow register (excluded from scan; masked, see header)
    // key_q as seen by the AES core: 0 in scan mode (DFT key mask). Unread when EN_AES = 0.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [127:0] key_eff_w;
    /* verilator lint_on  UNUSEDSIGNAL */
    logic [3:0]   key_seen_q;     // which KEY words have been written since reset
    logic [3:0]   key_wr_w, key_accept_w;
    logic         key_valid_w, key_valid_d_w;

    assign busy_q = (state_q != C_IDLE);

    // DFT key mask (Doc: tm:ch:dft-architecture sec.7.3): 128 AND gates. Must survive synthesis
    // as logic on the key path -- it is the whole point of excluding key_q from scan.
    assign key_eff_w = key_q & {128{~scan_mode_i}};

    assign key_valid_w = &key_seen_q;

    // Scan-mode edge detect for wipe_w: a 2-FF synchroniser and one history flop, deliberately unreset.
    // They track scan_mode_i through reset, so a reset neither creates nor hides an edge.
    logic scan_s1_q, scan_s2_q, scan_prev_q;
    always_ff @(posedge clk) begin
        scan_s1_q   <= scan_mode_i;
        scan_s2_q   <= scan_s1_q;
        scan_prev_q <= scan_s2_q;
    end

    logic wipe_w;   // one cycle per scan_mode_i edge (entry and exit); clears all key/data state
    assign wipe_w = scan_s2_q ^ scan_prev_q;

    // scan_wipe_done_o is 0 from a scan_mode_i change until the edge that loads scan_prev_q.
    // That edge also applies the wipe_w clears. It is a constant 1 after 3 clk edges of a steady scan_mode_i.
    assign scan_wipe_done_o = ~((scan_mode_i ^ scan_prev_q) | (scan_s1_q ^ scan_prev_q) | wipe_w);

    logic op_legal_w;
    assign op_legal_w = (((mode_w == 2'd0) || (mode_w == 2'd1)) && EN_AES && key_valid_w)
                      || ((mode_w == 2'd2) && EN_SHA);   // mode 3 is always illegal

    logic start_accept_w, aes_start_w;
    /* verilator lint_off UNUSEDSIGNAL */
    logic sha_start_w;   // unused when EN_SHA = 0
    /* verilator lint_on  UNUSEDSIGNAL */
    assign start_accept_w = start_pulse_w && (state_q == C_IDLE) && op_legal_w && !wipe_w;
    assign aes_start_w    = start_accept_w & ~mode_w[1];
    assign sha_start_w    = start_accept_w & mode_w[1];

    always_comb begin
        state_d = state_q;
        unique case (state_q)
            C_IDLE:  if (start_pulse_w) state_d = (op_legal_w && !wipe_w) ? C_BUSY : C_DONE;
            C_BUSY:  if (wipe_w)                               state_d = C_DONE;   // aborted: no data
                     else if (aes_done_set_w | sha_done_set_w) state_d = C_IDLE;
            C_DONE:  state_d = C_IDLE;
            default: state_d = C_IDLE;
        endcase
    end

    assign busy_d = (state_d != C_IDLE);

    always_ff @(posedge clk) begin
        if (!rst_n) state_q <= C_IDLE;
        else        state_q <= state_d;
    end

    // CTR choice latched at the accepted start so the completion-edge writeback cannot be
    // corrupted by a CTRL write in flight.
    logic ctr_op_q;
    always_ff @(posedge clk) begin
        if (!rst_n || wipe_w) ctr_op_q <= 1'b0;
        else if (aes_start_w) ctr_op_q <= ctr_mode_w;
    end

    // =========================================================================
    // Sticky done and key_write_rejected: SET WINS over a same-cycle W1C
    // =========================================================================
    logic done_q, done_d, done_set_any_w;
    assign done_set_any_w = aes_done_set_w | sha_done_set_w | (state_q == C_DONE);
    assign done_d         = (done_q & ~clr_w[0]) | done_set_any_w;

    logic key_rej_q, key_rej_d;
    assign key_rej_d = (key_rej_q & ~clr_w[1] & ~(|key_accept_w)) | ((|key_wr_w) & (busy_q | wipe_w));

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            done_q    <= 1'b0;
            key_rej_q <= 1'b0;
        end else begin
            done_q    <= done_d;
            key_rej_q <= key_rej_d;
        end
    end

    assign irq_o = done_q & irq_en_w;

    // =========================================================================
    // Key shadow -- address-decoded per-word write-snoop, rejected while busy. Constant-bound
    // unrolled loops only; no runtime index.
    // =========================================================================
    always_comb begin
        for (int unsigned i = 0; i < 4; i++) begin
            // A zero strobe selects no byte lane: no write attempted, so neither accepted nor rejected.
            key_wr_w[i]     = wr_acc_w & is_key_addr_w[i] & (|pstrb);
            key_accept_w[i] = key_wr_w[i] & ~busy_q;   // wipe_w needs no term: it wins in every consumer
        end
    end

    assign key_valid_d_w = ~wipe_w & (&(key_seen_q | key_accept_w));

    always_ff @(posedge clk) begin
        if (!rst_n || wipe_w) begin
            key_q       <= 128'h0;
            key_seen_q  <= 4'h0;
        end else begin
            for (int unsigned i = 0; i < 4; i++) begin
                if (key_accept_w[i]) begin
                    key_q[32*(3-i) +: 32] <= (key_q[32*(3-i) +: 32] & ~strb_mask_w)
                                           | (pwdata & strb_mask_w);
                    key_seen_q[i]         <= 1'b1;
                end
            end
        end
    end

    // =========================================================================
    // Message shadow -- DIN is a 4-word aperture onto one shift register (see ds:mod:crypto-accel)
    // =========================================================================
    logic [MSG_W-1:0] msg_q;
    logic             din_push_w;
    assign din_push_w = wr_acc_w & is_din_addr_w & (pstrb == 4'hF) & ~busy_q;   // wipe_w wins in msg_q's clear

    always_ff @(posedge clk) begin
        if (!rst_n || wipe_w) msg_q <= '0;
        else if (din_push_w) msg_q <= {msg_q[MSG_W-33:0], pwdata};
    end

    // =========================================================================
    // Core connections
    // =========================================================================
    /* verilator lint_off UNUSEDSIGNAL */
    logic         aes_busy_w, sha_busy_w;   // the wrapper FSM keeps its own busy; kept for symmetry
    /* verilator lint_on  UNUSEDSIGNAL */
    logic [127:0] aes_dout_w;
    logic [255:0] sha_h_o_w;

    logic [127:0] iv_block_w;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [127:0] aes_block_w;   // unused when EN_AES = 0
    /* verilator lint_on  UNUSEDSIGNAL */
    assign iv_block_w  = {regs_o[REG_IV0], regs_o[REG_IV0 + 1], regs_o[REG_IV0 + 2],
                          regs_o[REG_IV0 + 3]};
    assign aes_block_w = ctr_mode_w ? iv_block_w : msg_q[127:0];

    logic [255:0] digest_w;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [255:0] sha_h_i_w;     // unused when EN_SHA = 0
    /* verilator lint_on  UNUSEDSIGNAL */
    assign digest_w  = {regs_o[REG_DIGEST0],     regs_o[REG_DIGEST0 + 1], regs_o[REG_DIGEST0 + 2],
                        regs_o[REG_DIGEST0 + 3], regs_o[REG_DIGEST0 + 4], regs_o[REG_DIGEST0 + 5],
                        regs_o[REG_DIGEST0 + 6], regs_o[REG_DIGEST0 + 7]};
    assign sha_h_i_w = sha_cont_w ? digest_w : FIPS_H0;

    if (EN_AES) begin : g_aes
        aes128_core #(
            .SBOX_PARALLEL (SBOX_PARALLEL)
        ) u_aes (
            .clk        (clk),
            .rst_n      (rst_n),
            .start_i    (aes_start_w),
            .scan_mode_i(scan_mode_i),
            .wipe_i     (wipe_w),
            .key_i      (key_eff_w),
            .block_i    (aes_block_w),
            .busy_o     (aes_busy_w),
            .done_set_o (aes_done_set_w),
            .dout_o     (aes_dout_w)
        );
    end else begin : g_no_aes
        assign aes_busy_w     = 1'b0;
        assign aes_done_set_w = 1'b0;
        assign aes_dout_w     = '0;
    end

    if (EN_SHA) begin : g_sha
        sha256_core u_sha (
            .clk        (clk),
            .rst_n      (rst_n),
            .wipe_i     (wipe_w),
            .start_i    (sha_start_w),
            .block_i    (msg_q),
            .h_i        (sha_h_i_w),
            .busy_o     (sha_busy_w),
            .done_set_o (sha_done_set_w),
            .h_o        (sha_h_o_w)
        );
    end else begin : g_no_sha
        assign sha_busy_w     = 1'b0;
        assign sha_done_set_w = 1'b0;
        assign sha_h_o_w      = '0;
    end

    // =========================================================================
    // HW-writeback -- combinational mirror of the NEXT state / completion value
    // =========================================================================
    logic ctr_inc_w;
    assign ctr_inc_w = aes_done_set_w & ctr_op_q;

    always_comb begin
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // CRYPTO_STATUS: {key_write_rejected, key_valid, done, busy}. RO -- live mirror.
        hw_wen_i  [REG_STATUS] = 1'b1;
        hw_wdata_i[REG_STATUS] = {28'h0, key_rej_d, key_valid_d_w, done_d, busy_d};

        // CRYPTO_IRQ_STAT: {done}. Same flop as STATUS[1].
        hw_wen_i  [REG_IRQ_STAT] = 1'b1;
        hw_wdata_i[REG_IRQ_STAT] = {31'h0, done_d};

        // CRYPTO_DOUT0-3: written on the AES completion edge. CTR XORs the plaintext word here.
        for (int unsigned i = 0; i < 4; i++) begin
            hw_wen_i  [REG_DOUT0 + i] = aes_done_set_w;
            hw_wdata_i[REG_DOUT0 + i] = aes_dout_w[32*(3-i) +: 32]
                                      ^ (ctr_op_q ? msg_q[32*(3-i) +: 32] : 32'h0);
        end

        // CRYPTO_IV3: INC32 on the rightmost word only, carry discarded. IV0-2 never HW-written.
        hw_wen_i  [REG_IV0 + 3] = ctr_inc_w;
        hw_wdata_i[REG_IV0 + 3] = regs_o[REG_IV0 + 3] + 32'd1;

        // CRYPTO_DIGEST0-7: written on the SHA completion edge; also the chaining register.
        for (int unsigned i = 0; i < 8; i++) begin
            hw_wen_i  [REG_DIGEST0 + i] = sha_done_set_w;
            hw_wdata_i[REG_DIGEST0 + i] = sha_h_o_w[32*(7-i) +: 32];
        end

        // Scan wipe: clear the bank words that hold key- or message-derived results, and IV, through the hardware-write port.
        // This block comes last, so it overrides every completion write and the IV3 increment in the same cycle.
        if (wipe_w) begin
            for (int unsigned i = 0; i < 4; i++) begin
                hw_wen_i  [REG_DOUT0 + i] = 1'b1;
                hw_wdata_i[REG_DOUT0 + i] = 32'h0;
                hw_wen_i  [REG_IV0 + i]   = 1'b1;
                hw_wdata_i[REG_IV0 + i]   = 32'h0;
            end
            for (int unsigned i = 0; i < 8; i++) begin
                hw_wen_i  [REG_DIGEST0 + i] = 1'b1;
                hw_wdata_i[REG_DIGEST0 + i] = 32'h0;
            end
        end
    end

endmodule : crypto_accel
