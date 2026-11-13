// gpio_controller - GPIO controller, APB4 slave, with per-pin level and edge interrupts.
//
// Function: The pins form a unidirectional triplet: gpio_out_o (drive value), gpio_oe_o (1 = drive)
//   and gpio_in_i (sensed level). There is no tristate. Merging the triplet into a pad is pad-ring work.
//   gpio_in_i is asynchronous. N_PINS single-bit cdc_sync instances synchronise it, one per pin.
// Registers (word index; the full map is in ds:mod):
//   0 DATA_IN (RO, synchronised pin levels), 1 DATA_OUT (RW), 2 DIR (RW, 1 = output),
//   3 IRQ_EN (RW, masks irq_o only), 4 IRQ_TYPE (RW, 0 level, 1 edge),
//   5 IRQ_POL (RW, 0 active-low or falling, 1 active-high or rising),
//   6 IRQ_STAT (RO, raw pending), 7 IRQ_CLR (W1C, edge pins only, reads 0).
//   Only the low N_PINS bits of the RW registers are writable. An unimplemented pin cannot source an event.
//   IRQ_STAT is live for a level pin. For an edge pin it sets on the edge and clears on IRQ_CLR or reset; a new edge beats a same-cycle clear.
//   IRQ_CLR has no effect on a level pin. Remove the condition at the source, or mask it in IRQ_EN.
// Parameters: ADDR_W (APB address width, default 12), N_PINS (1 to 32, default 32; other values are an
//   elaboration $fatal), SYNC_STAGES (gpio_in_i synchroniser depth, at least 2, default 2).
// Clocks and resets: clk is the only clock. rst_n is active low and synchronous (pclk = clk, presetn = rst_n).
//   After reset DIR = 0 (all inputs), DATA_OUT = 0, IRQ_TYPE = 0 (level), IRQ_POL = 0 (active-low) and IRQ_EN = 0 (masked).
// Caller rules:
//   - irq_o = |(IRQ_STAT & IRQ_EN). It is level-held, never a single-cycle pulse.
//   - The consumer synchroniser in soc_top needs a level that stays asserted for several cycles.
//   - Software clears an edge interrupt with IRQ_CLR. A level interrupt follows the pin.
//   - APB access has zero wait states. pready is 1 in every ACCESS phase.
// Full contract: ds:mod:gpio-controller
// Doc: ds:mod:gpio-controller, tm:mod:gpio-controller

