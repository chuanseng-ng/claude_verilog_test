// pwm_controller - pulse-width modulation controller, APB4 slave, N_CH channels (default 4).
//
// Function: A shared tick counter advances once every (PRESCALE+1) core_clk cycles and counts 0 .. PERIOD-1.
//   It wraps to 0 every PERIOD ticks (the period-wrap event).
//   Channel ch is active while it is enabled and tick_count < DUTY[ch]. pwm_o[ch] = active ^ CTRL[4+ch].
//   The output is left-aligned only. There is no centre alignment and no dead time.
//   pwm_o is push-pull with no oe and no asynchronous input. The module has no CDC.
// Registers (word index, N_REGS = 8):
//   0 CTRL (RW: [3:0] channel enable, [7:4] polarity, 0 = active-high), 1 PERIOD (RW, shared, in prescaled ticks),
//   2 PRESCALE (RW, one tick = PRESCALE+1 core_clk cycles), 3 DUTY01 (RW: [15:0] ch0, [31:16] ch1),
//   4 DUTY23 (RW: ch2, ch3), 5 IRQ_EN (RW, masks irq_o only), 6 IRQ_STAT (RO, sticky per-channel period wrap),
//   7 IRQ_CLR (W1C, reads 0).
//   DUTY == 0 gives a true 0 percent output. DUTY >= PERIOD gives a true 100 percent output.
//   PERIOD == 0 holds pwm_o inactive and the counters at 0, so no period wrap and no IRQ occur.
//   A disabled channel drives its inactive level and never sets its IRQ_STAT bit.
//   An enabled channel sets its IRQ_STAT bit on each period wrap. It clears on IRQ_CLR or reset.
//   A new period wrap beats a same-cycle IRQ_CLR write (set wins).
// Parameters: ADDR_W (APB address width, default 12), N_CH (1 to 8, default 4; other values are an elaboration $fatal).
//   Only channels 0 to 3 have register bits. A channel index of 4 or more is permanently disabled with duty 0.
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous (pclk = clk, presetn = rst_n).
// Caller rules:
//   - irq_o = |(IRQ_STAT & IRQ_EN). It is level-held, never a single-cycle pulse.
//   - The consumer synchroniser in soc_top needs a level that stays asserted for several cycles.
//   - APB access has zero wait states. pready is 1 in every ACCESS phase.
//   - A -to false path at the top-level SDC for pwm_o is an integration concern.
// Doc: ds:mod:pwm-controller, tm:mod:pwm-controller

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

    // Elaboration guard. A $fatal in a generate scope fires at elaboration, also under `verilator --lint-only`.
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

    // MAP_CH: channels actually representable by this fixed 8-register/32-bit map (see ds:mod:pwm-controller).
    localparam int unsigned MAP_CH = (N_CH > 4) ? 4 : N_CH;

    // Implemented-channel mask, MAP_CH-wide. The width cast keeps MAP_CH == 32 from truncating to 0.
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
    // Synchronous reset (see ds:mod:pwm-controller). `>=` comparisons rather than `==` so a
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
            // PERIOD==0: hold both counters at 0 -- no tick, no wrap, ever (see ds:mod:pwm-controller).
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
    // (see ds:mod:pwm-controller). Channels >= MAP_CH (only reachable if N_CH > 4) are
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
    // Active condition + output drive — see ds:mod:pwm-controller for the duty==0 / duty>=period
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

    // PWM_IRQ_CLR write-snoop: a one-cycle clear mask.
    // The address compare zero-extends addr_word to 32 bits, so N_REGS == 2**WORDW cannot wrap a valid index.
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

    // The expanded strobe must land in a named net before it is sliced.
    // A part-select applied directly to a function call is not legal Verilog-2005. sv2v passes it through and yosys rejects it.
    // The 32-bit temp needs a local UNUSEDSIGNAL waiver for bits [31:N_CH].
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] strb_mask_w;
    /* verilator lint_on  UNUSEDSIGNAL */
    assign strb_mask_w = strb_expand(pstrb);

    logic [N_CH-1:0] clr_w;
    assign clr_w = (access_w && pwrite && is_irq_clr_addr_w) ?
                   (pwdata[N_CH-1:0] & strb_mask_w[N_CH-1:0]) : {N_CH{1'b0}};

    // =========================================================================
    // PWM_IRQ_STAT next-state — sticky per channel, SET WINS over a same-cycle
    // CLEAR (see ds:mod:pwm-controller).
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
    // IRQ output — level-held (see ds:mod:pwm-controller).
    // =========================================================================
    assign irq_o = |(regs_o[REG_PWM_IRQ_STAT] & regs_o[REG_PWM_IRQ_EN]);

endmodule : pwm_controller
