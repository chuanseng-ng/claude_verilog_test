// gpio_controller.sv
// Phase 6a — General-purpose I/O controller, APB4 slave (bead claude_verilog_test-ckc).
//
// Register map (word indices into the apb4_register_bank):
//   0  GPIO_DATA_IN   RO             live synchronised pin levels (HW-written)
//   1  GPIO_DATA_OUT  RW             output-drive value per pin
//   2  GPIO_DIR       RW             1 = pin driven as output, 0 = input
//   3  GPIO_IRQ_EN    RW             1 = pin's IRQ event masked into irq_o
//   4  GPIO_IRQ_TYPE  RW             0 = level-sensitive, 1 = edge-sensitive
//   5  GPIO_IRQ_POL   RW             0 = active-low/falling, 1 = active-high/rising
//   6  GPIO_IRQ_STAT  RO             per-pin pending: sticky in edge mode,
//                                    live in level mode (HW-written)
//   7  GPIO_IRQ_CLR   W1C            APB-write-snoop clear (edge pins only);
//                                    always reads 0
//
// Only the low N_PINS bits of GPIO_DATA_OUT/GPIO_DIR/GPIO_IRQ_EN/GPIO_IRQ_TYPE/
// GPIO_IRQ_POL/GPIO_IRQ_CLR are SW-writable (WMASK restricted to the
// implemented-pin mask below); the rest of this module's internal buses are
// N_PINS-wide, so an unimplemented pin (N_PINS < 32) can never source an
// event or a driven level.
//
// Input synchronisation: gpio_in_i is an asynchronous external pin bus. Per
// rtl/soc/cdc/cdc_2ff_sync.sv's own scope warning, that primitive is valid
// ONLY for WIDTH=1 or gray-coded buses -- NOT an arbitrary multi-bit binary
// bus, because independent bits can resolve metastability on different
// destination-clock edges and the sampled word could transiently equal a
// value no single source-side cycle ever drove. GPIO pins carry no cross-bit
// word coherency (each pin is an independent, unrelated external signal), so
// this module instantiates N_PINS SEPARATE single-bit cdc_2ff_sync instances
// -- one per pin -- rather than one WIDTH(N_PINS) instance, making that
// absence of coherency explicit and self-documenting rather than accidental.
//
// Edge detection: the synchronised bus is registered one further cycle
// (gpio_in_prev_q); rise = sync & ~prev, fall = ~sync & prev.
//
// Per-pin IRQ event (raw, independent of GPIO_IRQ_EN -- GPIO_IRQ_STAT is the
// raw pending register; GPIO_IRQ_EN masks only the irq_o output). Both event
// terms are computed for every pin every cycle; GPIO_IRQ_TYPE selects which
// one reaches GPIO_IRQ_STAT:
//   edge mode  (IRQ_TYPE=1): event = IRQ_POL ? rise : fall
//   level mode (IRQ_TYPE=0): event = IRQ_POL ? sync : ~sync
//
// GPIO_IRQ_STAT update (HW-written every cycle), per pin, BY TRIGGER TYPE:
//   edge  (IRQ_TYPE=1): STICKY.  stat = (stat & ~clr) | edge_event
//       SET WINS over CLEAR on a same-cycle collision -- a GPIO_IRQ_CLR write
//       that lands the same cycle a fresh edge is captured leaves the bit SET,
//       so an edge is never silently lost to a racing clear.
//   level (IRQ_TYPE=0): LIVE.    stat = level_event
//       The bit simply follows the pin, and GPIO_IRQ_CLR has NO EFFECT on it.
//       A level interrupt is silenced by removing the condition at the source
//       or by masking GPIO_IRQ_EN -- never by clearing status.
//
// This edge-sticky / level-live split follows ARM PL061 (GPIORIS is the raw
// level in level mode; GPIOICR clears edge detection only). The alternative --
// making level events sticky too -- was rejected: with the reset defaults
// (IRQ_TYPE=0 level, IRQ_POL=0 active-low) and undriven pins reading low,
// every pin's level condition is TRUE at reset, so a sticky raw register
// would latch to all-ones on the first cycle out of reset and stay there
// until software cleared a register it had not yet configured.
//
// irq_o = |(GPIO_IRQ_STAT & GPIO_IRQ_EN) -- LEVEL-HELD, never a single-cycle
// pulse. This is required, not stylistic: soc_top.sv documents (see its IRQ
// routing note) that every IRQ source feeding interrupt_controller crosses
// core_clk -> cpu_core_clk through a plain 2-FF cdc_2ff_sync (u_ext_irq_sync),
// which can only safely observe a level that stays asserted for multiple
// destination-clock cycles -- a single-cycle pulse could be missed entirely
// by that synchroniser. GPIO_IRQ_STAT's stickiness is what makes irq_o
// level-held: an edge-mode bit stays 1 until SW clears it via GPIO_IRQ_CLR,
// and a level-mode bit stays 1 for as long as its condition holds -- in both
// cases far longer than the 2 destination-clock cycles the synchroniser needs.
// Compare timer.sv's irq_pending_q and interrupt_controller.sv's raw source
// levels, which are level-held for the same reason.
//
// No tristate: gpio_out_o/gpio_oe_o/gpio_in_i form a unidirectional triplet
// (drive value, output-enable, sensed level) rather than a single inout pad
// signal -- this repo has no tristate primitives or pad-ring model at the
// RTL level. Merging these three into one true bidirectional pad is a
// pad-ring / integration-level concern, out of scope for this module.
//
// APB4 interface (ARM IHI0024C):
//   pclk = clk, presetn = rst_n (active-low synchronous reset)
//   ADDR_W = 12 (byte address; [1:0] unused, word-aligned)
//   Zero wait states: pready driven 1 every ACCESS phase.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module gpio_controller
#(
    parameter int unsigned ADDR_W = 12,   // APB4 local address width
    parameter int unsigned N_PINS = 32    // number of implemented GPIO pins (<= 32)
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

    // Elaboration-time guard (IEEE 1800-2017 §20.11): $fatal directly inside a
    // generate scope, not wrapped in `initial`, fires at ELABORATION time --
    // under `verilator --lint-only` too, which never runs simulation and would
    // otherwise silently let an illegal N_PINS through. Mirrors
    // rtl/soc/cdc/cdc_2ff_sync.sv's g_stages_check and the rationale recorded
    // at rtl/soc/sram_controller.sv:110-126.
    // N_PINS == 0 is rejected as well as > 32: a zero-pin instance would make
    // every [N_PINS-1:0] part-select below a [-1:0] range, and PIN_MASK's
    // >> (32 - N_PINS) a >> 32 (all zeroes), so the module would be both
    // illegal and useless.
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
    // Idiom mirrored verbatim from interrupt_controller.sv:77 (GH #87-safe
    // width-cast: N_PINS==32 must not truncate to 0).
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
    // Input synchronisation — N_PINS independent single-bit cdc_2ff_sync
    // instances (see header: a single WIDTH(N_PINS) instance is forbidden by
    // cdc_2ff_sync.sv's own scope warning for an arbitrary binary bus).
    // =========================================================================
    logic [N_PINS-1:0] gpio_in_sync_q;

    genvar p;
    generate
        for (p = 0; p < N_PINS; p++) begin : g_in_sync
            cdc_2ff_sync #(
                .WIDTH  (1),
                .STAGES (2)
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
    // CODING_GUIDELINES.md §1.4 "grandfathered" note — this subsystem is
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
    // Per-pin IRQ event — raw, independent of GPIO_IRQ_EN (see header).
    // =========================================================================
    logic [N_PINS-1:0] irq_type_w, irq_pol_w;
    assign irq_type_w = regs_o[REG_GPIO_IRQ_TYPE][N_PINS-1:0];
    assign irq_pol_w  = regs_o[REG_GPIO_IRQ_POL][N_PINS-1:0];

    logic [N_PINS-1:0] edge_event_w, level_event_w;
    assign edge_event_w  = (irq_pol_w & rise_w) | (~irq_pol_w & fall_w);
    assign level_event_w = (irq_pol_w & gpio_in_sync_q) | (~irq_pol_w & ~gpio_in_sync_q);

    // =========================================================================
    // GPIO_IRQ_CLR write-snoop — one-cycle clear mask.
    // Address-compare zero-extends addr_word to 32 b before comparing (GH #87
    // truncation-safe idiom, mirrored verbatim from apb4_register_bank.sv) so
    // that N_REGS == 2**WORDW can never wrap a valid index to a false match.
    // =========================================================================
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
    // GPIO_IRQ_STAT next-state — per pin, by trigger type (see header):
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
    // IRQ output — level-held (see header rationale).
    // =========================================================================
    assign irq_o = |(regs_o[REG_GPIO_IRQ_STAT] & regs_o[REG_GPIO_IRQ_EN]);

endmodule : gpio_controller
