// =============================================================================
// pll_rnm.sv  --  Real-Number Model (RNM) for PLL Clock Generator
// Design : pll_clkgen  (Phase 7, Milestone M-b / M-c, bead claude_verilog_test-010)
// Tool   : Verilator 5.x elaboration + cocotb co-sim (M-c)
//
// Ports
//   ref_clk_i     : 1b input  — 100 MHz reference clock (from crystal / XO)
//   rst_n_i       : 1b input  — active-low asynchronous reset
//   feedback_div  : 4b input  — divider ratio: 4'h0 → N=N_DIV_DEFAULT (13)
//   post_div_sel  : 2b input  — post-divider: 2'b00→/1, 2'b01→/2, 2'b10→/4
//   out_clk_o     : 1b output — PLL output clock
//   locked_o      : 1b output — lock indicator
//
// Behaviour
//   - Computes f_out = F_REF * N / post_div in real arithmetic
//   - Models vtune settling toward lock target with first-order step (alpha=0.5/cycle)
//   - Asserts locked_o after LOCK_PERSIST_CYCLES consecutive ref cycles with
//     vtune within LOCK_WINDOW_V of target; deasserts on reset
//   - Generates out_clk_o via phase accumulator (no $realtime dependency)
//
// Spec traceability
//   f_out_hz      → constraints.specs.f_out_hz      = 1.282e9
//   divider_n     → constraints.specs.divider_n     = 13
//   lock_time_us  → constraints.specs.lock_time_us  = 20
//   post_div      → constraints.specs.post_div      = [1,2,4]
//
// Connect-rule boundary (for M-c AMS co-sim):
//   ref_clk_i, rst_n_i, feedback_div, post_div_sel : L2R (digital → RNM)
//   out_clk_o, locked_o                            : R2L (RNM → digital)
// =============================================================================