module gpio_controller
#(
    parameter int unsigned ADDR_W      = 12,  // APB4 local address width
    parameter int unsigned N_PINS      = 32,  // number of implemented GPIO pins (<= 32)
    parameter int unsigned SYNC_STAGES = 2    // gpio_in_i synchroniser depth (>= 2, bead xtaa)
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
    // GPIO pins — unidirectional triplet (no tristate in this repo; the
    // pad-level bidirectional merge is an integration/pad-ring concern)
    // =========================================================================
    output logic [N_PINS-1:0] gpio_out_o,
    output logic [N_PINS-1:0] gpio_oe_o,   // 1 = drive output
    input  logic [N_PINS-1:0] gpio_in_i,   // asynchronous external pins

    // =========================================================================
    // Interrupt output
    // =========================================================================
    output logic irq_o
);

    // Elaboration guard. A $fatal in a generate scope fires at elaboration, also under `verilator --lint-only`.
    // N_PINS must be in [1, 32]. N_PINS == 0 would make every [N_PINS-1:0] select a [-1:0] range.
    if (N_PINS == 0 || N_PINS > 32) begin : g_n_pins_check
        $fatal(1, "gpio_controller: N_PINS (%0d) must be in [1, 32]", N_PINS);
    end

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned REG_GPIO_DATA_IN  = 0;
    localparam int unsigned REG_GPIO_DATA_OUT = 1;
    localparam int unsigned REG_GPIO_DIR      = 2;
    localparam int unsigned REG_GPIO_IRQ_EN   = 3;
    localparam int unsigned REG_GPIO_IRQ_TYPE = 4;
    localparam int unsigned REG_GPIO_IRQ_POL  = 5;
    localparam int unsigned REG_GPIO_IRQ_STAT = 6;
    localparam int unsigned REG_GPIO_IRQ_CLR  = 7;
    localparam int unsigned N_REGS            = 8;

    // Word address width (mirrors apb4_register_bank's own WORDW).
    localparam int unsigned WORDW = ADDR_W - 2;

    // Implemented-pin mask: only the low N_PINS bits are SW-writable.
    // The width cast keeps N_PINS == 32 from truncating to 0.
    localparam logic [31:0] PIN_MASK = 32'(({32{1'b1}} >> (32 - N_PINS)));

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  // 0 GPIO_DATA_IN   RO  (HW-written)
        32'h0000_0000,  // 1 GPIO_DATA_OUT  RW  (all pins driven low)
        32'h0000_0000,  // 2 GPIO_DIR       RW  (all pins inputs)
        32'h0000_0000,  // 3 GPIO_IRQ_EN    RW  (all IRQs masked)
        32'h0000_0000,  // 4 GPIO_IRQ_TYPE  RW  (all level-sensitive)
        32'h0000_0000,  // 5 GPIO_IRQ_POL   RW  (all active-low/falling)
        32'h0000_0000,  // 6 GPIO_IRQ_STAT  RO  (HW-written, sticky)
        32'h0000_0000   // 7 GPIO_IRQ_CLR   W1C (always reads 0)
    };

    // WMASK: DATA_IN/IRQ_STAT/IRQ_CLR are RO/HW-owned from the register
    // bank's point of view (IRQ_CLR is cleared purely by the APB write-snoop
    // below, never via the normal WMASK-gated SW-write path); the rest are
    // SW-writable up to the implemented-pin mask.
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_0000,  // 0 GPIO_DATA_IN   RO
        PIN_MASK,       // 1 GPIO_DATA_OUT  RW
        PIN_MASK,       // 2 GPIO_DIR       RW
        PIN_MASK,       // 3 GPIO_IRQ_EN    RW
        PIN_MASK,       // 4 GPIO_IRQ_TYPE  RW
        PIN_MASK,       // 5 GPIO_IRQ_POL   RW
        32'h0000_0000,  // 6 GPIO_IRQ_STAT  RO
        32'h0000_0000   // 7 GPIO_IRQ_CLR   W1C (snoop-only, never regbank-SW-writable)
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
    // Input synchronisation — N_PINS independent single-bit cdc_sync
    // instances (see ds:mod:gpio-controller: a single WIDTH(N_PINS) instance is forbidden by
    // cdc_sync.sv's own scope warning for an arbitrary binary bus).
    // =========================================================================
    logic [N_PINS-1:0] gpio_in_sync_q;

    genvar p;
    generate
        for (p = 0; p < N_PINS; p++) begin : g_in_sync
            cdc_sync #(
                .WIDTH  (1),
                .STAGES (SYNC_STAGES)
            ) u_gpio_in_sync (
                .clk_i   (clk),
                .rst_n_i (rst_n),
                .d_i     (gpio_in_i[p]),
                .q_o     (gpio_in_sync_q[p])
            );
        end
    endgenerate

    // =========================================================================
    // Output drive — combinational mirrors of the RW registers.
    // =========================================================================
    assign gpio_out_o = N_PINS'(regs_o[REG_GPIO_DATA_OUT]);
    assign gpio_oe_o  = N_PINS'(regs_o[REG_GPIO_DIR]);

    // =========================================================================
    // Edge detection — one further cycle of registration on the synchronised
    // bus. Synchronous reset (peripheral discipline, docs/development/
    // Doc: um:guide:coding-guidelines §1.4 "grandfathered" note — this subsystem is
    // uniformly synchronous-reset; see timer.sv/spi_controller.sv).
    // =========================================================================
    logic [N_PINS-1:0] gpio_in_prev_q;

    always_ff @(posedge clk) begin
        if (!rst_n)
            gpio_in_prev_q <= '0;
        else
            gpio_in_prev_q <= gpio_in_sync_q;
    end

    logic [N_PINS-1:0] rise_w, fall_w;
    assign rise_w = gpio_in_sync_q & ~gpio_in_prev_q;
    assign fall_w = ~gpio_in_sync_q & gpio_in_prev_q;

    // =========================================================================
    // Per-pin IRQ event — raw, independent of GPIO_IRQ_EN (see ds:mod:gpio-controller).
    // =========================================================================
    logic [N_PINS-1:0] irq_type_w, irq_pol_w;
    assign irq_type_w = regs_o[REG_GPIO_IRQ_TYPE][N_PINS-1:0];
    assign irq_pol_w  = regs_o[REG_GPIO_IRQ_POL][N_PINS-1:0];

    logic [N_PINS-1:0] edge_event_w, level_event_w;
    assign edge_event_w  = (irq_pol_w & rise_w) | (~irq_pol_w & fall_w);
    assign level_event_w = (irq_pol_w & gpio_in_sync_q) | (~irq_pol_w & ~gpio_in_sync_q);

    // GPIO_IRQ_CLR write-snoop: a one-cycle clear mask.
    // The address compare zero-extends addr_word to 32 bits, so N_REGS == 2**WORDW cannot wrap a valid index.
    logic [WORDW-1:0] addr_word_w;
    assign addr_word_w = paddr[ADDR_W-1:2];

    logic access_w;
    assign access_w = psel & penable;  // pready is a constant 1 from the bank

    logic is_irq_clr_addr_w;
    assign is_irq_clr_addr_w =
        ({{(32-WORDW){1'b0}}, addr_word_w} == 32'(REG_GPIO_IRQ_CLR));

    // strb_expand: byte-strobe to bit-mask expansion, copied verbatim from
    // apb4_register_bank.sv so the clear mask honours partial-word writes
    // exactly like the register bank's own SW-write path.
    function automatic logic [31:0] strb_expand(input logic [3:0] strb);
        for (int unsigned b = 0; b < 4; b++)
            strb_expand[8*b +: 8] = strb[b] ? 8'hFF : 8'h00;
    endfunction

    logic [31:0] clr_w;
    assign clr_w = (access_w && pwrite && is_irq_clr_addr_w) ?
                   (pwdata & strb_expand(pstrb)) : 32'h0;

    // =========================================================================
    // GPIO_IRQ_STAT next-state — per pin, by trigger type (see ds:mod:gpio-controller):
    //   edge  pins: sticky, SET WINS over a same-cycle CLEAR.
    //   level pins: live; clr_w has no effect on them by construction.
    // =========================================================================
    logic [N_PINS-1:0] stat_q_w, stat_next_w;
    assign stat_q_w = regs_o[REG_GPIO_IRQ_STAT][N_PINS-1:0];
    assign stat_next_w =
          ( irq_type_w & ((stat_q_w & ~clr_w[N_PINS-1:0]) | edge_event_w))
        | (~irq_type_w & level_event_w);

    // =========================================================================
    // HW-writeback — combinational mirrors driven every cycle
    // =========================================================================
    always_comb begin
        // Default all hw_wen_i/hw_wdata_i to inactive
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // GPIO_DATA_IN: live synchronised pin levels (RO — HW owns this)
        hw_wen_i  [REG_GPIO_DATA_IN] = 1'b1;
        hw_wdata_i[REG_GPIO_DATA_IN] = 32'(gpio_in_sync_q);

        // GPIO_IRQ_STAT: sticky raw pending (RO — HW owns this)
        hw_wen_i  [REG_GPIO_IRQ_STAT] = 1'b1;
        hw_wdata_i[REG_GPIO_IRQ_STAT] = 32'(stat_next_w);
    end

    // =========================================================================
    // IRQ output — level-held (see ds:mod:gpio-controller).
    // =========================================================================
    assign irq_o = |(regs_o[REG_GPIO_IRQ_STAT] & regs_o[REG_GPIO_IRQ_EN]);

endmodule : gpio_controller
