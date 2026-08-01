// pmu.sv
// Pre-Phase-6 #5 (GH epic #98, this file: GH #99) — behavioral power-management
// unit (PMU): power-mode APB4 register block + per-domain sequencer FSM.
//
// SCOPE (per docs/POWER_DOMAIN_EVALUATION.md, DECIDED 2026-06-27, "GO (scoped):
// behavioral PMU sequencer only"): this is a clock-gate / reset / functional-
// isolation *sequencing* controller, modeled as ordinary synchronous RTL and
// fully verifiable under Verilator. It does NOT model real supply removal,
// power switches, or retention-cell silicon — those require a UPF-capable
// simulator not available in this open-source flow and are explicitly
// deferred. `pnr/constraints/phase5_soc.upf` already carries the UPF intent
// (PD_CPU/PD_GPU/PD_SRAM/PD_PERIPH, ISO_CPU/ISO_GPU, system_pst) that this
// module's outputs are named and ordered to match.
//
// Power modes (2-bit CTRL[1:0], matches phase5_soc.upf system_pst 4-state PST):
//   00  NORMAL   — CPU on,  GPU on
//   01  CPU_OFF  — CPU off, GPU on
//   10  GPU_OFF  — CPU on,  GPU off
//   11  IDLE     — CPU off, GPU off
//
// Sequencing order (fixed by the UPF, not a design choice — see evaluation
// doc section 3 and phase5_soc.upf ISO_CPU/ISO_GPU + PSW_CPU/PSW_GPU):
//   Power-down: assert *_ret_save -> assert *_iso_en -> gate clock (*_clk_en=0)
//               -> assert domain reset (*_rst_n=0).
//   Power-up:   release domain reset (*_rst_n=1) -> ungate clock (*_clk_en=1)
//               -> assert *_ret_restore -> de-assert *_iso_en.
// Each direction is walked one action per clk_i cycle through an explicit FSM
// (9 states per domain: ON, 4 power-down actions, OFF, 4 power-up actions) so
// the order above is structurally guaranteed and directly observable/
// assertable by verification. A domain's target (from CTRL) is only re-sampled
// while the domain is settled at ON or OFF — a request that changes mid-
// sequence does not reverse the in-flight sequence, it takes effect once the
// current one completes. This avoids ill-defined half-isolated / half-gated
// states.
//
// Retention scope (explicit no-op): cpu_ret_save_o/cpu_ret_restore_o (and GPU
// equivalents) are emitted in the correct order for verification to assert,
// but there is no retention-cell silicon in this model (phase5_soc.upf:23,
// "No retention registers in Phase 5"). Because the domain's reset is only
// ever asserted while its clock is already gated (DOM_PD_GATE precedes DOM_OFF)
// and is always released before the clock is ungated (DOM_PU_RST precedes
// DOM_PU_CLK), the domain's own flops never see an active clock edge while
// held in reset -- architectural state (e.g. CPU MSTATUS/MTVEC/PC) survives an
// off->on cycle by construction, without needing real retention hardware.
// This matches the documented model: state is rebuilt/preserved because the
// domain is clock-gated, not because retention cells restored it.
//
// Isolation: cpu_iso_en_o / gpu_iso_en_o are ACTIVE-HIGH (phase5_soc.upf
// ISO_CPU/ISO_GPU, `-isolation_sense high`, `-clamp_value 0`, `-applies_to
// outputs`, `-location parent`) — this module only computes the *_iso_en
// control signal; the actual output-clamp muxes live in soc_top (outside
// u_cpu/u_gpu, in the always-on PD_PERIPH domain), per the UPF's
// `-location parent` placement. See soc_top.sv for the clamp scope/rationale.
//
// This module deliberately does NOT emit cpu_pg_ctrl/gpu_pg_ctrl (the UPF
// power-switch control signals, PSW_CPU/PSW_GPU, active-LOW on-value per
// phase5_soc.upf:94-95,103-104 `-on_value 0 -off_value 1`). Real power
// switches are part of the deferred full-power-gating scope (no switch
// insertion happens in this ASAP7 flow either — pnr/asap7/soc/pdn.tcl).
// Forward-compat note: if a future phase adds real switches, cpu_pg_ctrl
// would be the INVERSE of the "domain on" sense used internally here
// (pg_ctrl = 0 means "on"), unlike every other signal in this module.
//
// Reset style (explicit decision, see docs/development/CODING_GUIDELINES.md
// section 1.4): this module uses SYNCHRONOUS reset (`always_ff @(posedge
// clk_i)` gated by `if (!rst_n_i)`), matching every other module on the APB
// peripheral ring it lives on (uart_controller, spi_controller, timer,
// interrupt_controller, apb4_register_bank, pll_apb_regs — all synchronous-
// reset, PD_PERIPH always-on domain). Section 1.4's general guidance for NEW
// modules is async-assert/sync-deassert with a per-domain reset synchronizer,
// but soc_top has NO reset synchronizer anywhere in the design (core_rst_n =
// rst_n_i & pll_locked is a plain combinational AND — pll_subsystem.sv:93) and
// section 1.4 also requires uniform discipline within one subsystem. Adding
// this module's own async-reset flavor (and the synchronizer that would then
// be needed to make it safe) would make the PMU the sole exception on its own
// bus and does not match the surrounding synchronous-reset peripheral
// subsystem it integrates into. Matching the subsystem was chosen over
// introducing the project's first reset synchronizer as a side effect of a
// PMU; full CPU/peripheral reset-discipline unification remains the separate
// P3 audit item already tracked in CODING_GUIDELINES.md.
//
// Register map (byte offset, 32-bit words) — APB4 slave, reuses
// apb4_register_bank.sv (all APB4 protocol machinery: pready hardwired 1,
// pslverr hardwired 0, SW-write-wins-over-HW-write same cycle, HW writes
// bypass WMASK, out-of-range writes dropped / reads return 0):
//
//   0x00  CTRL       [RW]
//           [1:0]  pmu_mode_req — requested power mode (NORMAL/CPU_OFF/
//                                 GPU_OFF/IDLE, see encoding above)
//           [31:2] reserved (RO 0)
//
//   0x04  STATUS     [RO, HW-driven every cycle]
//           [0]    cpu_domain_on — 1 when the CPU domain sequencer has
//                                  settled at DOM_ON
//           [1]    gpu_domain_on — 1 when the GPU domain sequencer has
//                                  settled at DOM_ON
//           [2]    busy          — 1 while either domain is mid-sequence
//                                  (neither settled ON nor settled OFF)
//           [31:3] reserved (RO 0)
//
//   0x08  DOMAIN_EN  [RO, HW-driven every cycle] — live per-signal bitmap,
//                     primarily for verification observability (each PMU
//                     output bit directly readable without FSM-state decode):
//           [0]  cpu_clk_en       [1]  gpu_clk_en
//           [2]  cpu_iso_en       [3]  gpu_iso_en
//           [4]  cpu_rst_n        [5]  gpu_rst_n
//           [6]  cpu_ret_save     [7]  cpu_ret_restore
//           [8]  gpu_ret_save     [9]  gpu_ret_restore
//           [31:10] reserved (RO 0)
//
// Reset defaults (CTRL=NORMAL, both domains DOM_ON): cpu_clk_en_o=1,
// gpu_clk_en_o=1, cpu_iso_en_o=0, gpu_iso_en_o=0, cpu_rst_n_o=1, gpu_rst_n_o=1,
// both ret_save/ret_restore=0 -- identical to pre-PMU soc_top behavior, so
// dropping this module in with no firmware writes to CTRL is a no-op for the
// existing soc_all regression.
//
// APB4 clock/reset mapping: pclk = clk_i, presetn = rst_n_i. clk_i/rst_n_i is
// core_clk/core_rst_n (PD_PERIPH always-on domain) — the PMU itself is never
// clock-gated or reset by its own sequencing (it sequences the CPU/GPU
// domains, not itself).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.
// Per house style: no `default_nettype` directive (Spyglass IND, section 1.3).

