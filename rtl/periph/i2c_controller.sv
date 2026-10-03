// i2c_controller.sv
// Phase 6a-5 -- I2C master controller, APB4 slave (bead claude_verilog_test-f7vs.9,
// docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6a-5 -- I2C"). Master-only, 7-bit addressing, repeated
// START, mandatory clock stretching, arbitration-loss DETECTION, 8-byte TX/RX FIFOs.
//
// !!! PAD-RING CONTRACT -- READ BEFORE INTEGRATING (also in docs/design/MEMORY_MAP.md) !!!
//   * Open-drain, NO TRISTATE. Each line is the unidirectional triplet used by GPIO:
//       i2c_scl_o / i2c_scl_oe_o / i2c_scl_i      i2c_sda_o / i2c_sda_oe_o / i2c_sda_i
//   * `*_oe_o` is the real control. oe = 1 DRIVES THE LINE LOW; oe = 0 RELEASES it.
//   * `*_o` is HARD-TIED 1'b0 and is DEAD. It exists only for pad-ring symmetry with
//     gpio_out_o/gpio_oe_o/gpio_in_i, so the I2C pins map onto a pad cell the same way a GPIO pin
//     does. Do not use it as data: the pad must drive 0 when oe = 1 and be high-Z when oe = 0.
//   * An EXTERNAL PULL-UP on each line is REQUIRED. Nothing on-chip ever drives a line high; a
//     released line is high only because the pull-up makes it so.
//   * The wired-AND of master and slaves lives OFF-CHIP (the physical bus). This RTL does not model
//     it; a testbench must (the internal loopback below models it for its one slave only).
//   * `*_i` are the sensed pad levels and are ASYNCHRONOUS (see "CDC").
//
// Register map (word indices into the apb4_register_bank, N_REGS=12; 0x030-0xFFC read 0):
//   0  I2C_CTRL      RW  [0] EN, [1] LOOPBACK, [11:8] RX_THR (FIFO level that raises
//                        IRQ_STAT[4]; 0 behaves as 1; 9..15 never fire); other bits reserved, read 0
//   1  I2C_STATUS    RO  [0] busy (engine executing a command), [1] txn_active (this master holds
//                        the bus: START sent, STOP not yet), [2] nack (sticky), [3] arb_lost
//                        (sticky), [4] timeout (sticky), [5] SCL sensed level, [6] SDA sensed level
//                        ([4:2] are the SAME flops as IRQ_STAT[3:1]; they clear via IRQ_CLR)
//   2  I2C_CLKDIV    RW  [15:0] tick divider, reset 0x00FF. One bit = 4 ticks, a tick is
//                        (CLKDIV+1) clk cycles, so f_scl = f_clk / (4*(CLKDIV+1)) with no stretching
//                        (see "Bit timing" for the exact phase split and the residual error).
//                        Values below CLKDIV_MIN are CLAMPED to CLKDIV_MIN (reads back as written)
//   3  I2C_ADDR      RW  [6:0] slave address, [7] R/W (0 = write, 1 = read); START sends
//                        {ADDR[6:0], ADDR[7]}. The engine does not police ADDR[7] against the
//                        data op in CMD: software keeps them consistent
//   4  I2C_TX_DATA   WO  a write with pstrb[0] pushes pwdata[7:0] into the TX FIFO (snoop-push);
//                        a push into a FULL FIFO is dropped; reads 0
//   5  I2C_RX_DATA   RO  RX FIFO head; an APB READ pops it (snoop-pop, SPI_RX idiom); reading an
//                        EMPTY FIFO returns 0, sets no status and does not underflow
//   6  I2C_CMD       WO  snoop-pulse, reads 0, see "Commands"
//   7  I2C_FIFO_STAT RO  [3:0] tx_level, [7:4] rx_level, [8] tx_full, [9] tx_empty, [10] rx_full,
//                        [11] rx_empty
//   8  I2C_TIMEOUT   RW  [15:0] stuck-wait limit in engine TICKS, reset 0xFFFF; 0 disables
//   9  I2C_IRQ_EN    RW  [4:0] masks irq_o only; I2C_IRQ_STAT is the raw pending register
//  10  I2C_IRQ_STAT  RO  [0] done, [1] nack, [2] arb_lost, [3] timeout (all four sticky),
//                        [4] rx_threshold (LIVE level, follows the RX FIFO)
//  11  I2C_IRQ_CLR    WO  W1C against IRQ_STAT[3:0] (bit 4 is a live level and has no clear);
//                        reads 0
//
// Commands. A write to I2C_CMD with pstrb[0] set (pstrb[1] for COUNT) starts ONE command:
//   [0] START   [1] WRITE   [2] READ   [3] STOP   [4] NACK_LAST   [15:8] COUNT
// Fixed execution order inside one command: START (or repeated START if txn_active) + address
// byte; then COUNT data bytes (WRITE wins if WRITE and READ are both set); then STOP.
//   * COUNT 0 means 1. WRITE pops the TX FIFO per byte and READ pushes the RX FIFO per byte; if the
//     TX FIFO is empty (WRITE) or the RX FIFO is full (READ) the engine HOLDS SCL LOW and waits,
//     bounded by I2C_TIMEOUT. COUNT may exceed the 8-byte FIFOs for that reason.
//   * READ ACKs every byte except the last of the command, which is NACKed iff NACK_LAST = 1.
//   * A NACK (address or write data) sets `nack`, abandons the remaining data bytes, and still
//     sends STOP if STOP was requested; otherwise the bus is held (txn_active stays 1) so software
//     can issue STOP or a repeated START. `done` then sets.
//   * A command is ACCEPTED only when CTRL.EN = 1, the engine is idle, and it is legal: it needs
//     START, or txn_active for a WRITE/READ/STOP-only command. An illegal or busy-time write is
//     IGNORED silently; STATUS.busy is the gate software polls.
//   * `done` sets when a command finishes normally (ACK or NACK), after STOP when one was sent. An
//     arbitration loss or timeout sets its own sticky bit INSTEAD of `done`.
//   * CTRL.EN = 0 aborts the engine at once (lines released, no event bit, txn_active cleared) and
//     flushes BOTH FIFOs once, on the 1 -> 0 edge. Sticky flags and registers are retained. Change
//     CTRL.LOOPBACK only while idle.
//
// Bit timing (full phase table, derivation and residual-error list: i2c_bit_engine.sv header).
// N = CLKDIV_eff + 1 clk per tick; one SCL bit is FOUR timed phases and the bus period is 4*N clk,
// f_scl = f_clk / (4*N), with SCL low = 2N + K and SCL high = 2N - K clk, K = floor(N/8) (the skew
// buys the Fast-mode tLOW; a symmetric split misses it). The 3 clk it takes the released SCL to come
// back through the 2-FF synchroniser are counted INSIDE the high phase, so the period is exactly 4*N.
// Measured (100 MHz clk): CLKDIV 249 -> 1000 clk = 100.0 kHz (tLOW 5.31 us, tHIGH 4.69 us); CLKDIV 62
// -> 252 clk = 396.8 kHz (tLOW 1.33 us, tHIGH 1.19 us).
// RESIDUAL ERROR: exactly 4*N unless (a) the SCL pad rises more than ~1 clk after oe_o releases it
// (the excess is waited out and adds to the period -- bus-capacitance stretching, not compensated);
// (b) a slave stretches SCL (adds the stretch, bounded by I2C_TIMEOUT); (c) CTRL.LOOPBACK, which has
// no synchroniser, runs at 4*N - 2 clk. Fast-mode tLOW at an exact 400 kHz is missed for N = 4..7 and
// 13..15 only (f_clk 6.4..11.2 or 20.8..24 MHz); Standard mode and every other N meet the limits.
//
// Clock stretching is MANDATORY: the bit engine releases SCL, then does not advance (and does not
// start its SCL-high interval) until the SYNCHRONISED scl_i reads high. I2C_TIMEOUT bounds every such
// wait (bus busy before START, SCL stretched, FIFO starvation). On expiry the sticky `timeout` bit
// sets, both lines are released and the engine goes idle. It is sticky and diagnostic: without it a
// stuck slave hangs the FSM with no visible cause.
//
// Arbitration: whenever the engine releases SDA to send a 1 (data/address bit, or a NACK in a read's
// ACK slot) it compares that against the sensed SDA at the end of the SCL-high interval. Sensed low
// = another master drove it = ARBITRATION LOST: sticky `arb_lost`, lines released, engine idle. The
// ACK slot of a write is excluded (the slave is meant to pull it low). There is NO retry FSM;
// software re-issues. Detection falls out of the open-drain model for free.
//
// CDC: i2c_scl_i and i2c_sda_i are asynchronous external pins and are SINGLE-BIT, so each goes
// through its own cdc_2ff_sync #(.WIDTH(1)) instance. cdc_2ff_sync's multi-bit prohibition does not
// apply (cf. gpio_controller.sv, which instantiates one per pin for the same reason). Nothing is
// placed in front of the synchroniser. Its reset value is 0, which reads as "line low" for the first
// two cycles after reset; nothing depends on it, because EN resets 0 and the pre-START bus-free wait
// (S_BUSWAIT) simply holds until both synchronised lines read high.
//
// Prescaler minimum (explicit elaboration guard): the engine samples the SYNCHRONISED lines, which
// lag the pins by SYNC_STAGES clk, and the oe register adds one more. An SCL-low interval is two
// ticks and the SDA-to-sample distance is at least two ticks, so a tick must comfortably exceed
// that latency. CLKDIV_MIN (default 3 -> tick = 4 clk, 2x margin over the 4-clk worst case) must be
// >= SYNC_STAGES + 1; a smaller override FAILS ELABORATION (g_clkdiv_min_check), and CLKDIV below
// CLKDIV_MIN is clamped in hardware. With the four-phase bit (see "Bit timing") the SAME bound is
// also what keeps the shortened S_BIT_HI1 reload (CLKDIV_eff - (SYNC_STAGES+1) - K) non-negative:
// at CLKDIV_eff = SYNC_STAGES + 1 it is exactly 0 (a 1-clk phase, K = 0), so the minimum is unchanged
// by the fourth phase and is tight, not conservative. The SCL-low interval is now 2N + K >= two ticks
// and the SDA-to-sample distance 2N + K - 3 >= two ticks, so the original latency argument holds.
// The bit engine receives the clamped value and does not re-check it.
// The same lesson as spi_controller.sv's SPI_CLK_DIV >= 7, but enforced rather than documented (SPI
// leaves 0..1 unsafe).
//
// Loopback (CTRL[1], SPI_CTRL[4] precedent): the sensed lines come from an internal wired-AND of
// the master's own oe with a tiny internal slave instead of from the synchronised pins; the pad
// oe_o outputs are forced 0 so a real bus is not disturbed. The slave ACKs ANY address and every
// write byte, and a read returns the LAST BYTE WRITTEN (reset 0xA5) -- write then read-back works.
// It never stretches and does not model sync latency (the mux sits AFTER the synchroniser, as in
// spi_controller.sv). It exists to make the SoC fabric test cheap; protocol coverage needs a real BFM.
//
// IRQ: irq_o = |(IRQ_STAT & IRQ_EN). LEVEL-HELD, never a pulse -- every IRQ source crosses
// core_clk -> cpu_core_clk through a plain 2-FF cdc_2ff_sync in soc_top.sv, which can miss a pulse.
//   sticky next = (q & ~clear) | set    -- a SET WINS over a same-cycle W1C, so an event is never
//   lost to a racing clear (GPIO_IRQ_STAT / trng health_fail precedent). rx_threshold is not
//   sticky: it follows the FIFO level and drops when software pops below the threshold.
//
// Reset: synchronous, active-low throughout (no `negedge rst_n`), matching the other periph/.
// Single clock domain (core_clk); the only asynchronous inputs are the two pins above.
//
// APB4 interface (ARM IHI0024C): clk/rst_n map to pclk/presetn. ADDR_W = 12 (byte address, [1:0]
// unused). Zero wait states (pready is the bank's constant 1). Writes commit on the ACCESS phase
// (psel & penable); the TX push, RX pop, CMD and IRQ_CLR snoops decode that same phase. Read-only
// registers are written by hardware with the NEXT-state value (as trng.sv), so a read one transfer
// after an event cannot see stale data.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module i2c_controller
#(
    parameter int unsigned ADDR_W     = 12,   // APB4 local address width
    parameter int unsigned CLKDIV_MIN = 3     // smallest legal CLKDIV; must be >= SYNC_STAGES + 1
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

    // =========================================================================
    // I2C pads -- open-drain triplets, NO tristate (see PAD-RING CONTRACT above)
    // =========================================================================
    output logic i2c_scl_o,       // DEAD: hard-tied 1'b0, pad-ring symmetry with GPIO only
    output logic i2c_scl_oe_o,    // 1 = drive SCL low, 0 = release (external pull-up)
    input  logic i2c_scl_i,       // sensed SCL level, ASYNCHRONOUS
    output logic i2c_sda_o,       // DEAD: hard-tied 1'b0, pad-ring symmetry with GPIO only
    output logic i2c_sda_oe_o,    // 1 = drive SDA low, 0 = release (external pull-up)
    input  logic i2c_sda_i,       // sensed SDA level, ASYNCHRONOUS

    // Interrupt -- level-held, never a pulse
    output logic irq_o
);

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned SYNC_STAGES = 2;   // cdc_2ff_sync depth used for both pins

    // Elaboration guards. A generate-scope $fatal (not wrapped in `initial`) fires at ELABORATION
    // time, under `verilator --lint-only` too (same idiom as gpio_controller.sv's g_n_pins_check).
    // 12 registers need word index 0..11 -> at least 4 word bits -> ADDR_W >= 6.
    if (ADDR_W < 6 || ADDR_W > 32) begin : g_addr_w_check
        $fatal(1, "i2c_controller: ADDR_W (%0d) must be in [6, 32]", ADDR_W);
    end
    // The prescaler minimum must exceed the synchroniser latency (see header). The upper bound keeps
    // the clamp constant inside the 16-bit CLKDIV field.
    if (CLKDIV_MIN < SYNC_STAGES + 1 || CLKDIV_MIN > 16'hFFFF) begin : g_clkdiv_min_check
        $fatal(1, "i2c_controller: CLKDIV_MIN (%0d) must be in [SYNC_STAGES+1 = %0d, 65535]: a tick must exceed the %0d-clk synchroniser latency",
               CLKDIV_MIN, SYNC_STAGES + 1, SYNC_STAGES);
    end

    localparam int unsigned REG_CTRL      = 0;
    localparam int unsigned REG_STATUS    = 1;
    localparam int unsigned REG_CLKDIV    = 2;
    localparam int unsigned REG_ADDR      = 3;
    localparam int unsigned REG_TX_DATA   = 4;
    localparam int unsigned REG_RX_DATA   = 5;
    localparam int unsigned REG_CMD       = 6;
    localparam int unsigned REG_FIFO_STAT = 7;
    localparam int unsigned REG_TIMEOUT   = 8;
    localparam int unsigned REG_IRQ_EN    = 9;
    localparam int unsigned REG_IRQ_STAT  = 10;
    localparam int unsigned REG_IRQ_CLR   = 11;
    localparam int unsigned N_REGS        = 12;

    localparam int unsigned FIFO_DEPTH = 8;

    // Word address width (mirrors apb4_register_bank's own WORDW).
    localparam int unsigned WORDW = ADDR_W - 2;

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  //  0 I2C_CTRL      RW (disabled at reset)
        32'h0000_0000,  //  1 I2C_STATUS    RO (HW-written)
        32'h0000_00FF,  //  2 I2C_CLKDIV    RW
        32'h0000_0000,  //  3 I2C_ADDR      RW
        32'h0000_0000,  //  4 I2C_TX_DATA   WO (snoop-only, reads 0)
        32'h0000_0000,  //  5 I2C_RX_DATA   RO (HW-written)
        32'h0000_0000,  //  6 I2C_CMD       WO (snoop-only, reads 0)
        32'h0000_0000,  //  7 I2C_FIFO_STAT RO (HW-written)
        32'h0000_FFFF,  //  8 I2C_TIMEOUT   RW (enabled, max)
        32'h0000_0000,  //  9 I2C_IRQ_EN    RW
        32'h0000_0000,  // 10 I2C_IRQ_STAT  RO (HW-written)
        32'h0000_0000   // 11 I2C_IRQ_CLR   WO (snoop-only, reads 0)
    };

    // WMASK: RO / WO words get 32'h0 (drop writes, read back reset value or HW value).
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_0F03,  //  0 I2C_CTRL    [11:8],[1:0] defined
        32'h0000_0000,  //  1 I2C_STATUS
        32'h0000_FFFF,  //  2 I2C_CLKDIV
        32'h0000_00FF,  //  3 I2C_ADDR
        32'h0000_0000,  //  4 I2C_TX_DATA
        32'h0000_0000,  //  5 I2C_RX_DATA
        32'h0000_0000,  //  6 I2C_CMD
        32'h0000_0000,  //  7 I2C_FIFO_STAT
        32'h0000_FFFF,  //  8 I2C_TIMEOUT
        32'h0000_001F,  //  9 I2C_IRQ_EN
        32'h0000_0000,  // 10 I2C_IRQ_STAT
        32'h0000_0000   // 11 I2C_IRQ_CLR
    };

    logic [31:0] regs_o    [N_REGS];
    logic        hw_wen_i  [N_REGS];
    logic [31:0] hw_wdata_i[N_REGS];

    // -------------------------------------------------------------------------
    // APB address decode (zero-extended to 32 b before comparing -- GH #87-safe idiom).
    // -------------------------------------------------------------------------
    logic [WORDW-1:0] addr_word_w;
    assign addr_word_w = paddr[ADDR_W-1:2];

    logic access_w;
    assign access_w = psel & penable;  // pready is a constant 1 from the bank

    logic is_tx_addr_w, is_rx_addr_w, is_cmd_addr_w, is_irq_clr_addr_w;
    assign is_tx_addr_w      = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_TX_DATA));
    assign is_rx_addr_w      = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_RX_DATA));
    assign is_cmd_addr_w     = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_CMD));
    assign is_irq_clr_addr_w = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_IRQ_CLR));

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
    // Register views
    // =========================================================================
    logic        en_w, loop_w;
    logic [3:0]  rx_thr_w;
    logic [15:0] clkdiv_w, timeout_w;
    logic [7:0]  addr_reg_w;
    logic [4:0]  irq_en_w;

    assign en_w       = regs_o[REG_CTRL][0];
    assign loop_w     = regs_o[REG_CTRL][1];
    assign rx_thr_w   = regs_o[REG_CTRL][11:8];
    assign clkdiv_w   = regs_o[REG_CLKDIV][15:0];
    assign addr_reg_w = regs_o[REG_ADDR][7:0];
    assign timeout_w  = regs_o[REG_TIMEOUT][15:0];
    assign irq_en_w   = regs_o[REG_IRQ_EN][4:0];

    // Unused register bits (reserved fields, and the words whose value is carried by the bank
    // purely for readback: the HW-written RO words, and the snoop-only WO words).
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_regs_w;
    assign unused_regs_w = ^{regs_o[REG_CTRL][31:12], regs_o[REG_CTRL][7:2],
                             regs_o[REG_STATUS], regs_o[REG_CLKDIV][31:16],
                             regs_o[REG_ADDR][31:8], regs_o[REG_TX_DATA], regs_o[REG_RX_DATA],
                             regs_o[REG_CMD], regs_o[REG_FIFO_STAT], regs_o[REG_TIMEOUT][31:16],
                             regs_o[REG_IRQ_EN][31:5], regs_o[REG_IRQ_STAT], regs_o[REG_IRQ_CLR]};
    /* verilator lint_on  UNUSEDSIGNAL */

    // Clamp: a tick must exceed the synchroniser latency (see header).
    logic [15:0] div_eff_w;
    assign div_eff_w = (clkdiv_w < 16'(CLKDIV_MIN)) ? 16'(CLKDIV_MIN) : clkdiv_w;

    // Enable-edge detect: the TX/RX FIFOs flush on the 1 -> 0 edge.
    logic en_q;
    logic en_fall_w;
    assign en_fall_w = en_q & ~en_w;

    always_ff @(posedge clk) begin
        if (!rst_n) en_q <= 1'b0;
        else        en_q <= en_w;
    end

    // =========================================================================
    // Snoops -- TX push, RX pop, CMD, IRQ_CLR (all decode the ACCESS phase)
    // =========================================================================
    function automatic logic [31:0] strb_expand(input logic [3:0] strb);
        for (int unsigned b = 0; b < 4; b++)
            strb_expand[8*b +: 8] = strb[b] ? 8'hFF : 8'h00;
    endfunction

    // The expanded strobe MUST land in a named net before being sliced (a part-select applied
    // directly to a function-call result is not legal Verilog-2005; sv2v passes it through and yosys
    // rejects it -- see trng.sv / pwm_controller.sv, fixed in 2c5f351).
    logic [31:0] strb_mask_w;
    assign strb_mask_w = strb_expand(pstrb);

    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] wdata_m_w;               // pwdata with unselected byte lanes zeroed; only some fields used
    /* verilator lint_on  UNUSEDSIGNAL */
    assign wdata_m_w = pwdata & strb_mask_w;

    logic wr_acc_w;
    assign wr_acc_w = access_w & pwrite;

    // TX push: byte 0 only (an 8-bit register in a word slot).
    logic tx_push_apb_w;
    assign tx_push_apb_w = wr_acc_w & is_tx_addr_w & pstrb[0];

    // RX pop: any read ACCESS at RX_DATA (gated by non-empty below).
    logic rx_pop_apb_w;
    assign rx_pop_apb_w = access_w & ~pwrite & is_rx_addr_w;

    // CMD fields. COUNT comes from byte 1 and reads 0 if that lane is not written.
    logic       c_wr_acc_w, c_start_w, c_write_w, c_read_w, c_stop_w, c_nack_last_w;
    logic [7:0] c_count_w;
    assign c_wr_acc_w    = wr_acc_w & is_cmd_addr_w;
    assign c_start_w     = wdata_m_w[0];
    assign c_write_w     = wdata_m_w[1];
    assign c_read_w      = wdata_m_w[2];
    assign c_stop_w      = wdata_m_w[3];
    assign c_nack_last_w = wdata_m_w[4];
    assign c_count_w     = wdata_m_w[15:8];

    // IRQ_CLR W1C bits [3:0] (honours pstrb via the masked data).
    logic [3:0] clr_w;
    assign clr_w = {4{wr_acc_w & is_irq_clr_addr_w}} & wdata_m_w[3:0];

    // =========================================================================
    // Input synchronisation -- two SEPARATE single-bit cdc_2ff_sync instances
    // =========================================================================
    logic scl_ext_s_w, sda_ext_s_w;

    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES)
    ) u_scl_sync (
        .clk_i   (clk),
        .rst_n_i (rst_n),
        .d_i     (i2c_scl_i),
        .q_o     (scl_ext_s_w)
    );

    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES)
    ) u_sda_sync (
        .clk_i   (clk),
        .rst_n_i (rst_n),
        .d_i     (i2c_sda_i),
        .q_o     (sda_ext_s_w)
    );

    // =========================================================================
    // Protocol engine -- command FSM, SCL phase generator, arbitration, timeout (i2c_bit_engine.sv).
    // Everything else in this file is the software-visible shell around it.
    // =========================================================================
    logic       scl_oe_q, sda_oe_q;        // registered open-drain controls from the engine
    logic       tx_pop_w, rx_push_w;       // engine -> FIFO strobes
    logic [7:0] rx_byte_w;                 // byte the engine pushes into the RX FIFO
    logic       done_set_w, nack_set_w, arb_set_w, tout_set_w;   // event pulses (parent owns the sticky)
    logic       busy_d_w, txn_d_w;         // engine next-state mirrors (STATUS writeback)
    logic       scl_s_w, sda_s_w;          // lines as the engine sees them (see "Lines" below)

    i2c_bit_engine #(
        .SYNC_STAGES (SYNC_STAGES)
    ) u_bit_engine (
        .clk           (clk),
        .rst_n         (rst_n),
        .en_i          (en_w),
        .div_eff_i     (div_eff_w),
        .timeout_i     (timeout_w),
        .cmd_wr_i      (c_wr_acc_w),
        .c_start_i     (c_start_w),
        .c_write_i     (c_write_w),
        .c_read_i      (c_read_w),
        .c_stop_i      (c_stop_w),
        .c_nack_last_i (c_nack_last_w),
        .c_count_i     (c_count_w),
        .addr_i        (addr_reg_w),
        .scl_s_i       (scl_s_w),
        .sda_s_i       (sda_s_w),
        .tx_empty_i    (tx_empty_w),
        .rx_full_i     (rx_full_w),
        .tx_head_i     (tx_fifo_q[0]),
        .tx_pop_o      (tx_pop_w),
        .rx_push_o     (rx_push_w),
        .rx_byte_o     (rx_byte_w),
        .scl_oe_o      (scl_oe_q),
        .sda_oe_o      (sda_oe_q),
        .done_set_o    (done_set_w),
        .nack_set_o    (nack_set_w),
        .arb_set_o     (arb_set_w),
        .tout_set_o    (tout_set_w),
        .busy_d_o      (busy_d_w),
        .txn_d_o       (txn_d_w)
    );

    // Sticky event flags
    logic done_q, nack_q, arb_q, tout_q;
    logic done_d, nack_d, arb_d, tout_d;

    // Lines -- as the engine sees them: synchronised pins, or the internal loopback wired-AND.
    logic slv_pull_q;                      // loopback slave pulling SDA low (declared early: used below)
    assign scl_s_w = loop_w ? ~scl_oe_q                  : scl_ext_s_w;
    assign sda_s_w = loop_w ? (~sda_oe_q & ~slv_pull_q)  : sda_ext_s_w;

    // Pad outputs: oe_o is the real control; `*_o` is hard-tied 0 (see PAD-RING CONTRACT). In
    // loopback the master must not disturb a real bus, so oe_o is forced released.
    assign i2c_scl_o    = 1'b0;
    assign i2c_sda_o    = 1'b0;
    assign i2c_scl_oe_o = scl_oe_q & ~loop_w;
    assign i2c_sda_oe_o = sda_oe_q & ~loop_w;

    // =========================================================================
    // FIFOs -- shift registers, head at [0], entries above `level` are always zero
    // (trng.sv idiom). TX: APB push / engine pop. RX: engine push / APB pop.
    // =========================================================================
    logic [7:0] tx_fifo_q [FIFO_DEPTH];
    logic [7:0] tx_fifo_d [FIFO_DEPTH];
    logic [7:0] rx_fifo_q [FIFO_DEPTH];
    logic [7:0] rx_fifo_d [FIFO_DEPTH];
    logic [3:0] tx_level_q, tx_level_d;
    logic [3:0] rx_level_q, rx_level_d;

    logic tx_full_w, tx_empty_w, rx_full_w, rx_empty_w;
    assign tx_full_w  = (tx_level_q == 4'(FIFO_DEPTH));
    assign tx_empty_w = (tx_level_q == 4'd0);
    assign rx_full_w  = (rx_level_q == 4'(FIFO_DEPTH));
    assign rx_empty_w = (rx_level_q == 4'd0);


    // Push / pop qualification. A TX push into a full FIFO is dropped; an RX pop on empty is a no-op.
    // RX push is never attempted on a full FIFO (S_DATA_WAIT gates on rx_full_w).
    logic tx_push_w, rx_pop_w;
    assign tx_push_w = tx_push_apb_w & ~tx_full_w;
    assign rx_pop_w  = rx_pop_apb_w & ~rx_empty_w;

    logic [3:0] tx_wr_idx_w, rx_wr_idx_w;  // slot a pushed byte lands in, after the pop shift
    assign tx_wr_idx_w = tx_pop_w ? (tx_level_q - 4'd1) : tx_level_q;
    assign rx_wr_idx_w = rx_pop_w ? (rx_level_q - 4'd1) : rx_level_q;

    always_comb begin
        for (int unsigned i = 0; i < FIFO_DEPTH; i++) begin
            if (tx_pop_w) tx_fifo_d[i] = (i + 1 < FIFO_DEPTH) ? tx_fifo_q[(i + 1) % FIFO_DEPTH] : 8'h0;
            else          tx_fifo_d[i] = tx_fifo_q[i];
            if (tx_push_w && tx_wr_idx_w == 4'(i)) tx_fifo_d[i] = pwdata[7:0];
            if (en_fall_w)                         tx_fifo_d[i] = 8'h0;

            if (rx_pop_w) rx_fifo_d[i] = (i + 1 < FIFO_DEPTH) ? rx_fifo_q[(i + 1) % FIFO_DEPTH] : 8'h0;
            else          rx_fifo_d[i] = rx_fifo_q[i];
            if (rx_push_w && rx_wr_idx_w == 4'(i)) rx_fifo_d[i] = rx_byte_w;
            if (en_fall_w)                         rx_fifo_d[i] = 8'h0;
        end

        tx_level_d = tx_level_q;
        if (en_fall_w)                    tx_level_d = 4'd0;
        else if (tx_push_w && !tx_pop_w)  tx_level_d = tx_level_q + 4'd1;
        else if (tx_pop_w && !tx_push_w)  tx_level_d = tx_level_q - 4'd1;

        rx_level_d = rx_level_q;
        if (en_fall_w)                    rx_level_d = 4'd0;
        else if (rx_push_w && !rx_pop_w)  rx_level_d = rx_level_q + 4'd1;
        else if (rx_pop_w && !rx_push_w)  rx_level_d = rx_level_q - 4'd1;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            tx_level_q <= 4'd0;
            rx_level_q <= 4'd0;
            for (int unsigned i = 0; i < FIFO_DEPTH; i++) begin
                tx_fifo_q[i] <= 8'h0;
                rx_fifo_q[i] <= 8'h0;
            end
        end else begin
            tx_level_q <= tx_level_d;
            rx_level_q <= rx_level_d;
            for (int unsigned i = 0; i < FIFO_DEPTH; i++) begin
                tx_fifo_q[i] <= tx_fifo_d[i];
                rx_fifo_q[i] <= rx_fifo_d[i];
            end
        end
    end

    // Sticky event flags: SET WINS over a same-cycle W1C clear (an event is never lost to a racing
    // clear). The engine supplies the one-clock set pulses; the flops live here with the W1C.
    always_comb begin
        done_d = (done_q & ~clr_w[0]) | done_set_w;
        nack_d = (nack_q & ~clr_w[1]) | nack_set_w;
        arb_d  = (arb_q  & ~clr_w[2]) | arb_set_w;
        tout_d = (tout_q & ~clr_w[3]) | tout_set_w;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            done_q <= 1'b0;
            nack_q <= 1'b0;
            arb_q  <= 1'b0;
            tout_q <= 1'b0;
        end else begin
            done_q <= done_d;
            nack_q <= nack_d;
            arb_q  <= arb_d;
            tout_q <= tout_d;
        end
    end

    // =========================================================================
    // Internal loopback slave (CTRL.LOOPBACK) -- simple ACKing slave on the master's own lines.
    // Sees master oe directly (in-domain, no synchroniser). ACKs any address and every write byte;
    // a read returns the last byte written. Never stretches. Modes: IDLE, ADDR, WR, RD.
    // =========================================================================
    typedef enum logic [1:0] {
        SLV_IDLE = 2'd0,
        SLV_ADDR = 2'd1,
        SLV_WR   = 2'd2,
        SLV_RD   = 2'd3
    } slv_mode_e;

    slv_mode_e   slv_mode_q;
    logic [3:0]  slv_bits_q;          // SCL rising edges seen in the current byte (0..9)
    logic [7:0]  slv_sh_q;            // address / write-data shift register
    logic [7:0]  slv_last_wr_q;       // last byte written by the master (read-back source)
    logic        slv_mnack_q;         // master NACKed the last byte the slave sent
    logic        slv_scl_q, slv_sda_q;

    logic slv_scl_w, slv_sda_w;       // loopback bus levels: wired-AND of master and slave
    assign slv_scl_w = ~scl_oe_q;
    assign slv_sda_w = ~sda_oe_q & ~slv_pull_q;

    logic slv_start_w, slv_stop_w, slv_rise_w, slv_fall_w;
    assign slv_start_w = slv_scl_w &  slv_sda_q & ~slv_sda_w;   // SDA falls while SCL high
    assign slv_stop_w  = slv_scl_w & ~slv_sda_q &  slv_sda_w;   // SDA rises while SCL high
    assign slv_rise_w  =  slv_scl_w & ~slv_scl_q;
    assign slv_fall_w  = ~slv_scl_w &  slv_scl_q;

    logic [2:0] slv_tx_idx_w;         // bit of the read byte to present after `bits` rising edges
    assign slv_tx_idx_w = 3'(4'd7 - slv_bits_q);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            slv_mode_q    <= SLV_IDLE;
            slv_bits_q    <= 4'd0;
            slv_sh_q      <= 8'h00;
            slv_last_wr_q <= 8'hA5;
            slv_mnack_q   <= 1'b0;
            slv_pull_q    <= 1'b0;
            slv_scl_q     <= 1'b1;
            slv_sda_q     <= 1'b1;
        end else begin
            slv_scl_q <= slv_scl_w;
            slv_sda_q <= slv_sda_w;

            if (!loop_w) begin
                slv_mode_q  <= SLV_IDLE;
                slv_bits_q  <= 4'd0;
                slv_mnack_q <= 1'b0;
                slv_pull_q  <= 1'b0;
            end else if (slv_start_w) begin
                slv_mode_q <= SLV_ADDR;
                slv_bits_q <= 4'd0;
                slv_pull_q <= 1'b0;
            end else if (slv_stop_w) begin
                slv_mode_q <= SLV_IDLE;
                slv_bits_q <= 4'd0;
                slv_pull_q <= 1'b0;
            end else if (slv_rise_w && slv_mode_q != SLV_IDLE) begin
                if (slv_bits_q < 4'd8) begin
                    slv_sh_q   <= {slv_sh_q[6:0], slv_sda_w};
                    slv_bits_q <= slv_bits_q + 4'd1;
                end else if (slv_bits_q == 4'd8) begin
                    slv_mnack_q <= slv_sda_w;           // master's ACK/NACK (read mode)
                    slv_bits_q  <= 4'd9;
                end
            end else if (slv_fall_w) begin
                case (slv_mode_q)
                    SLV_ADDR, SLV_WR: begin
                        if (slv_bits_q == 4'd8) begin
                            slv_pull_q <= 1'b1;         // ACK the byte
                            if (slv_mode_q == SLV_WR) slv_last_wr_q <= slv_sh_q;
                        end else if (slv_bits_q == 4'd9) begin
                            slv_bits_q <= 4'd0;
                            slv_pull_q <= 1'b0;
                            if (slv_mode_q == SLV_ADDR) begin
                                if (slv_sh_q[0]) begin
                                    slv_mode_q <= SLV_RD;
                                    slv_pull_q <= ~slv_last_wr_q[7];   // present bit 7
                                end else begin
                                    slv_mode_q <= SLV_WR;
                                end
                            end
                        end
                    end
                    SLV_RD: begin
                        if (slv_bits_q >= 4'd1 && slv_bits_q <= 4'd7) begin
                            slv_pull_q <= ~slv_last_wr_q[slv_tx_idx_w];
                        end else if (slv_bits_q == 4'd8) begin
                            slv_pull_q <= 1'b0;         // release for the master's ACK slot
                        end else if (slv_bits_q == 4'd9) begin
                            slv_bits_q <= 4'd0;
                            if (slv_mnack_q) begin
                                slv_mode_q <= SLV_IDLE;
                                slv_pull_q <= 1'b0;
                            end else begin
                                slv_pull_q <= ~slv_last_wr_q[7];       // next byte, bit 7
                            end
                        end
                    end
                    default: ;
                endcase
            end
        end
    end

    // =========================================================================
    // HW-writeback -- combinational mirror of the NEXT state, driven every cycle
    // =========================================================================
    logic [3:0] eff_thr_w;
    assign eff_thr_w = (rx_thr_w == 4'd0) ? 4'd1 : rx_thr_w;

    logic rx_thr_d_w, rx_thr_q_w;
    assign rx_thr_d_w = (rx_level_d >= eff_thr_w);
    assign rx_thr_q_w = (rx_level_q >= eff_thr_w);

    always_comb begin
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // I2C_STATUS
        hw_wen_i  [REG_STATUS] = 1'b1;
        hw_wdata_i[REG_STATUS] = {25'h0, sda_s_w, scl_s_w, tout_d, arb_d, nack_d, txn_d_w,
                                  busy_d_w};

        // I2C_RX_DATA: FIFO head (0 when empty -- entries above `level` are zero by construction).
        hw_wen_i  [REG_RX_DATA] = 1'b1;
        hw_wdata_i[REG_RX_DATA] = {24'h0, rx_fifo_d[0]};

        // I2C_FIFO_STAT
        hw_wen_i  [REG_FIFO_STAT] = 1'b1;
        hw_wdata_i[REG_FIFO_STAT] = {20'h0, (rx_level_d == 4'd0), (rx_level_d == 4'(FIFO_DEPTH)),
                                     (tx_level_d == 4'd0), (tx_level_d == 4'(FIFO_DEPTH)),
                                     rx_level_d, tx_level_d};

        // I2C_IRQ_STAT: {rx_threshold (live), timeout, arb_lost, nack, done}
        hw_wen_i  [REG_IRQ_STAT] = 1'b1;
        hw_wdata_i[REG_IRQ_STAT] = {27'h0, rx_thr_d_w, tout_d, arb_d, nack_d, done_d};
    end

    // =========================================================================
    // Interrupt -- level-held (see header)
    // =========================================================================
    assign irq_o = |({rx_thr_q_w, tout_q, arb_q, nack_q, done_q} & irq_en_w);

endmodule : i2c_controller