`timescale 1ns/1ps

module pll_rnm #(
    parameter real F_REF_HZ          = 100.0e6,  // Reference frequency (Hz)
    parameter int  N_DIV_DEFAULT     = 13,        // Default feedback divider
    parameter real F_VCO_NOM_HZ      = 1.3e9,    // VCO freq at VTUNE_NOM_V (Hz)
    parameter real KVCO_HZ_V         = 80.0e6,   // Fine Kvco (Hz/V)
    parameter real VTUNE_NOM_V       = 0.35,      // Vtune at F_VCO_NOM_HZ (V)
    parameter real LOCK_WINDOW_V     = 0.005,     // ±5 mV vtune lock window
    parameter int  LOCK_PERSIST_CYCLES = 5,       // Consecutive cycles in window
    parameter real VTUNE_RESET_V     = 0.0        // Vtune at reset
) (
    input  logic       ref_clk_i,
    input  logic       rst_n_i,
    input  logic [3:0] feedback_div,
    input  logic [1:0] post_div_sel,
    output logic       out_clk_o,
    output logic       locked_o
);

    // -------------------------------------------------------------------------
    // Internal state
    // -------------------------------------------------------------------------
    real vtune;           // Current loop-filter tuning voltage (V)
    real f_vco_hz;        // Current VCO frequency (Hz) — combinational from vtune
    real phase_acc;       // Phase accumulator for out_clk generation (VCO cycles)
    int  lock_count;      // Consecutive in-window ref cycles

    // -------------------------------------------------------------------------
    // Resolved divider values (combinational)
    // -------------------------------------------------------------------------
    int  n_div_actual;
    int  post_div_actual;

    always_comb begin
        n_div_actual   = (feedback_div == 4'h0) ? N_DIV_DEFAULT : int'(feedback_div);
        case (post_div_sel)
            2'b00:   post_div_actual = 1;
            2'b01:   post_div_actual = 2;
            2'b10:   post_div_actual = 4;
            default: post_div_actual = 1;
        endcase
    end

    // -------------------------------------------------------------------------
    // VCO frequency (combinational) — clamped to [0.9, 1.5] GHz
    // -------------------------------------------------------------------------
    always_comb begin
        automatic real fv;
        fv = F_VCO_NOM_HZ + KVCO_HZ_V * (vtune - VTUNE_NOM_V);
        if      (fv < 0.9e9) fv = 0.9e9;
        else if (fv > 1.5e9) fv = 1.5e9;
        f_vco_hz = fv;
    end

    // -------------------------------------------------------------------------
    // Vtune target: value at which f_vco = F_REF * N  (integer-N lock point)
    // -------------------------------------------------------------------------
    function automatic real vtune_target_fn(input int n_div);
        automatic real f_target;
        f_target = F_REF_HZ * real'(n_div);
        return VTUNE_NOM_V + (f_target - F_VCO_NOM_HZ) / KVCO_HZ_V;
    endfunction

    // -------------------------------------------------------------------------
    // Lock acquisition + vtune update (synchronous on ref_clk_i)
    // First-order step: vtune[k+1] = vtune[k] + alpha*(target - vtune[k])
    // alpha=0.5 → locks in ~10 ref cycles (~100 ns), far within 20 µs spec
    // -------------------------------------------------------------------------
    always_ff @(posedge ref_clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            vtune      <= VTUNE_RESET_V;
            lock_count <= 0;
            locked_o   <= 1'b0;
        end else begin
            automatic real vt;
            automatic real in_win;
            vt = vtune_target_fn(n_div_actual);

            // Vtune step
            vtune <= vtune + 0.5 * (vt - vtune);

            // Lock window check on CURRENT vtune (before update, for timing)
            // Use current vtune vs target
            in_win = ((vtune - vt < LOCK_WINDOW_V) && (vt - vtune < LOCK_WINDOW_V))
                     ? 1.0 : 0.0;

            if (in_win > 0.5) begin
                if (lock_count < LOCK_PERSIST_CYCLES)
                    lock_count <= lock_count + 1;
            end else begin
                lock_count <= 0;
            end

            locked_o <= (lock_count >= LOCK_PERSIST_CYCLES) ? 1'b1 : 1'b0;
        end
    end

    // -------------------------------------------------------------------------
    // Output clock via phase accumulator
    // Accumulates f_vco/f_ref VCO cycles per ref cycle; toggles every N*P/2
    // -------------------------------------------------------------------------
    always_ff @(posedge ref_clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            phase_acc <= 0.0;
            out_clk_o <= 1'b0;
        end else begin
            automatic real cpr;       // VCO cycles per ref cycle
            automatic real half_per;  // Toggle threshold in VCO cycles
            cpr      = f_vco_hz / F_REF_HZ;
            half_per = real'(n_div_actual * post_div_actual) / 2.0;
            phase_acc <= phase_acc + cpr;
            if (phase_acc + cpr >= half_per) begin
                out_clk_o <= ~out_clk_o;
                phase_acc <= phase_acc + cpr - half_per;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Elaboration-time parameter checks
    // -------------------------------------------------------------------------
    // synthesis translate_off
    initial begin
        if (N_DIV_DEFAULT <= 0 || N_DIV_DEFAULT > 63)
            $fatal(1, "pll_rnm: N_DIV_DEFAULT=%0d out of [1,63]", N_DIV_DEFAULT);
        if (F_VCO_NOM_HZ < 0.5e9 || F_VCO_NOM_HZ > 2.0e9)
            $fatal(1, "pll_rnm: F_VCO_NOM_HZ=%.3e out of [0.5G,2.0G]", F_VCO_NOM_HZ);
        $display("[pll_rnm] F_REF=%.0f MHz  N=%0d  F_VCO_NOM=%.3f GHz  Kvco=%.0f MHz/V",
            F_REF_HZ/1e6, N_DIV_DEFAULT, F_VCO_NOM_HZ/1e9, KVCO_HZ_V/1e6);
        $display("[pll_rnm] Vtune_nom=%.3f V  Lock_window=%.1f mV  Persist=%0d cycles",
            VTUNE_NOM_V, LOCK_WINDOW_V*1e3, LOCK_PERSIST_CYCLES);
        $display("[pll_rnm] f_out (N=13,/1) = %.3f GHz",
            (F_VCO_NOM_HZ + KVCO_HZ_V*(VTUNE_NOM_V - VTUNE_NOM_V))/1e9);
    end
    // synthesis translate_on

endmodule : pll_rnm