module pmu #(
    parameter int unsigned ADDR_W = 12  // local byte address width (4 KB slot)
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

    // ── GPU domain sequencing outputs (PD_GPU, phase5_soc.upf) ──────────────
    output logic gpu_clk_en_o,
    output logic gpu_iso_en_o,
    output logic gpu_rst_n_o,
    output logic gpu_ret_save_o,
    output logic gpu_ret_restore_o
);

    // =========================================================================
    // Register file: 3 words — CTRL (RW), STATUS (RO/HW), DOMAIN_EN (RO/HW)
    // =========================================================================
    localparam int unsigned N_REGS = 3;

    localparam logic [31:0] WMASK[N_REGS] = '{
        32'h0000_0003,  // CTRL:      bits[1:0] pmu_mode_req writable
        32'h0000_0000,  // STATUS:    RO (HW-driven)
        32'h0000_0000  // DOMAIN_EN: RO (HW-driven)
    };

    localparam logic [31:0] RESET_VAL[N_REGS] = '{
        32'h0000_0000,  // CTRL:      NORMAL (mode 00) at reset
        32'h0000_0003,  // STATUS:    cpu_domain_on=1, gpu_domain_on=1, busy=0
        32'h0000_0033  // DOMAIN_EN: cpu_clk_en=gpu_clk_en=cpu_rst_n=gpu_rst_n=1;
                        //   iso/ret bits=0 -- matches DOM_ON reset defaults below
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
    // (power-up x4) -> ON. One action per state, matching the fixed UPF order.
    typedef enum logic [3:0] {
        DOM_ON         = 4'd0,  // steady: clk ungated, no iso, reset released
        DOM_PD_SAVE    = 4'd1,  // power-down 1: assert ret_save
        DOM_PD_ISO     = 4'd2,  // power-down 2: assert iso_en
        DOM_PD_GATE    = 4'd3,  // power-down 3: gate clock
        DOM_OFF        = 4'd4,  // steady: clk gated, iso asserted, reset asserted
        DOM_PU_RST     = 4'd5,  // power-up 1: release domain reset
        DOM_PU_CLK     = 4'd6,  // power-up 2: ungate clock
        DOM_PU_RESTORE = 4'd7,  // power-up 3: assert ret_restore
        DOM_PU_ISO     = 4'd8   // power-up 4: de-assert iso_en
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

    logic clk_en_w      [N_DOM];
    logic iso_en_w      [N_DOM];
    logic rst_n_w       [N_DOM];
    logic ret_save_w    [N_DOM];
    logic ret_restore_w [N_DOM];

    genvar d;
    generate
        for (d = 0; d < N_DOM; d++) begin : g_dom_seq

            // ── State register (synchronous reset -- see header) ────────────
            always_ff @(posedge clk_i) begin
                if (!rst_n_i) begin
                    dom_state_q[d] <= DOM_ON;
                end else begin
                    unique case (dom_state_q[d])
                        DOM_ON:         dom_state_q[d] <= dom_target_on[d] ? DOM_ON : DOM_PD_SAVE;
                        DOM_PD_SAVE:    dom_state_q[d] <= DOM_PD_ISO;
                        DOM_PD_ISO:     dom_state_q[d] <= DOM_PD_GATE;
                        DOM_PD_GATE:    dom_state_q[d] <= DOM_OFF;
                        DOM_OFF:        dom_state_q[d] <= dom_target_on[d] ? DOM_PU_RST : DOM_OFF;
                        DOM_PU_RST:     dom_state_q[d] <= DOM_PU_CLK;
                        DOM_PU_CLK:     dom_state_q[d] <= DOM_PU_RESTORE;
                        DOM_PU_RESTORE: dom_state_q[d] <= DOM_PU_ISO;
                        DOM_PU_ISO:     dom_state_q[d] <= DOM_ON;
                        default:        dom_state_q[d] <= DOM_ON;
                    endcase
                end
            end

            // ── Output decode (combinational; one action live per state) ────
            always_comb begin
                unique case (dom_state_q[d])
                    DOM_ON: begin
                        clk_en_w[d] = 1'b1;
                        iso_en_w[d] = 1'b0;
                        rst_n_w[d] = 1'b1;
                        ret_save_w[d] = 1'b0;
                        ret_restore_w[d] = 1'b0;
                    end
                    DOM_PD_SAVE: begin
                        clk_en_w[d] = 1'b1;
                        iso_en_w[d] = 1'b0;
                        rst_n_w[d] = 1'b1;
                        ret_save_w[d] = 1'b1;
                        ret_restore_w[d] = 1'b0;
                    end
                    DOM_PD_ISO: begin
                        clk_en_w[d] = 1'b1;
                        iso_en_w[d] = 1'b1;
                        rst_n_w[d] = 1'b1;
                        ret_save_w[d] = 1'b0;
                        ret_restore_w[d] = 1'b0;
                    end
                    DOM_PD_GATE: begin
                        clk_en_w[d] = 1'b0;
                        iso_en_w[d] = 1'b1;
                        rst_n_w[d] = 1'b1;
                        ret_save_w[d] = 1'b0;
                        ret_restore_w[d] = 1'b0;
                    end
                    DOM_OFF: begin
                        clk_en_w[d] = 1'b0;
                        iso_en_w[d] = 1'b1;
                        rst_n_w[d] = 1'b0;
                        ret_save_w[d] = 1'b0;
                        ret_restore_w[d] = 1'b0;
                    end
                    DOM_PU_RST: begin
                        clk_en_w[d] = 1'b0;
                        iso_en_w[d] = 1'b1;
                        rst_n_w[d] = 1'b1;
                        ret_save_w[d] = 1'b0;
                        ret_restore_w[d] = 1'b0;
                    end
                    DOM_PU_CLK: begin
                        clk_en_w[d] = 1'b1;
                        iso_en_w[d] = 1'b1;
                        rst_n_w[d] = 1'b1;
                        ret_save_w[d] = 1'b0;
                        ret_restore_w[d] = 1'b0;
                    end
                    DOM_PU_RESTORE: begin
                        clk_en_w[d] = 1'b1;
                        iso_en_w[d] = 1'b1;
                        rst_n_w[d] = 1'b1;
                        ret_save_w[d] = 1'b0;
                        ret_restore_w[d] = 1'b1;
                    end
                    DOM_PU_ISO: begin
                        clk_en_w[d] = 1'b1;
                        iso_en_w[d] = 1'b0;
                        rst_n_w[d] = 1'b1;
                        ret_save_w[d] = 1'b0;
                        ret_restore_w[d] = 1'b0;
                    end
                    default: begin
                        clk_en_w[d] = 1'b1;
                        iso_en_w[d] = 1'b0;
                        rst_n_w[d] = 1'b1;
                        ret_save_w[d] = 1'b0;
                        ret_restore_w[d] = 1'b0;
                    end
                endcase
            end

        end : g_dom_seq
    endgenerate

    // ── Map per-domain arrays to named output ports ─────────────────────────
    assign cpu_clk_en_o      = clk_en_w[DOM_CPU];
    assign cpu_iso_en_o      = iso_en_w[DOM_CPU];
    assign cpu_rst_n_o       = rst_n_w[DOM_CPU];
    assign cpu_ret_save_o    = ret_save_w[DOM_CPU];
    assign cpu_ret_restore_o = ret_restore_w[DOM_CPU];

    assign gpu_clk_en_o      = clk_en_w[DOM_GPU];
    assign gpu_iso_en_o      = iso_en_w[DOM_GPU];
    assign gpu_rst_n_o       = rst_n_w[DOM_GPU];
    assign gpu_ret_save_o    = ret_save_w[DOM_GPU];
    assign gpu_ret_restore_o = ret_restore_w[DOM_GPU];

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
    assign hw_wdata[1]   = {29'b0, pmu_busy, gpu_domain_on, cpu_domain_on};

    assign hw_wen  [2]   = 1'b1;
    assign hw_wdata[2]   = {
        22'b0,
        ret_restore_w[DOM_GPU],
        ret_save_w[DOM_GPU],
        ret_restore_w[DOM_CPU],
        ret_save_w[DOM_CPU],
        rst_n_w[DOM_GPU],
        rst_n_w[DOM_CPU],
        iso_en_w[DOM_GPU],
        iso_en_w[DOM_CPU],
        clk_en_w[DOM_GPU],
        clk_en_w[DOM_CPU]
    };

endmodule : pmu
