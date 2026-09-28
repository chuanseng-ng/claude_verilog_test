// pwm_controller.sv
// Phase 6a-2 -- Pulse-width modulation controller, APB4 slave (bead claude_verilog_test-f7vs.6,
// docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6a-2 -- PWM"). Written to the pre-committed contract in
// tb/cocotb/soc/test_pwm.py (that suite's module docstring is the authoritative spec; this header
// summarises it).
//
// Register map (word indices into the apb4_register_bank, N_REGS=8):
//   0  PWM_CTRL       RW   [3:0] per-channel enable, [7:4] per-channel output polarity
//                           (polarity: 0 = active-high, 1 = inverted)
//   1  PWM_PERIOD     RW   [15:0] shared period, in prescaled ticks (ALL channels share it --
//                           a per-channel period would be 4x the registers for no real benefit,
//                           and a shared period is what makes multi-channel phase relationships
//                           meaningful; see docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7)
//   2  PWM_PRESCALE   RW   [15:0] core_clk divider; one tick = (PRESCALE+1) core_clk cycles
//   3  PWM_DUTY01     RW   [15:0] ch0 duty, [31:16] ch1 duty (prescaled ticks)
//   4  PWM_DUTY23     RW   [15:0] ch2 duty, [31:16] ch3 duty (prescaled ticks)
//   5  PWM_IRQ_EN     RW   [3:0] per-channel period-wrap IRQ enable -- masks irq_o ONLY
//   6  PWM_IRQ_STAT   RO   [3:0] sticky per-channel period-wrap (HW-written)
//   7  PWM_IRQ_CLR    W1C  APB-write-snoop clear against PWM_IRQ_STAT; always reads 0
//
// Timing contract: a shared 16-bit tick counter counts 0 .. PERIOD-1 and wraps back to 0 (the
// period-wrap event) once every (PRESCALE+1) core_clk cycles. Channel ch's active condition is
// (tick_count < DUTY[ch]) while ch is enabled; pwm_o[ch] = active_condition ^ PWM_CTRL[4+ch]
// (polarity=0 drives pwm_o=1 during the active window, polarity=1 is the exact complement).
// Left/edge-aligned only -- no centre-alignment, no dead-time (both explicit non-goals: centre-
// alignment needs an up/down counter and only earns its keep alongside dead-time, which itself
// implies complementary output pairs and a shoot-through safety story no consumer here has).
//
// Three corner cases, all a defined decision rather than an accident (test_pwm.py's module
// docstring specifies these; this RTL matches it):
//   DUTY == 0        : true 0% -- tick_count (unsigned, >= 0) can never be < 0, so the active
//                       condition is false for every value of tick_count. No special-case logic
//                       needed; it falls out of the compare itself, with no one-cycle glitch.
//   DUTY >= PERIOD    : true 100% -- tick_count ranges 0 .. PERIOD-1, so tick_count < DUTY holds
//                       for the whole range, INCLUDING the exact wrap instant (tick_count goes
//                       PERIOD-1 -> 0, both satisfy the compare) -- the active condition's value
//                       never changes at the wrap boundary, so there is no one-tick glitch there
//                       either. Again falls out of the same compare with no special case.
//   PERIOD == 0       : no valid period exists. Explicitly forced: the active condition carries
//                       an unconditional (period != 0) term, so pwm_o holds its inactive level;
//                       and the tick/wrap counters are held at 0 whenever period==0 (see the
//                       always_ff below), so a period-wrap event can structurally never fire and
//                       no IRQ is ever generated. This avoids both an output glitch and a
//                       spurious/runaway interrupt storm from an otherwise ill-defined compare
//                       against a free-running counter.
//
// A channel's enable/duty/polarity fields (PWM_CTRL[c]/[4+c], PWM_DUTYxx) are only physically
// representable for channel indices < MAP_CH (4, given the fixed nibble/half-word register
// layout above -- 2 duty registers x 2 half-words = 4 channels' worth of duty storage, and an
// 8-bit CTRL field split 4+4). The elaboration guard below accepts N_CH up to 8 (matching the
// generic-component convention used throughout rtl/periph/), but only channels 0..MAP_CH-1 are
// ever wired to real register bits; any channel index >= MAP_CH (reachable only when N_CH > 4,
// not exercised by test_pwm.py, which always uses the N_CH=4 default) is permanently disabled
// with duty forced to 0 -- there is no register space in this map to control it.
//
// A disabled channel (PWM_CTRL[ch]==0) drives its inactive level continuously (its active
// condition is forced false regardless of DUTY) and its PWM_IRQ_STAT bit never accumulates a
// period-wrap event, regardless of DUTY -- a real datapath/status gate, not merely an irq_o mask
// (contrast PWM_IRQ_EN, which gates irq_o only; PWM_IRQ_STAT keeps accumulating for an enabled
// channel even with its own IRQ_EN bit clear).
//
// PWM_IRQ_STAT update (HW-written every cycle), sticky per channel:
//   stat = (stat & ~clr) | wrap_event   where wrap_event[ch] = enabled[ch] & period_wrap_this_cycle
// SET WINS over CLEAR on a same-cycle collision -- a PWM_IRQ_CLR write whose ACCESS-phase commit
// edge lands the same cycle a fresh period-wrap is captured leaves the bit SET, mirroring
// gpio_controller.sv's identical edge-sticky formula (and proven set-beats-clear test pattern).
//
// irq_o = |(PWM_IRQ_STAT & PWM_IRQ_EN) -- LEVEL-HELD, never a single-cycle pulse. Required, not
// stylistic: every IRQ source feeding interrupt_controller crosses core_clk -> cpu_core_clk
// through a plain 2-FF cdc_2ff_sync at rtl/soc/soc_top.sv:637-644, which can only safely observe
// a level held for multiple destination-clock cycles -- a single-cycle pulse could be missed
// entirely. PWM_IRQ_STAT's stickiness (it stays 1 until a PWM_IRQ_CLR write with no coincident
// fresh wrap) is what makes irq_o level-held.
//
// No CDC at all: pwm_o is a push-pull output with no oe and no asynchronous input pin -- unlike
// gpio_controller.sv, this module has nothing to synchronise. The `-to` false path this implies
// at the top-level SDC (mirroring the uart_tx_o convention) is an integration-level concern, out
// of scope here.
//
// Reset: synchronous, active-low throughout -- `always_ff @(posedge clk) if (!rst_n) ... else
// ...`, no `negedge rst_n` in any sensitivity list. Matches gpio_controller.sv / timer.sv /
// spi_controller.sv and the rest of rtl/periph/'s uniform synchronous-reset discipline (the
// mismatch against the async-reset rtl/soc/cdc/* primitives is why the lint target below carries
// -Wno-SYNCASYNCNET).
//
// APB4 interface (ARM IHI0024C):
//   clk/rst_n map straight through (pclk=clk, presetn=rst_n) -- matching gpio_controller.sv's
//   convention, not apb4_register_bank's own pclk/presetn port names.
//   ADDR_W = 12 (byte address; [1:0] unused, word-aligned).
//   Zero wait states: pready driven 1 every ACCESS phase (apb4_register_bank's own behaviour).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module pwm_controller
#(
    parameter int unsigned ADDR_W = 12,   // APB4 local address width
    parameter int unsigned N_CH   = 4     // number of PWM channels (1 <= N_CH <= 8)
) (
    input  logic clk,
    input  logic rst_n,

    // =========================================================================
    // APB4 slave — control/status registers
    // pclk = clk, presetn = rst_n (active-low).
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
    // PWM channel outputs — push-pull only, no oe, no async input, no CDC.
    // =========================================================================
    output logic [N_CH-1:0] pwm_o,

    // =========================================================================
    // Interrupt output
    // =========================================================================
    output logic irq_o
);

    // Elaboration-time guard (IEEE 1800-2017 §20.11): $fatal directly inside a generate scope,
    // not wrapped in `initial`, fires at ELABORATION time -- under `verilator --lint-only` too.
    // Mirrors rtl/soc/cdc/cdc_2ff_sync.sv's g_stages_check and gpio_controller.sv:137-139.
    if (N_CH == 0 || N_CH > 8) begin : g_n_ch_check
        $fatal(1, "pwm_controller: N_CH (%0d) must be in [1, 8]", N_CH);
    end

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned REG_PWM_CTRL     = 0;
    localparam int unsigned REG_PWM_PERIOD   = 1;
    localparam int unsigned REG_PWM_PRESCALE = 2;
    localparam int unsigned REG_PWM_DUTY01   = 3;
    localparam int unsigned REG_PWM_DUTY23   = 4;
    localparam int unsigned REG_PWM_IRQ_EN   = 5;
    localparam int unsigned REG_PWM_IRQ_STAT = 6;
    localparam int unsigned REG_PWM_IRQ_CLR  = 7;
    localparam int unsigned N_REGS           = 8;

    // Word address width (mirrors apb4_register_bank's own WORDW).
    localparam int unsigned WORDW = ADDR_W - 2;

    // MAP_CH: channels actually representable by this fixed 8-register/32-bit map (see header).
    localparam int unsigned MAP_CH = (N_CH > 4) ? 4 : N_CH;

    // Implemented-channel mask, MAP_CH-wide. Idiom mirrored from interrupt_controller.sv:78 /
    // gpio_controller.sv:160 (GH #87-safe width-cast: MAP_CH==32 case never arises here, but the
    // idiom is kept identical for consistency).
    localparam logic [31:0] CH_MASK = 32'(({32{1'b1}} >> (32 - MAP_CH)));

    // Per-half-word duty write masks: a duty half-word is SW-writable only if its channel is
    // within MAP_CH.
    localparam logic [15:0] DUTY_CH0_MASK = (MAP_CH >= 1) ? 16'hFFFF : 16'h0000;
    localparam logic [15:0] DUTY_CH1_MASK = (MAP_CH >= 2) ? 16'hFFFF : 16'h0000;
    localparam logic [15:0] DUTY_CH2_MASK = (MAP_CH >= 3) ? 16'hFFFF : 16'h0000;
    localparam logic [15:0] DUTY_CH3_MASK = (MAP_CH >= 4) ? 16'hFFFF : 16'h0000;

    // CTRL write mask: enable bits [MAP_CH-1:0], polarity bits [MAP_CH+3:4].
    localparam logic [31:0] CTRL_WMASK = CH_MASK | (CH_MASK << 4);

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  // 0 PWM_CTRL      RW
        32'h0000_0000,  // 1 PWM_PERIOD    RW
        32'h0000_0000,  // 2 PWM_PRESCALE  RW
        32'h0000_0000,  // 3 PWM_DUTY01    RW
        32'h0000_0000,  // 4 PWM_DUTY23    RW
        32'h0000_0000,  // 5 PWM_IRQ_EN    RW
        32'h0000_0000,  // 6 PWM_IRQ_STAT  RO (HW-written)
        32'h0000_0000   // 7 PWM_IRQ_CLR   W1C (always reads 0)
    };

    // WMASK: IRQ_STAT/IRQ_CLR are RO/HW-owned from the register bank's point of view (IRQ_CLR is
    // cleared purely by the APB write-snoop below, never via the normal WMASK-gated SW-write
    // path); the rest are SW-writable up to the implemented-channel mask.
    localparam logic [31:0] WMASK [N_REGS] = '{
        CTRL_WMASK,                        // 0 PWM_CTRL
        32'h0000_FFFF,                     // 1 PWM_PERIOD
        32'h0000_FFFF,                     // 2 PWM_PRESCALE
        {DUTY_CH1_MASK, DUTY_CH0_MASK},     // 3 PWM_DUTY01
        {DUTY_CH3_MASK, DUTY_CH2_MASK},     // 4 PWM_DUTY23
        CH_MASK,                           // 5 PWM_IRQ_EN
        32'h0000_0000,                     // 6 PWM_IRQ_STAT
        32'h0000_0000                      // 7 PWM_IRQ_CLR (snoop-only, never regbank-SW-writable)
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
    // Shared prescaler / tick / period counters.
    // Synchronous reset (see header). `>=` comparisons rather than `==` so a
    // dynamic PRESCALE/PERIOD change (e.g. lowering PRESCALE below the current
    // count) self-corrects on the next cycle instead of missing its compare and
    // locking up (test_pwm_prescaler_change_mid_period).
    // =========================================================================
    logic [15:0] period_w, prescale_w;
    assign period_w   = regs_o[REG_PWM_PERIOD][15:0];
    assign prescale_w = regs_o[REG_PWM_PRESCALE][15:0];

    logic [15:0] prescale_cnt_q, tick_count_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            prescale_cnt_q <= 16'h0;
            tick_count_q   <= 16'h0;
        end else if (period_w == 16'h0) begin
            // PERIOD==0: hold both counters at 0 -- no tick, no wrap, ever (see header).
            prescale_cnt_q <= 16'h0;
            tick_count_q   <= 16'h0;
        end else if (prescale_cnt_q >= prescale_w) begin
            prescale_cnt_q <= 16'h0;
            if (tick_count_q >= period_w - 16'h1)
                tick_count_q <= 16'h0;
            else
                tick_count_q <= tick_count_q + 16'h1;
        end else begin
            prescale_cnt_q <= prescale_cnt_q + 16'h1;
        end
    end

    // tick_fire_w: a tick occurs this cycle. wrap_fire_w: this tick wraps the period back to 0.
    // Both combinational off the CURRENT (pre-update) counter state, matching the values used by
    // the active-condition compare below.
    logic tick_fire_w, wrap_fire_w;
    assign tick_fire_w = (period_w != 16'h0) && (prescale_cnt_q >= prescale_w);
    assign wrap_fire_w = tick_fire_w && (tick_count_q >= (period_w - 16'h1));

    // =========================================================================
    // Per-channel decode — enable/polarity/duty, mapped only for c < MAP_CH
    // (see header). Channels >= MAP_CH (only reachable if N_CH > 4) are
    // permanently disabled with duty tied to 0 -- no register space exists for
    // them in this fixed map.
    // =========================================================================
    logic [N_CH-1:0] enabled_w, polarity_w;
    logic [15:0]      duty_w [N_CH];

    genvar c;
    generate
        for (c = 0; c < N_CH; c++) begin : g_ch_decode
            if (c < 4) begin : g_mapped
                assign enabled_w[c]  = regs_o[REG_PWM_CTRL][c];
                assign polarity_w[c] = regs_o[REG_PWM_CTRL][4+c];
                if (c < 2) begin : g_duty01
                    assign duty_w[c] = regs_o[REG_PWM_DUTY01][16*c +: 16];
                end else begin : g_duty23
                    assign duty_w[c] = regs_o[REG_PWM_DUTY23][16*(c-2) +: 16];
                end
            end else begin : g_unmapped
                assign enabled_w[c]  = 1'b0;
                assign polarity_w[c] = 1'b0;
                assign duty_w[c]     = 16'h0;
            end
        end
    endgenerate

    // =========================================================================
    // Active condition + output drive — see header for the duty==0 / duty>=period
    // / period==0 corner cases, all of which fall directly out of this compare.
    // =========================================================================
    logic [N_CH-1:0] active_cond_w;
    generate
        for (c = 0; c < N_CH; c++) begin : g_active
            assign active_cond_w[c] =
                enabled_w[c] && (period_w != 16'h0) && (tick_count_q < duty_w[c]);
        end
    endgenerate

    assign pwm_o = N_CH'(active_cond_w ^ polarity_w);

    // =========================================================================
    // PWM_IRQ_CLR write-snoop — one-cycle clear mask.
    // Address-compare zero-extends addr_word to 32 b before comparing (GH #87
    // truncation-safe idiom, mirrored verbatim from apb4_register_bank.sv /
    // gpio_controller.sv:277-289) so N_REGS == 2**WORDW can never wrap a valid
    // index to a false match.
    // =========================================================================
    logic [WORDW-1:0] addr_word_w;
    assign addr_word_w = paddr[ADDR_W-1:2];

    logic access_w;
    assign access_w = psel & penable;  // pready is a constant 1 from the bank

    logic is_irq_clr_addr_w;
    assign is_irq_clr_addr_w =
        ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_PWM_IRQ_CLR));

    // strb_expand: byte-strobe to bit-mask expansion, copied verbatim from
    // apb4_register_bank.sv / gpio_controller.sv so the clear mask honours
    // partial-word writes exactly like the register bank's own SW-write path.
    function automatic logic [31:0] strb_expand(input logic [3:0] strb);
        for (int unsigned b = 0; b < 4; b++)
            strb_expand[8*b +: 8] = strb[b] ? 8'hFF : 8'h00;
    endfunction

    // Sliced to N_CH bits directly (rather than a full 32-bit temp) -- PWM_IRQ_STAT/CLR only
    // ever carry N_CH meaningful bits, and a 32-bit clr_w would leave bits [31:N_CH] structurally
    // unused, which Verilator -Wall flags (UNUSEDSIGNAL).
    logic [N_CH-1:0] clr_w;
    assign clr_w = (access_w && pwrite && is_irq_clr_addr_w) ?
                   (pwdata[N_CH-1:0] & strb_expand(pstrb)[N_CH-1:0]) : {N_CH{1'b0}};

    // =========================================================================
    // PWM_IRQ_STAT next-state — sticky per channel, SET WINS over a same-cycle
    // CLEAR (see header).
    // =========================================================================
    logic [N_CH-1:0] wrap_event_w, stat_q_w, stat_next_w;
    assign wrap_event_w = enabled_w & {N_CH{wrap_fire_w}};
    assign stat_q_w      = regs_o[REG_PWM_IRQ_STAT][N_CH-1:0];
    assign stat_next_w   = (stat_q_w & ~clr_w) | wrap_event_w;

    // =========================================================================
    // HW-writeback — combinational mirror driven every cycle
    // =========================================================================
    always_comb begin
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // PWM_IRQ_STAT: sticky raw pending (RO — HW owns this)
        hw_wen_i  [REG_PWM_IRQ_STAT] = 1'b1;
        hw_wdata_i[REG_PWM_IRQ_STAT] = 32'(stat_next_w);
    end

    // =========================================================================
    // IRQ output — level-held (see header rationale).
    // =========================================================================
    assign irq_o = |(regs_o[REG_PWM_IRQ_STAT] & regs_o[REG_PWM_IRQ_EN]);

endmodule : pwm_controller
