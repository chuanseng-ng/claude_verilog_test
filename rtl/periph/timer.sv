// timer.sv
// Phase 5 (M4) — Programmable timer with prescaler, compare, and IRQ output.
// APB migration PR-4: converted from AXI4-Lite slave to APB4 slave.
//
// Register map (word indices into the apb4_register_bank):
//   0  TMR_COUNTER  RO             live count value (HW-written, no SW write)
//   1  TMR_COMPARE  RW 0xFFFFFFFF  compare threshold; match sets irq_pending
//   2  TMR_CTRL     RW 0x0         [0]=enable [1]=irq_en [2]=auto_clear(edge)
//   3  TMR_PRESCALE RW 0x0         count increments every (TMR_PRESCALE+1) clks
//                                  prescale=0 → tick every clock
//
// irq_o → CPU timer_irq_i (MTIP in RISC-V M-mode).
// irq_pending_q is sticky: set on (count >= compare) while enabled.
// auto_clear edge (CTRL[2] 0→1): clears irq_pending_q AND resets count to 0.
//
// APB4 interface (ARM IHI0024C):
//   pclk = clk, presetn = rst_n (active-low synchronous reset)
//   ADDR_W = 12 (byte address; [1:0] unused, word-aligned)
//   Zero wait states: pready driven 1 every ACCESS phase.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module timer
#(
    parameter int unsigned ADDR_W  = 12,  // APB4 local address width
    parameter int unsigned CNT_W   = 32,  // counter width
    parameter int unsigned PRESC_W = 16   // prescaler width
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
    // Interrupt output
    // =========================================================================
    output logic irq_o   // → CPU timer_irq_i (MTIP)
);

    // =========================================================================
    // Local constants
    // =========================================================================
    localparam int unsigned REG_TMR_COUNTER  = 0;
    localparam int unsigned REG_TMR_COMPARE  = 1;
    localparam int unsigned REG_TMR_CTRL     = 2;
    localparam int unsigned REG_TMR_PRESCALE = 3;
    localparam int unsigned N_REGS           = 4;

    // CTRL bit positions
    localparam int unsigned CTRL_ENABLE_BIT     = 0;
    localparam int unsigned CTRL_IRQEN_BIT      = 1;
    localparam int unsigned CTRL_AUTOCLEAR_BIT  = 2;

    // =========================================================================
    // Register bank configuration
    // =========================================================================
    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,  // 0 TMR_COUNTER  RO  (HW-written)
        32'hFFFF_FFFF,  // 1 TMR_COMPARE  RW  (no match at reset)
        32'h0000_0000,  // 2 TMR_CTRL     RW  (disabled)
        32'h0000_0000   // 3 TMR_PRESCALE RW  (tick every cycle)
    };

    // WMASK: COUNTER is RO (HW-owned); COMPARE/CTRL/PRESCALE are SW-writable
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_0000,  // 0 TMR_COUNTER  RO
        32'hFFFF_FFFF,  // 1 TMR_COMPARE  RW
        32'h0000_0007,  // 2 TMR_CTRL     RW [2:0] only
        32'h0000_FFFF   // 3 TMR_PRESCALE RW [PRESC_W-1:0]
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
    // Control register aliases
    // =========================================================================
    logic        enable;
    logic        irq_en;
    logic        auto_clear;

    assign enable     = regs_o[REG_TMR_CTRL][CTRL_ENABLE_BIT];
    assign irq_en     = regs_o[REG_TMR_CTRL][CTRL_IRQEN_BIT];
    assign auto_clear = regs_o[REG_TMR_CTRL][CTRL_AUTOCLEAR_BIT];

    // =========================================================================
    // auto_clear edge detection (0→1 rising edge on CTRL[2])
    // =========================================================================
    logic auto_clear_prev_q;
    logic auto_clear_pulse;

    always_ff @(posedge clk) begin
        if (!rst_n)
            auto_clear_prev_q <= 1'b0;
        else
            auto_clear_prev_q <= auto_clear;
    end

    assign auto_clear_pulse = auto_clear & ~auto_clear_prev_q;

    // =========================================================================
    // Prescaler — tick every (TMR_PRESCALE+1) clocks
    // presc_q counts down from TMR_PRESCALE to 0; tick on presc_q==0.
    // When TMR_PRESCALE==0 the reload is 0, so presc_q stays 0 → tick every cycle.
    // =========================================================================
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] prescale_reg;  // full reg; only [PRESC_W-1:0] used below
    /* verilator lint_on  UNUSEDSIGNAL */
    logic [PRESC_W-1:0] presc_q;
    logic               tick;

    assign prescale_reg = regs_o[REG_TMR_PRESCALE];
    assign tick         = (presc_q == {PRESC_W{1'b0}});

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            presc_q <= {PRESC_W{1'b0}};
        end else begin
            if (tick)
                presc_q <= prescale_reg[PRESC_W-1:0];
            else
                presc_q <= presc_q - PRESC_W'(1);
        end
    end

    // =========================================================================
    // Counter — CNT_W-bit free-running counter gated by enable
    // =========================================================================
    logic [CNT_W-1:0] count_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            count_q <= {CNT_W{1'b0}};
        end else begin
            if (auto_clear_pulse) begin
                count_q <= {CNT_W{1'b0}};
            end else if (enable && tick) begin
                count_q <= count_q + CNT_W'(1);
            end
        end
    end

    // =========================================================================
    // Compare and IRQ pending
    // Full-width CNT_W comparison; irq_pending_q is sticky.
    // =========================================================================
    logic [CNT_W-1:0] compare_val;
    logic             match;
    logic             irq_pending_q;

    assign compare_val = regs_o[REG_TMR_COMPARE][CNT_W-1:0];
    assign match       = enable && (count_q >= compare_val);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            irq_pending_q <= 1'b0;
        end else begin
            if (auto_clear_pulse)
                irq_pending_q <= 1'b0;
            else if (match)
                irq_pending_q <= 1'b1;
        end
    end

    // =========================================================================
    // HW-writeback — combinational mirrors driven every cycle
    // =========================================================================
    always_comb begin
        // Default all hw_wen_i/hw_wdata_i to inactive
        for (int unsigned r = 0; r < N_REGS; r++) begin
            hw_wen_i  [r] = 1'b0;
            hw_wdata_i[r] = 32'h0;
        end

        // TMR_COUNTER: live count (RO — HW owns this, no SW write)
        hw_wen_i  [REG_TMR_COUNTER] = 1'b1;
        hw_wdata_i[REG_TMR_COUNTER] = 32'(count_q);

        // TMR_COMPARE, TMR_CTRL, TMR_PRESCALE: SW-owned (RW), HW does not write
        hw_wen_i  [REG_TMR_COMPARE]  = 1'b0;
        hw_wdata_i[REG_TMR_COMPARE]  = 32'h0;
        hw_wen_i  [REG_TMR_CTRL]     = 1'b0;
        hw_wdata_i[REG_TMR_CTRL]     = 32'h0;
        hw_wen_i  [REG_TMR_PRESCALE] = 1'b0;
        hw_wdata_i[REG_TMR_PRESCALE] = 32'h0;
    end

    // =========================================================================
    // IRQ output
    // =========================================================================
    assign irq_o = irq_en & irq_pending_q;

endmodule : timer
