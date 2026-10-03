// crypto_accel.sv
// Phase 6b -- AES-128 / SHA-256 crypto accelerator, APB4 slave (bead claude_verilog_test-f7vs.10,
// docs/PHASE6_IP_EXPANSION_PLAN.md Sec.6b "6b -- CRYPTO"). Wrapper over aes128_core.sv and
// sha256_core.sv: ONE APB slot, ONE interrupt. EN_AES / EN_SHA drop a core from the build.
//
// NON-GOALS -- READ BEFORE USING. This is NOT production cryptography.
//   * NO side-channel or DPA resistance: the S-box is a data-dependent logic network, nothing is
//     masked, balanced or randomised. Operation DURATION is fixed by construction -- fixed
//     iteration counts, no early exit, no data-dependent control, so 11/41/66/2 clk depends only
//     on mode and SBOX_PARALLEL, never on key or data -- but that is a statement about cycle
//     count only. NO claim is made about power, EM or glitch behaviour.
//   * NO fault-injection hardening: no redundancy, no duplicated datapath, no integrity check on
//     the round count, state or key.
//   * NOT certified and NOT validated against any scheme (no FIPS 140, Common Criteria, CAVP/ACVP).
//     Correctness is established by known-answer vectors in simulation only.
//   * ANY BUS MASTER CAN WRITE, REPLACE AND USE THE KEY, AND READ THE RESULTS. The key itself is
//     NOT readable over the bus (KEY0-3 read 0 forever, and key_q reaches no output), but that
//     buys very little: there is no privilege or secure/non-secure split -- crossbar masters M0
//     (CPU), M1/M2 (GPU) and M3 (DMA) all decode to the APB ring, and axil_to_apb ignores AxPROT
//     -- so any master can substitute its OWN key between a victim's key load and its start, then
//     read DOUT. In CTR mode that yields DOUT = E_attacker(IV) ^ msg_q, from which the attacker
//     recovers the victim's plaintext even though DIN also reads 0; in SHA mode it yields
//     H(victim_msg). Treat this block as an unprotected shared oracle, not as key storage.
//   * NO KEY LIFECYCLE: no zeroisation command, no lock bit, and key_valid never drops once set.
//     The ONLY clear is core_rst_n (rst_n_i & pll_locked), i.e. a whole-SoC reset -- which also
//     fires on a PLL unlock -- so "zeroise the key" means "reset the SoC".
//   * RESIDUAL STATE SURVIVES A CONTEXT SWITCH. key_q, rk_q (the round-10 key, which inverts to
//     the master key), msg_q, DOUT, DIGEST and IV all persist. A second user that writes fewer
//     than four KEY words, or uses partial strobes, silently runs on the first user's key or a
//     mixed key with key_valid still 1; and DOUT/DIGEST remain readable, which in CTR decrypt is
//     the previous user's PLAINTEXT. Software must rewrite all four KEY words with pstrb=0xF on
//     every switch. Note also that after an illegal start `done` asserts while DOUT still holds
//     the PREVIOUS result -- stale data that looks valid.
//   * NONCE AND IV MANAGEMENT ARE ENTIRELY SOFTWARE'S JOB. IV resets to 0, nothing enforces
//     uniqueness, and IV is the one register with no busy-time protection (it lives in the bank,
//     so unlike KEY and DIN there is no shadow-side check to add): a mid-operation write to IV3
//     re-bases the next counter block, so software can cause counter reuse.
//   * NO INTEGRITY AND NO DECRYPT DATAPATH. ECB leaks plaintext patterns block-for-block; CTR is
//     unauthenticated and trivially malleable (flipping a ciphertext bit flips the plaintext bit).
//     There is no MAC, no AEAD mode and no AES decrypt -- CTR covers decryption instead.
//   * THE KEY SHADOW REGISTER (key_q, 128 flops) IS FULLY EXPOSED THROUGH SCAN. Once DFT scan
//     insertion is applied, every flop in this peripheral -- key_q, the AES state s_q and round key
//     rk_q, the message shadow msg_q, the SHA working registers (w_q, a..h_q, hin_q) and the bank
//     flops holding DOUT, DIGEST and IV -- is observable and controllable through the scan chain.
//     DFT ACCESS MUST THEREFORE BE TREATED AS KEY ACCESS. The same holds for any debug path that
//     can observe flop state.
//
// BYTE ORDER. FIPS-197 / FIPS 180-4 big-endian, consistently. For any 128-bit block B[0..15],
// word 0 carries B0 in bits [31:24]: DIN0[31:24] = B0 ... DIN3[7:0] = B15, and the same for KEY,
// IV and DOUT. DIGEST0[31:24] is the most significant byte of H0. FIPS-197 App. B/C vectors and
// hashlib.sha256 therefore line up with no byte swap.
//
// NO NEW RUNTIME-INDEXED MUX (bead ma7 acceptance criterion). The S-box and the SHA K table are
// constant-label case functions, Rcon is an xtime() chain, the message schedule a shift register;
// see the sub-core headers. In this file every KEY / DIN / DOUT / DIGEST word is addressed by a
// constant index inside a constant-bound unrolled loop.
//
// Register map (word indices into the apb4_register_bank, N_REGS=32; 0x070-0x07C reserved, read 0):
//   0    0x000 CRYPTO_CTRL     RW  [1:0] mode (0 ECB, 1 CTR, 2 SHA, 3 reserved), [2] start (W1P,
//                                  reads 0), [3] IRQ enable, [4] SHA_CONT; [31:5] reserved
//   1    0x004 CRYPTO_STATUS   RO  [0] busy, [1] done, [2] key_valid, [3] key_write_rejected
//   2-5  0x008 CRYPTO_KEY0-3   WO  AES-128 key; ALWAYS READS 0 (no readback path exists)
//   6-9  0x018 CRYPTO_IV0-3    RW  CTR counter block (IV3 is the INC32 word)
//   10-13 0x028 CRYPTO_DIN0-3  WO  4-word APERTURE onto one 512-bit shift register; reads 0
//   14-17 0x038 CRYPTO_DOUT0-3 RO  AES output block
//   18-25 0x048 CRYPTO_DIGEST0-7 RO SHA-256 digest; ALSO the SHA chaining value
//   26   0x068 CRYPTO_IRQ_STAT RO  [0] sticky done (the same flop as STATUS[1])
//   27   0x06C CRYPTO_IRQ_CLR  WO  W1C by write-snoop: [0] clears done, [1] clears key_write_rejected
//   28-31      reserved        read 0
//
// REGISTER-BANK PATTERN. hw_wen = 1 every cycle <=> the word is a LIVE MIRROR of internal state
// (STATUS, IRQ_STAT). hw_wen = a pulse <=> the bank word IS the storage element and must hold
// between events (DOUT, DIGEST, IV3). The second form is why this design has no result registers
// at all. STATUS and IRQ_STAT are written every cycle with the value the state flops (state_q,
// done_q, key_rej_q, key_seen_q) are ABOUT TO TAKE, so after every clock edge each field of those
// words equals the corresponding state flop's new value, with no lag: a transfer that completes at
// edge N is already reflected in a read whose ACCESS phase follows it. That is the whole guarantee
// -- STATUS == f(state flops) after every edge -- and it implies nothing about any other register.
//
// START. CTRL[2] is NOT STORED: WMASK[CTRL] has bit 2 clear, so it reads 0 forever and clears
// itself by construction. start is a write-snoop pulse (psel & penable & pwrite at CTRL, pwdata[2]
// and pstrb[0]). A stored start bit cleared by a same-cycle hw_wen writeback would be the
// "one-cycle window in which the value is wrong" failure of plan Sec.3 consequence 1, and the bank's
// collision rule (software wins inside WMASK) would let a software 1 beat the hardware clear anyway.
// Only one APB transfer completes per cycle, so NO TWO SNOOPS CAN FIRE TOGETHER: in particular a
// KEY write can never coincide with a start write. START WHILE BUSY IS SILENTLY IGNORED (no status
// bit, no pslverr). SOFTWARE CONTRACT -- MODE THEN START, IN SEPARATE TRANSFERS: mode, SHA_CONT
// and the legality check all read the bank's CTRL register, which still holds its PRE-write value
// during the ACCESS cycle of the write that carries START. A single write that both changes the
// mode (or SHA_CONT) and sets START therefore runs the OLD mode; write the mode first, then START
// in a later transfer. This single-write case is deliberately not pinned by the test suite.
// Observed latency from the ACCESS phase of the start write to done: 11 clk
// (ECB/CTR, SBOX_PARALLEL=16), 41 clk (SBOX_PARALLEL=4), 66 clk (SHA), 2 clk (illegal op).
//
// ILLEGAL / DISABLED MODE is hang-free at both levels. op_legal = (mode 0|1 & EN_AES & key_valid)
// | (mode 2 & EN_SHA); mode 3 is always illegal. An illegal start takes C_IDLE -> C_DONE -> C_IDLE:
// 2 cycles, busy pulses, done / IRQ_STAT set (the IRQ fires if enabled), NO DOUT / DIGEST / IV
// writeback. Neither the FSM nor a polling driver can hang. DONE DOES NOT IMPLY VALID DATA:
// software must check key_valid and that the mode it asked for is built. (Dropping the start
// silently was rejected: it satisfies "must not hang the FSM" but hangs a `while (!done)` driver.)
//
// KEY. Written by write-snoop into the shadow key_q (address-decoded per word, so KEY0-3 may be
// written in any order; partial byte strobes merge exactly as the bank's own masked write does).
// Key writes are REJECTED while STATUS.busy: this is a spec/determinism requirement (the cores
// sample the key on the start edge only and do not need it held), so it must not be removed as
// redundant. A rejected write latches STATUS[3]; it clears on reset, on IRQ_CLR[1] and on an
// accepted key write. key_valid is set by writing all four words and cleared ONLY BY RESET; a
// partial rewrite leaves key_valid = 1 over a mixed key (software's problem; clearing on any
// single write would break the common "rewrite one word" pattern). THERE IS NO KEY READBACK.
// A key write with pstrb == 4'h0 selects no byte lane: it is NOT a key write at all -- it changes
// no key bit, does not count toward key_valid, and, even while busy, latches no key_write_rejected
// (nothing was attempted). A non-zero strobe, however partial, merges its lanes and counts.
// key_valid is meaningful only when EN_AES = 1: with EN_AES = 0 the shadow still tracks writes (so
// STATUS[2] reads 1 once four words are written) but no AES core exists, op_legal rejects modes
// 0/1 regardless of it, and the bit carries no information.
//
// DIN. The DIN window is a 4-WORD APERTURE onto one 512-bit shift register: only the fact that a
// write hit DIN0..3 matters, not which, and WRITE ORDER IS THE CONTRACT (most significant word
// first: 16 words for SHA, M0 first; 4 words for AES, B0..B3 first). A PARTIAL-STROBE write is
// DROPPED (byte-granular pushes into a shift register have no meaning). Pushes are REJECTED WHILE
// BUSY, with no status bit -- a deliberate, documented asymmetry with key_write_rejected: CTR
// consumes the plaintext at the COMPLETION edge, so it must be stable for the whole operation.
//
// AES MODES. ECB: DOUT = AES(key, DIN). CTR: the core encrypts the counter block IV and the XOR
// with DIN happens at the WRITEBACK, not in the core (the core stays a pure block-encrypt
// primitive, which keeps ECB, CTR-encrypt and CTR-decrypt one datapath). CTR DECRYPT IS
// BIT-IDENTICAL TO CTR ENCRYPT: there is no decrypt mode and no inverse S-box. After each CTR block
// IV3 is incremented (NIST SP 800-38A B.1 INC32: rightmost 32 bits only, carry DISCARDED, IV0-2
// never hardware-written); software must not run one counter past a 2^32-block wrap. IV lives IN
// the bank, so the bank cannot protect it while busy: a software write to IV during a CTR
// operation corrupts the counter, and a same-cycle software write to IV3 beats the hardware
// increment (bank collision rule) -- correct for a re-seed, and otherwise software's responsibility.
//
// SHA CHAINING. DIGEST0-7 are WMASK=0 and written ONLY by the SHA completion pulse, so they ARE the
// chaining register -- no extra 256-bit register. CTRL[4] SHA_CONT: 0 starts from the FIPS 180-4
// H0 constants, 1 continues from the current DIGEST. Multi-block: write 16 words, start with
// SHA_CONT=0, poll done, write the next 16, start with SHA_CONT=1, ..., read DIGEST. PADDING AND
// LENGTH ENCODING ARE SOFTWARE'S JOB. The mode and SHA_CONT are sampled at the start edge; the CTR
// choice is latched at start for the writeback.
//
// CTRL WRITTEN WHILE BUSY is not a supported use, but is safe in these respects. GUARANTEED: the
// operation in flight completes with the mode it STARTED with (the core that was started is the
// one that completes; the CTR/ECB writeback XOR and the IV3 increment use the start-time latch;
// SHA_CONT and the chaining value were sampled at the start edge), so DOUT / DIGEST / IV3 for that
// operation are not corrupted; IRQ enable (CTRL[3]) takes effect immediately on irq_o. NOT
// GUARANTEED: that the new CTRL value does anything for the operation in flight; and a START bit
// in such a write is ignored (busy). The new mode / SHA_CONT apply to the NEXT start. IV is not
// protected while busy at all (see AES MODES).
//
// DOUT / DIGEST VALIDITY. A bank word is written on the completion edge of each operation, so it is
// valid from one completion edge to the next: DOUT / DIGEST ARE NEVER GARBAGE, THEY ARE EITHER
// CURRENT OR ONE OPERATION STALE (a read during a new operation returns the previous result, never
// a partial round state). Software should still gate reads on done.
//
// IRQ: irq_o = done_q & CTRL[3]. LEVEL-HELD, never a pulse -- every IRQ source crosses
// core_clk -> cpu_core_clk through a plain 2-FF cdc_2ff_sync in soc_top.sv, which can miss a pulse.
//   done next = (done_q & ~IRQ_CLR[0]) | done_set   -- SET WINS over a same-cycle W1C, so a
//   completion is never lost to a racing clear. STATUS[1] and IRQ_STAT[0] are THE SAME FLOP mirrored
//   into two words (i2c_controller.sv precedent), not two pieces of state.
//
// CDC: NONE. Single clock domain (core_clk) and no asynchronous inputs anywhere in this peripheral,
// so the cdc_2ff_sync input-synchroniser pattern and the SDC set_false_path of the pad-input
// peripherals (GPIO, I2C) do NOT apply. This is stated rather than omitted on purpose.
//
// Reset: synchronous, active-low throughout (no `negedge rst_n`), matching the other periph/. The
// key shadow is zeroised by reset (and by nothing else).
//
// APB4 interface (ARM IHI0024C): clk/rst_n map to pclk/presetn. ADDR_W = 12 (byte address, [1:0]
// unused). Zero wait states (pready is the bank's constant 1). Writes commit on the ACCESS phase
// (psel & penable); the CTRL start, KEY, DIN and IRQ_CLR snoops decode that same phase.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

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

    // =========================================================================
    // Snoop front end (one copy, shared by every snoop). Only one APB transfer completes per
    // cycle, so no two snoops can ever fire together.
    // Address compares zero-extend addr_word_w to 32 b before comparing (GH #87 idiom, mirrored
    // from apb4_register_bank.sv) so N_REGS == 2**WORDW can never wrap a valid index to a match.
    // =========================================================================
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

    // CTRL start: W1P write-snoop. NOT stored (see header).
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
    logic [127:0] key_q;          // THE key shadow register (see non-goals: exposed through scan)
    logic [3:0]   key_seen_q;     // which KEY words have been written since reset
    logic [3:0]   key_wr_w, key_accept_w;
    logic         key_valid_w, key_valid_d_w;

    assign busy_q = (state_q != C_IDLE);

    assign key_valid_w = &key_seen_q;

    logic op_legal_w;
    assign op_legal_w = (((mode_w == 2'd0) || (mode_w == 2'd1)) && EN_AES && key_valid_w)
                      || ((mode_w == 2'd2) && EN_SHA);   // mode 3 is always illegal

    logic start_accept_w, aes_start_w;
    /* verilator lint_off UNUSEDSIGNAL */
    logic sha_start_w;   // unused when EN_SHA = 0
    /* verilator lint_on  UNUSEDSIGNAL */
    assign start_accept_w = start_pulse_w && (state_q == C_IDLE) && op_legal_w;
    assign aes_start_w    = start_accept_w & ~mode_w[1];
    assign sha_start_w    = start_accept_w & mode_w[1];

    always_comb begin
        state_d = state_q;
        unique case (state_q)
            C_IDLE:  if (start_pulse_w) state_d = op_legal_w ? C_BUSY : C_DONE;
            C_BUSY:  if (aes_done_set_w | sha_done_set_w) state_d = C_IDLE;
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
        if (!rst_n)           ctr_op_q <= 1'b0;
        else if (aes_start_w) ctr_op_q <= ctr_mode_w;
    end

    // =========================================================================
    // Sticky done and key_write_rejected: SET WINS over a same-cycle W1C
    // =========================================================================
    logic done_q, done_d, done_set_any_w;
    assign done_set_any_w = aes_done_set_w | sha_done_set_w | (state_q == C_DONE);
    assign done_d         = (done_q & ~clr_w[0]) | done_set_any_w;

    logic key_rej_q, key_rej_d;
    assign key_rej_d = (key_rej_q & ~clr_w[1] & ~(|key_accept_w)) | ((|key_wr_w) & busy_q);

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
            key_accept_w[i] = key_wr_w[i] & ~busy_q;
        end
    end

    assign key_valid_d_w = &(key_seen_q | key_accept_w);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
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
    // Message shadow -- DIN is a 4-word aperture onto one shift register (see header)
    // =========================================================================
    logic [MSG_W-1:0] msg_q;
    logic             din_push_w;
    assign din_push_w = wr_acc_w & is_din_addr_w & (pstrb == 4'hF) & ~busy_q;

    always_ff @(posedge clk) begin
        if (!rst_n)          msg_q <= '0;
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
            .key_i      (key_q),
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
    end

endmodule : crypto_accel
