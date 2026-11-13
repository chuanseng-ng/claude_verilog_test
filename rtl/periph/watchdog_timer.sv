// watchdog_timer - watchdog timer with bark, bite and window mode, APB4 slave.
//
// Function: A 32-bit down-counter runs from core_clk through a prescaler.
//   Enabling loads COUNT from RELOAD one edge after the commit edge E of the write that sets CTRL[0].
//   COUNT then falls by one per tick. Let P = PRESCALE and R = RELOAD.
//   BARK becomes visible (P+1)*R + 2 edges after E. The bark edge reloads the counter.
//   A second timeout with no valid feed is the BITE, (P+1)*R + 1 edges after the bark.
//   A valid feed reloads COUNT on its commit edge and clears the bark-to-bite escalation.
//   A feed on the edge where a timeout is detected is too late. The timeout wins.
//   Window mode (CTRL[2] = 1 and WINDOW != 0): a valid feed while COUNT > WINDOW sets STATUS[2] and does not reload.
//   A window violation never escalates to a bite by itself.
//   RELOAD = 0 while enabled fails toward firing: COUNT loads as 0, bark follows within a couple of edges and bite one edge later.
//   COUNT stays at 0 and does not underflow.
// Registers (word index, N_REGS = 8):
//   0 WDT_CTRL (RW: [0] enable, [1] RST_EN, [2] window-mode enable), 1 WDT_RELOAD (RW), 2 WDT_COUNT (RO),
//   3 WDT_WINDOW (RW, 0 disables the check), 4 WDT_FEED (WO, reads 0),
//   5 WDT_PRESCALE (RW [15:0], one tick = PRESCALE+1 core_clk cycles),
//   6 WDT_STATUS (RO, sticky: [0] bark, [1] bite, [2] window violation), 7 WDT_IRQ_CLR (WO, W1C on STATUS, reads 0).
//   Only the value 0x5A5A_C0DE with pstrb == 4'hF feeds the watchdog. Any other write to WDT_FEED is rejected.
// Parameters: ADDR_W (APB address width, default 12; the legal range is 5 to 32).
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous. The module has no CDC.
//   WDT_CTRL resets to 0, so RST_EN is off after reset. The STATUS bits set on their event and clear on W1C or reset.
// Caller rules:
//   - RELOAD writes while running are deferred. Only a feed, a bark reload or an enable loads the live counter.
//   - The bite is terminal. COUNT freezes at 0, and a later feed or enable does not revive it.
//   - wdt_rst_req_o is a separate flop from STATUS[1]. It is level-held until rst_n. A W1C of STATUS[1] does not drop it.
//   - RST_EN does not gate wdt_rst_req_o. It only arms the SoC-level CPU-domain reset AND-in in soc_top.
//   - rst_en_o exports WDT_CTRL[1] to soc_top. This module does not use it.
//   - irq_o = |STATUS[2:0]. It is level-held. There is no IRQ_EN register: masking is the interrupt_controller's job.
//   - A new bark or bite beats a same-cycle WDT_IRQ_CLR write (set wins).
//   - The counter runs from core_clk. A stuck or dead PLL cannot be barked at.
// Doc: ds:mod:watchdog-timer, tm:mod:watchdog-timer, cr:mod:watchdog-timer

