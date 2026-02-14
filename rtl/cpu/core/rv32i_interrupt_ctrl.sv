// rv32i_interrupt_ctrl.sv
// RV32I M-mode Interrupt Controller (Phase 2)
//
// Purely combinational. Combines interrupt pending bits with enable masks to
// produce a single irq_valid indicator and the corresponding mcause value.
//
// Priority: external (MEIP) > timer (MTIP)   [OQ-2]
//
// mip bits are independent of their enable bits (ext_irq_pending and
// timer_irq_pending reflect raw hardware inputs, for use in mip register).

module rv32i_interrupt_ctrl (
    // ── Enable and pending from CSR file ─────────────────────────────────────
    input  logic        mstatus_mie,       // Effective MIE (post-write for OQ-4)
    input  logic        mie_mtie,          // Machine Timer Interrupt Enable
    input  logic        mie_meie,          // Machine External Interrupt Enable

    // ── Raw hardware interrupt inputs ─────────────────────────────────────────
    input  logic        ext_irq_i,         // External interrupt (level-sensitive)
    input  logic        timer_irq_i,       // Timer interrupt (level-sensitive)

    // ── mip bits (independent of enable — used to build mip register) ─────────
    output logic        ext_irq_pending,   // mip.MEIP
    output logic        timer_irq_pending, // mip.MTIP

    // ── Interrupt delivery ────────────────────────────────────────────────────
    output logic        irq_valid,         // An enabled interrupt is pending and MIE=1
    output logic [31:0] irq_cause          // Full mcause value (bit31=1 for interrupts)
);

    // mip bits are purely the hardware inputs (OQ-2: independent of enable bits)
    assign ext_irq_pending   = ext_irq_i;
    assign timer_irq_pending = timer_irq_i;

    // irq_valid: global enable gate + individual enable gate
    logic ext_irq_enabled, timer_irq_enabled;
    assign ext_irq_enabled   = mstatus_mie && mie_meie && ext_irq_i;
    assign timer_irq_enabled = mstatus_mie && mie_mtie && timer_irq_i;

    assign irq_valid = ext_irq_enabled || timer_irq_enabled;

    // irq_cause: external wins over timer (OQ-2)
    // mcause[31]=1 (interrupt), exception code in [30:0]
    //   External interrupt: 0x8000_000B (code 11)
    //   Timer interrupt:    0x8000_0007 (code  7)
    always_comb begin
        if (ext_irq_enabled) begin
            irq_cause = 32'h8000_000B;   // Machine external interrupt
        end else begin
            irq_cause = 32'h8000_0007;   // Machine timer interrupt
        end
    end

endmodule
