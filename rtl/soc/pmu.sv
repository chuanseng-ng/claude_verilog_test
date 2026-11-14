// pmu - behavioural power-management unit with an APB4 register block and a per-domain sequencer.
//
// Function: The unit sequences clock gate, isolation, reset and retention signals for the CPU and GPU domains.
//   It does not model supply removal, power switches or retention cells. It has no cpu_pg_ctrl and no gpu_pg_ctrl.
//   CTRL[1:0] selects the mode: 00 NORMAL, 01 CPU_OFF, 10 GPU_OFF, 11 IDLE. The names and codes match the UPF.
//   Power-down order: *_ret_save, gate the clock (*_clk_en=0), *_iso_en, assert *_rst_n=0.
//   Power-up order: release *_rst_n, *_ret_restore, de-assert *_iso_en, ungate the clock (*_clk_en=1).
//   The clock is stopped before the clamp rises and the clamp is released before the clock runs.
//   Each domain walks one action per clk_i cycle through nine states. It samples its target only at ON or OFF.
// Registers: CTRL, STATUS, DOMAIN_EN and STATUS_CLR. STATUS[3] is the sticky cpu_iso_ack_timeout flag.
//   Reset or a write of 1 to STATUS_CLR[0] clears it. STATUS_CLR is write-1-to-clear and reads 0.
// Outputs: Every *_clk_en_o, *_iso_en_o, *_rst_n_o, *_ret_save_o and *_ret_restore_o is the Q of a flop.
// Parameters: ADDR_W is the local byte address width. ISO_ACK_TIMEOUT is the ack wait limit. The default is 255.
// Clocks and resets: clk_i and rst_n_i are core_clk and core_rst_n. The reset is synchronous.
//   Reset defaults: both domains ON, clk_en 1, iso_en 0, rst_n 1, ret_save 0, ret_restore 0.
//   The sequencing never gates or resets the PMU itself.
// Caller rules:
//   - Connect cpu_iso_ack_i to the CPU-domain clamp control, synchronised back into clk_i.
//   - cpu_iso_ack_i means the clamp is active and the CPU clock gate is closed.
//   - The CPU power-down waits for a rising cpu_iso_ack_i. The CPU power-up waits for a falling cpu_iso_ack_i.
//     An ack level that was already high (power-down) or low (power-up) when the wait began does not end the wait.
//   - After ISO_ACK_TIMEOUT cycles the wait ends and STATUS[3] sets.
//   - ISO_ACK_TIMEOUT must exceed the worst-case ack round trip, about 4*R+4 clk_i cycles when cpu_core_clk is R times slower
//     than clk_i. The default 255 covers R up to about 60 (an unmeasured estimate). A value that is too small ends a wait early.
//   - soc_top holds the isolation clamps. The UPF sense is high and the clamp value is 0.
//   - Retention save and restore have no effect. The GPU loses its state on a power cycle.
//   - Software must re-initialise the GPU after every power-up. It must not rely on CPU state surviving.
// Full contract: ds:mod:pmu
// Doc: ds:mod:pmu, tm:mod:pmu