module watchdog_timer
#(
    parameter int unsigned ADDR_W = 12    // APB4 local address width
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
    // Interrupt and reset request -- both level-held, never pulses
    // =========================================================================
    output logic irq_o,
    output logic wdt_rst_req_o,

    // WDT_CTRL[1] (RST_EN), exported for the SoC-level CPU-domain reset AND-in
    // in soc_top. It is NOT consumed inside this module: a bite asserts
    // wdt_rst_req_o regardless of RST_EN, and RST_EN gates only that integration
    // path. Exported as a real port because cross-module hierarchical references
    // are not synthesisable through sv2v/yosys, and the alternative -- soc_top
    // reconstructing this bit by snooping our own APB face -- is duplicated state
    // with no structural link to the register it mirrors.
    output logic rst_en_o
);

    // Elaboration-time guard: eight registers need at least 3 word-address bits, and the
    // zero-extend compares below assume ADDR_W fits in 32 bits.
    if (ADDR_W < 5 || ADDR_W > 32) begin : g_addr_w_check
        $fatal(1, "watchdog_timer: ADDR_W (%0d) must be in [5, 32]", ADDR_W);
    end

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned REG_WDT_CTRL     = 0;
    localparam int unsigned REG_WDT_RELOAD   = 1;
    localparam int unsigned REG_WDT_COUNT    = 2;
    localparam int unsigned REG_WDT_WINDOW   = 3;
    localparam int unsigned REG_WDT_FEED     = 4;
    localparam int unsigned REG_WDT_PRESCALE = 5;
    localparam int unsigned REG_WDT_STATUS   = 6;
    localparam int unsigned REG_WDT_IRQ_CLR  = 7;
    localparam int unsigned N_REGS           = 8;

    localparam logic [31:0] FEED_MAGIC = 32'h5A5A_C0DE;

    // Word address width (mirrors apb4_register_bank's own WORDW).
    localparam int unsigned WORDW = ADDR_W - 2;

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  // 0 WDT_CTRL      RW
        32'h0000_0000,  // 1 WDT_RELOAD    RW
        32'h0000_0000,  // 2 WDT_COUNT     RO (HW-written)
        32'h0000_0000,  // 3 WDT_WINDOW    RW
        32'h0000_0000,  // 4 WDT_FEED      WO (snoop-only, reads 0)
        32'h0000_0000,  // 5 WDT_PRESCALE  RW
        32'h0000_0000,  // 6 WDT_STATUS    RO (HW-written)
        32'h0000_0000   // 7 WDT_IRQ_CLR   WO (snoop-only, reads 0)
    };

    // WMASK: RO / WO words get 32'h0. FEED and IRQ_CLR are acted on purely by the write-snoop
    // below and are never storage; COUNT/STATUS are HW-owned.
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_0007,  // 0 WDT_CTRL     [2:0] defined
        32'hFFFF_FFFF,  // 1 WDT_RELOAD
        32'h0000_0000,  // 2 WDT_COUNT
        32'hFFFF_FFFF,  // 3 WDT_WINDOW
        32'h0000_0000,  // 4 WDT_FEED
        32'h0000_FFFF,  // 5 WDT_PRESCALE [15:0] defined
        32'h0000_0000,  // 6 WDT_STATUS
        32'h0000_0000   // 7 WDT_IRQ_CLR
    };

    logic [31:0] regs_o    [N_REGS];
    logic        hw_wen_i  [N_REGS];
    logic [31:0] hw_wdata_i[N_REGS];

    // APB address decode. The compares zero-extend addr_word to 32 bits.
    logic [WORDW-1:0] addr_word_w;
    assign addr_word_w = paddr[ADDR_W-1:2];

    logic access_w;
    assign access_w = psel & penable;  // pready is a constant 1 from the bank

    logic is_feed_addr_w, is_irq_clr_addr_w, is_ro_addr_w;
    assign is_feed_addr_w    = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_WDT_FEED));
    assign is_irq_clr_addr_w = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_WDT_IRQ_CLR));
    assign is_ro_addr_w      = ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_WDT_COUNT)) ||
                               ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_WDT_STATUS));

    // Stores to COUNT and STATUS are shown to the bank as reads. See cr:mod:watchdog-timer.
    logic bank_pwrite_w;
    assign bank_pwrite_w = pwrite & ~is_ro_addr_w;

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
        .pwrite     (bank_pwrite_w),
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
    logic        en_w, win_en_w;
    logic [31:0] reload_w, window_w, cnt_w;
    logic [15:0] presc_cfg_w;
    logic [2:0]  stat_w;

    // CTRL[1] (RST_EN) is stored and read back, but consumed only by the SoC-level reset AND-in
    // in soc_top (a later integration step); nothing in this module reads it.
    logic rst_en_w;
    assign en_w        = regs_o[REG_WDT_CTRL][0];
    assign rst_en_w    = regs_o[REG_WDT_CTRL][1];
    // Exported rather than stranded: the UNUSEDSIGNAL waiver this declaration
    // used to carry existed only because rst_en_w had no way out of the module.
    assign rst_en_o    = rst_en_w;
    assign win_en_w    = regs_o[REG_WDT_CTRL][2];
    assign reload_w    = regs_o[REG_WDT_RELOAD];
    assign window_w    = regs_o[REG_WDT_WINDOW];
    assign presc_cfg_w = regs_o[REG_WDT_PRESCALE][15:0];
    assign cnt_w       = regs_o[REG_WDT_COUNT];
    assign stat_w      = regs_o[REG_WDT_STATUS][2:0];

    // =========================================================================
    // Control state
    // =========================================================================
    logic [15:0] presc_q, presc_next_w;   // prescaler phase, counts 0 .. PRESCALE
    logic        en_q;                    // CTRL[0] one cycle ago: enable-edge detect
    logic        esc_q, esc_next_w;       // bark already raised: this is the second period
    logic        bite_q;                  // terminal bite latch == wdt_rst_req_o

    // Running: enabled, past the enable-load edge, and not bitten. Gates every event.
    logic running_w, load_w;
    assign running_w = en_w & en_q & ~bite_q;
    assign load_w    = en_w & ~en_q & ~bite_q;

    // Registered timeout detection: COUNT has reached 0 while running. State-based (no tick
    // needed), so RELOAD == 0 is expired immediately and cannot hang or underflow.
    logic expired_w;
    assign expired_w = running_w & (cnt_w == 32'h0);

    // Prescaler tick. `>=` rather than `==` so lowering PRESCALE below the live phase
    // self-corrects on the next cycle instead of missing the compare.
    logic tick_w;
    assign tick_w = running_w & (presc_q >= presc_cfg_w);

    // =========================================================================
    // FEED write-snoop -- magic value AND full word strobe (a byte-strobed store carrying part of
    // the magic must not pet the dog).
    // =========================================================================
    logic feed_valid_w;
    assign feed_valid_w = access_w & pwrite & is_feed_addr_w &
                          (pwdata == FEED_MAGIC) & (pstrb == 4'hF);

    logic window_active_w, window_closed_w;
    assign window_active_w = win_en_w & (window_w != 32'h0);
    assign window_closed_w = window_active_w & (cnt_w > window_w);

    logic feed_ok_w, violation_w;
    assign feed_ok_w   = feed_valid_w & running_w & ~window_closed_w;
    assign violation_w = feed_valid_w & running_w & window_closed_w;

    // =========================================================================
    // Counter / escalation next-state. Priority: enable-load > timeout > feed > tick.
    // =========================================================================
    logic [31:0] cnt_next_w;
    logic        set_bark_w, set_bite_w;

    always_comb begin
        cnt_next_w   = cnt_w;
        presc_next_w = running_w ? presc_q + 16'h1 : 16'h0;
        esc_next_w   = esc_q;
        set_bark_w   = 1'b0;
        set_bite_w   = 1'b0;

        if (load_w) begin
            cnt_next_w   = reload_w;
            presc_next_w = 16'h0;
            esc_next_w   = 1'b0;
        end else if (expired_w) begin
            if (esc_q) begin
                // Second period ran out with no valid feed: bite. COUNT is already 0.
                set_bite_w = 1'b1;
            end else begin
                // First timeout: bark, reload, start the second full period.
                set_bark_w   = 1'b1;
                cnt_next_w   = reload_w;
                presc_next_w = 16'h0;
                esc_next_w   = 1'b1;
            end
        end else if (feed_ok_w) begin
            cnt_next_w   = reload_w;
            presc_next_w = 16'h0;
            esc_next_w   = 1'b0;
        end else if (tick_w) begin
            // expired_w is false here, so cnt_w != 0: no underflow.
            cnt_next_w   = cnt_w - 32'h1;
            presc_next_w = 16'h0;
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            presc_q <= 16'h0;
            en_q    <= 1'b0;
            esc_q   <= 1'b0;
            bite_q  <= 1'b0;
        end else begin
            presc_q <= presc_next_w;
            en_q    <= en_w;
            esc_q   <= esc_next_w;
            if (set_bite_w)
                bite_q <= 1'b1;   // level-held until rst_n; not clearable by W1C or feed
        end
    end

    // =========================================================================
    // WDT_IRQ_CLR write-snoop -- one-cycle clear mask.
    // =========================================================================
    // strb_expand: byte-strobe to bit-mask expansion, copied verbatim from apb4_register_bank.sv
    // / gpio_controller.sv / pwm_controller.sv so the clear honours partial-word writes exactly
    // like the register bank's own SW-write path.
    function automatic logic [31:0] strb_expand(input logic [3:0] strb);
        for (int unsigned b = 0; b < 4; b++)
            strb_expand[8*b +: 8] = strb[b] ? 8'hFF : 8'h00;
    endfunction

    // The expanded strobe MUST land in a named net before being sliced. A part-select applied
    // directly to a function-call result is legal SystemVerilog and accepted by Verilator but NOT
    // legal Verilog-2005: sv2v passes it through verbatim and yosys rejects the generated file.
    // See pwm_controller.sv (fixed in 2c5f351) for the full story.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] strb_mask_w;
    /* verilator lint_on  UNUSEDSIGNAL */
    assign strb_mask_w = strb_expand(pstrb);

    logic [2:0] clr_w;
    assign clr_w = (access_w & pwrite & is_irq_clr_addr_w) ?
                   (pwdata[2:0] & strb_mask_w[2:0]) : 3'b000;

    // STATUS next-state: sticky, SET WINS over a same-cycle clear (see ds:mod:watchdog-timer).
    logic [2:0] set_w, stat_next_w;
    assign set_w       = {violation_w, set_bite_w, set_bark_w};
    assign stat_next_w = (stat_w & ~clr_w) | set_w;

    // =========================================================================
    // HW-writeback -- combinational mirror driven every cycle
    // =========================================================================
    always_comb begin
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // WDT_COUNT: the live down-counter lives in the bank (RO to software).
        hw_wen_i  [REG_WDT_COUNT] = 1'b1;
        hw_wdata_i[REG_WDT_COUNT] = cnt_next_w;

        // WDT_STATUS: sticky pending bits (RO -- HW owns this).
        hw_wen_i  [REG_WDT_STATUS] = 1'b1;
        hw_wdata_i[REG_WDT_STATUS] = 32'(stat_next_w);
    end

    // =========================================================================
    // Outputs -- both level-held (see ds:mod:watchdog-timer).
    // =========================================================================
    assign irq_o         = |stat_w;
    assign wdt_rst_req_o = bite_q;

endmodule : watchdog_timer