module pmu #(
    parameter int unsigned ADDR_W = 12,  // local byte address width (4 KB slot)
    // Cycles the CPU isolation-ack wait may last before the sequencer proceeds and flags
    // STATUS[3] (see ds:mod:pmu). >= 2; elaboration guard below.
    parameter int unsigned ISO_ACK_TIMEOUT = 255
) (
    input logic clk_i,
    input logic rst_n_i,

    // ── APB4 slave port (from apb_interconnect APB_PMU slot) ────────────────
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [      31:0] pwdata,
    input  logic [       3:0] pstrb,
    output logic [      31:0] prdata,
    output logic              pready,
    output logic              pslverr,

    // ── CPU domain sequencing outputs (PD_CPU, phase5_soc.upf) ──────────────
    output logic cpu_clk_en_o,       // 1 = CPU gated clock ungated (rv32i_clock_gate en)
    output logic cpu_iso_en_o,       // 1 = clamp CPU->fabric outputs to 0 (ISO_CPU)
    output logic cpu_rst_n_o,        // per-domain reset, active-low
    output logic cpu_ret_save_o,     // retention-save pulse (functional no-op, see header)
    output logic cpu_ret_restore_o,  // retention-restore pulse (functional no-op, see header)
    input  logic cpu_iso_ack_i,      // CPU-domain clamp control synchronised back to clk_i
                                     // (1 = clamp observed active, 0 = observed released);
                                     // 4-phase partner of cpu_iso_en_o, see "Isolation handshake"

    // ── GPU domain sequencing outputs (PD_GPU, phase5_soc.upf) ──────────────
    output logic gpu_clk_en_o,
    output logic gpu_iso_en_o,
    output logic gpu_rst_n_o,
    output logic gpu_ret_save_o,
    output logic gpu_ret_restore_o
);

    // The register bank decodes four word indices, so the local byte address needs at least four bits.
    if (ADDR_W < 4) begin : g_addrw_check
        $fatal(1, "pmu: ADDR_W (%0d) must be >= 4", ADDR_W);
    end

    // =========================================================================
    // Register file: 4 words — CTRL (RW), STATUS (RO/HW), DOMAIN_EN (RO/HW), STATUS_CLR (W1C snoop)
    // =========================================================================
    localparam int unsigned N_REGS = 4;
    localparam int unsigned REG_STATUS_CLR = 3;

    localparam logic [31:0] WMASK[N_REGS] = '{
        32'h0000_0003,  // CTRL:      bits[1:0] pmu_mode_req writable
        32'h0000_0000,  // STATUS:    RO (HW-driven)
        32'h0000_0000,  // DOMAIN_EN: RO (HW-driven)
        32'h0000_0000  // STATUS_CLR: no stored bits, the write is snooped
    };

    localparam logic [31:0] RESET_VAL[N_REGS] = '{
        32'h0000_0000,  // CTRL:      NORMAL (mode 00) at reset
        32'h0000_0003,  // STATUS:    cpu_domain_on=1, gpu_domain_on=1, busy=0
        32'h0000_0033,  // DOMAIN_EN: cpu_clk_en=gpu_clk_en=cpu_rst_n=gpu_rst_n=1;
                        //   iso/ret bits=0 -- matches DOM_ON reset defaults below
        32'h0000_0000  // STATUS_CLR: reads 0
    };

    logic [31:0] regs_out[N_REGS];
    logic        hw_wen  [N_REGS];
    logic [31:0] hw_wdata[N_REGS];

    apb4_register_bank #(
        .N_REGS   (N_REGS),
        .ADDR_W   (ADDR_W),
        .RESET_VAL(RESET_VAL),
        .WMASK    (WMASK)
    ) u_regbank (
        .pclk      (clk_i),
        .presetn   (rst_n_i),
        .psel      (psel),
        .penable   (penable),
        .pwrite    (pwrite),
        .paddr     (paddr),
        .pwdata    (pwdata),
        .pstrb     (pstrb),
        .prdata    (prdata),
        .pready    (pready),
        .pslverr   (pslverr),
        .regs_o    (regs_out),
        .hw_wen_i  (hw_wen),
        .hw_wdata_i(hw_wdata)
    );

    // CTRL is purely combinational read of regs_out[0] -- apb4_register_bank
    // already registers the SW-written value; no PMU-local copy needed.
    logic [1:0] pmu_mode_req;
    assign pmu_mode_req = regs_out[0][1:0];

    // reg 0 (CTRL): no HW write -- SW-only.
    assign hw_wen  [0] = 1'b0;
    assign hw_wdata[0] = '0;

    // =========================================================================
    // Per-domain sequencer FSM (0 = CPU, 1 = GPU) -- identical structure,
    // replicated via generate (house idiom for symmetric per-lane/per-bank
    // hardware, e.g. GPU lanes / D-cache banks).
    // =========================================================================
    localparam int unsigned N_DOM   = 2;
    localparam int unsigned DOM_CPU = 0;
    localparam int unsigned DOM_GPU = 1;

    localparam logic [1:0] MODE_NORMAL  = 2'b00;
    localparam logic [1:0] MODE_CPU_OFF = 2'b01;
    localparam logic [1:0] MODE_GPU_OFF = 2'b10;
    localparam logic [1:0] MODE_IDLE    = 2'b11;

    // Linear 9-state chain per domain: ON -> (power-down x4) -> OFF ->
    // (power-up x4) -> ON. One action per state. Isolation comes before reset on the way down and
    // restore comes before the clamp release on the way up, as the UPF requires.
    // The clock is stopped before the clamp rises and the clamp is released before the clock runs.
    typedef enum logic [3:0] {
        DOM_ON         = 4'd0,  // steady: clk ungated, no iso, reset released
        DOM_PD_SAVE    = 4'd1,  // power-down 1: assert ret_save
        DOM_PD_ISO     = 4'd2,  // power-down 3: assert iso_en and wait for the ack
        DOM_PD_GATE    = 4'd3,  // power-down 2: gate clock
        DOM_OFF        = 4'd4,  // steady: clk gated, iso asserted, reset asserted
        DOM_PU_RST     = 4'd5,  // power-up 1: release domain reset
        DOM_PU_CLK     = 4'd6,  // power-up 4: ungate clock
        DOM_PU_RESTORE = 4'd7,  // power-up 2: assert ret_restore
        DOM_PU_ISO     = 4'd8   // power-up 3: de-assert iso_en and wait for the ack release
    } pmu_dom_state_e;

    pmu_dom_state_e dom_state_q[N_DOM];
    logic [N_DOM-1:0] dom_target_on;

    // Decode requested mode into a per-domain "should be on" target. Domains
    // only re-sample this while settled at DOM_ON/DOM_OFF (see below), so a
    // mode change mid-sequence cannot reverse an in-flight transition.
    always_comb begin
        unique case (pmu_mode_req)
            MODE_NORMAL: begin
                dom_target_on[DOM_CPU] = 1'b1;
                dom_target_on[DOM_GPU] = 1'b1;
            end
            MODE_CPU_OFF: begin
                dom_target_on[DOM_CPU] = 1'b0;
                dom_target_on[DOM_GPU] = 1'b1;
            end
            MODE_GPU_OFF: begin
                dom_target_on[DOM_CPU] = 1'b1;
                dom_target_on[DOM_GPU] = 1'b0;
            end
            MODE_IDLE: begin
                dom_target_on[DOM_CPU] = 1'b0;
                dom_target_on[DOM_GPU] = 1'b0;
            end
            default: begin
                dom_target_on[DOM_CPU] = 1'b1;
                dom_target_on[DOM_GPU] = 1'b1;
            end
        endcase
    end

    // The outputs are registered. Each one is the Q of a flop that loads the decode of the next state.
    logic clk_en_q      [N_DOM];
    logic iso_en_q      [N_DOM];
    logic rst_n_q       [N_DOM];
    logic ret_save_q    [N_DOM];
    logic ret_restore_q [N_DOM];

    // Next-state decode and its output decode are combinational and may
    // glitch freely: they only ever feed flop D pins.
    pmu_dom_state_e dom_state_d [N_DOM];
    logic clk_en_d      [N_DOM];
    logic iso_en_d      [N_DOM];
    logic rst_n_d       [N_DOM];
    logic ret_save_d    [N_DOM];
    logic ret_restore_d [N_DOM];

    // pd_ack_ok[d] ends the power-down ack wait and pu_ack_ok[d] ends the power-up ack release wait.
    // wait_hit[d] is the timeout in a wait state. All three feed only the next-state logic.
    logic pd_ack_ok [N_DOM];
    logic pu_ack_ok [N_DOM];
    logic wait_hit  [N_DOM];
    logic cpu_iso_ack_to_q;   // STATUS[3], sticky

    // A zero or one cycle timeout can never be distinguished from "no wait" (the counter would
    // expire in the cycle the wait starts), so reject it at elaboration (generate-scope $fatal:
    // fires under --lint-only too, see cdc_gray_fifo.sv).
    if (ISO_ACK_TIMEOUT < 2) begin : g_timeout_check
        $fatal(1, "pmu: ISO_ACK_TIMEOUT (%0d) must be >= 2", ISO_ACK_TIMEOUT);
    end

    genvar d;
    generate
        for (d = 0; d < N_DOM; d++) begin : g_dom_seq

            // ── Next-state logic ────────────────────────────────────────────
            always_comb begin
                unique case (dom_state_q[d])
                    DOM_ON:         dom_state_d[d] = dom_target_on[d] ? DOM_ON : DOM_PD_SAVE;
                    DOM_PD_SAVE:    dom_state_d[d] = DOM_PD_GATE;
                    DOM_PD_GATE:    dom_state_d[d] = DOM_PD_ISO;
                    // Hold until the clamp is acknowledged (or the wait times out).
                    DOM_PD_ISO:     dom_state_d[d] = (pd_ack_ok[d] || wait_hit[d]) ? DOM_OFF
                                                                                   : DOM_PD_ISO;
                    DOM_OFF:        dom_state_d[d] = dom_target_on[d] ? DOM_PU_RST : DOM_OFF;
                    DOM_PU_RST:     dom_state_d[d] = DOM_PU_RESTORE;
                    DOM_PU_RESTORE: dom_state_d[d] = DOM_PU_ISO;
                    // Hold until the release is acknowledged (4-phase RZ). See ds:mod:pmu.
                    DOM_PU_ISO:     dom_state_d[d] = (pu_ack_ok[d] || wait_hit[d]) ? DOM_PU_CLK
                                                                                   : DOM_PU_ISO;
                    DOM_PU_CLK:     dom_state_d[d] = DOM_ON;
                    default:        dom_state_d[d] = DOM_ON;
                endcase
            end

            // ── Output decode of the NEXT state (one action live per state) ─
            always_comb begin
                unique case (dom_state_d[d])
                    DOM_ON: begin
                        clk_en_d[d] = 1'b1;
                        iso_en_d[d] = 1'b0;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                    DOM_PD_SAVE: begin
                        clk_en_d[d] = 1'b1;
                        iso_en_d[d] = 1'b0;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b1;
                        ret_restore_d[d] = 1'b0;
                    end
                    DOM_PD_GATE: begin
                        clk_en_d[d] = 1'b0;
                        iso_en_d[d] = 1'b0;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                    DOM_PD_ISO: begin
                        clk_en_d[d] = 1'b0;
                        iso_en_d[d] = 1'b1;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                    DOM_OFF: begin
                        clk_en_d[d] = 1'b0;
                        iso_en_d[d] = 1'b1;
                        rst_n_d[d] = 1'b0;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                    DOM_PU_RST: begin
                        clk_en_d[d] = 1'b0;
                        iso_en_d[d] = 1'b1;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                    DOM_PU_RESTORE: begin
                        clk_en_d[d] = 1'b0;
                        iso_en_d[d] = 1'b1;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b1;
                    end
                    DOM_PU_ISO: begin
                        clk_en_d[d] = 1'b0;
                        iso_en_d[d] = 1'b0;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                    DOM_PU_CLK: begin
                        clk_en_d[d] = 1'b1;
                        iso_en_d[d] = 1'b0;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                    default: begin
                        clk_en_d[d] = 1'b1;
                        iso_en_d[d] = 1'b0;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                endcase
            end

            // ── State + output registers (synchronous reset). See ds:mod:pmu. ──
            // Reset values are decode(DOM_ON): ungated, not isolated, reset
            // released, no retention pulse -- identical to what the former
            // combinational outputs showed during reset.
            always_ff @(posedge clk_i) begin
                if (!rst_n_i) begin
                    dom_state_q[d]    <= DOM_ON;
                    clk_en_q[d]       <= 1'b1;
                    iso_en_q[d]       <= 1'b0;
                    rst_n_q[d]        <= 1'b1;
                    ret_save_q[d]     <= 1'b0;
                    ret_restore_q[d]  <= 1'b0;
                end else begin
                    dom_state_q[d]    <= dom_state_d[d];
                    clk_en_q[d]       <= clk_en_d[d];
                    iso_en_q[d]       <= iso_en_d[d];
                    rst_n_q[d]        <= rst_n_d[d];
                    ret_save_q[d]     <= ret_save_d[d];
                    ret_restore_q[d]  <= ret_restore_d[d];
                end
            end

            // ── Isolation-ack wait + timeout ────────────────────────────────
            if (d == DOM_CPU) begin : g_ack_cpu
                localparam int unsigned CW = $clog2(ISO_ACK_TIMEOUT);

                logic          wait_active;
                logic [CW-1:0] wait_cnt_q;
                // ack_low_seen_q: the ack was low before, or during, the power-down wait. A stale high ack
                // from an earlier timed-out handshake cannot end the wait. ack_high_seen_q mirrors it for power-up.
                logic          ack_low_seen_q;
                logic          ack_high_seen_q;
                logic          sts_clr_w;

                assign pd_ack_ok[d] = cpu_iso_ack_i && ack_low_seen_q;
                assign pu_ack_ok[d] = !cpu_iso_ack_i && ack_high_seen_q;

                // In DOM_PD_ISO the wait is on ack rising, in DOM_PU_ISO on ack falling.
                assign wait_active =
                    ((dom_state_q[d] == DOM_PD_ISO) && !pd_ack_ok[d]) ||
                    ((dom_state_q[d] == DOM_PU_ISO) && !pu_ack_ok[d]);
                assign wait_hit[d] = wait_active && (wait_cnt_q == CW'(ISO_ACK_TIMEOUT - 1));

                // STATUS_CLR write-snoop: one-cycle clear pulse for STATUS[3], honouring pstrb[0].
                logic [ADDR_W-3:0] addr_word_w;
                assign addr_word_w = paddr[ADDR_W-1:2];
                assign sts_clr_w = psel && penable && pwrite && pstrb[0] && pwdata[0] &&
                                   ({{(32-(ADDR_W-2)){1'b0}}, addr_word_w} == 32'(REG_STATUS_CLR));

                always_ff @(posedge clk_i) begin
                    if (!rst_n_i) begin
                        wait_cnt_q       <= '0;
                        cpu_iso_ack_to_q <= 1'b0;
                        ack_low_seen_q   <= 1'b0;
                        ack_high_seen_q  <= 1'b0;
                    end else begin
                        // Counts the cycles spent waiting; any cycle that is not a wait (ack seen,
                        // or another state) restarts it, so every wait gets the full timeout.
                        if (wait_active && !wait_hit[d]) wait_cnt_q <= wait_cnt_q + CW'(1);
                        else                             wait_cnt_q <= '0;
                        // Sticky until reset or a STATUS_CLR write. A timeout in the same cycle wins over the clear.
                        if (wait_hit[d])        cpu_iso_ack_to_q <= 1'b1;
                        else if (sts_clr_w)     cpu_iso_ack_to_q <= 1'b0;
                        // Outside the wait state each qualifier follows the ack level. Inside it, the qualifier
                        // sets once the opposite level is seen and holds.
                        if (dom_state_q[d] == DOM_PD_ISO) begin
                            if (!cpu_iso_ack_i) ack_low_seen_q <= 1'b1;
                        end else begin
                            ack_low_seen_q <= !cpu_iso_ack_i;
                        end
                        if (dom_state_q[d] == DOM_PU_ISO) begin
                            if (cpu_iso_ack_i) ack_high_seen_q <= 1'b1;
                        end else begin
                            ack_high_seen_q <= cpu_iso_ack_i;
                        end
                    end
                end
            end else begin : g_ack_none
                // Same-clock domain: the clamp control IS the PMU flop, so it is "acknowledged"
                // the cycle it is raised and "released" the cycle it is dropped. Both waits are
                // zero-length and there is no timeout to flag.
                assign pd_ack_ok[d] = iso_en_q[d];
                assign pu_ack_ok[d] = !iso_en_q[d];
                assign wait_hit[d]  = 1'b0;
            end

        end : g_dom_seq
    endgenerate

    // ── Map per-domain arrays to named output ports ─────────────────────────
    assign cpu_clk_en_o      = clk_en_q[DOM_CPU];
    assign cpu_iso_en_o      = iso_en_q[DOM_CPU];
    assign cpu_rst_n_o       = rst_n_q[DOM_CPU];
    assign cpu_ret_save_o    = ret_save_q[DOM_CPU];
    assign cpu_ret_restore_o = ret_restore_q[DOM_CPU];

    assign gpu_clk_en_o      = clk_en_q[DOM_GPU];
    assign gpu_iso_en_o      = iso_en_q[DOM_GPU];
    assign gpu_rst_n_o       = rst_n_q[DOM_GPU];
    assign gpu_ret_save_o    = ret_save_q[DOM_GPU];
    assign gpu_ret_restore_o = ret_restore_q[DOM_GPU];

    // =========================================================================
    // STATUS / DOMAIN_EN: HW-written every cycle (same pattern as
    // pll_apb_regs.sv pushing pll_locked_i into STATUS[0]).
    // =========================================================================
    logic cpu_domain_on, gpu_domain_on, pmu_busy;

    assign cpu_domain_on = (dom_state_q[DOM_CPU] == DOM_ON);
    assign gpu_domain_on = (dom_state_q[DOM_GPU] == DOM_ON);
    assign pmu_busy = (dom_state_q[DOM_CPU] != DOM_ON && dom_state_q[DOM_CPU] != DOM_OFF) ||
                      (dom_state_q[DOM_GPU] != DOM_ON && dom_state_q[DOM_GPU] != DOM_OFF);

    assign hw_wen  [1]   = 1'b1;
    assign hw_wdata[1]   = {28'b0, cpu_iso_ack_to_q, pmu_busy, gpu_domain_on, cpu_domain_on};

    // STATUS_CLR (word 3) has no stored bits. The clear is snooped from the APB write in g_ack_cpu.
    assign hw_wen  [3]   = 1'b0;
    assign hw_wdata[3]   = '0;

    assign hw_wen  [2]   = 1'b1;
    assign hw_wdata[2]   = {
        22'b0,
        ret_restore_q[DOM_GPU],
        ret_save_q[DOM_GPU],
        ret_restore_q[DOM_CPU],
        ret_save_q[DOM_CPU],
        rst_n_q[DOM_GPU],
        rst_n_q[DOM_CPU],
        iso_en_q[DOM_GPU],
        iso_en_q[DOM_CPU],
        clk_en_q[DOM_GPU],
        clk_en_q[DOM_CPU]
    };

endmodule : pmu
