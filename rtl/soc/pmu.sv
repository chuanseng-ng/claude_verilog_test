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
// (PD_CPU/PD_GPU/PD_SRAM/PD_PERIPH, ISO_CPU/ISO_GPU, the SOC_PST state group) that
// this module's outputs are named and ordered to match. tools/verif/check_upf.py
// (CI) checks the mode names/encodings below against that file.
//
// Power modes (2-bit CTRL[1:0], matches the phase5_soc.upf SOC_PST NORMAL/CPU_OFF/GPU_OFF/IDLE states):
//   00  NORMAL   — CPU on,  GPU on
//   01  CPU_OFF  — CPU off, GPU on
//   10  GPU_OFF  — CPU on,  GPU off
//   11  IDLE     — CPU off, GPU off
//
// Sequencing order (fixed by the UPF, not a design choice — see evaluation
// doc section 3 and phase5_soc.upf ISO_CPU/ISO_GPU; the UPF has no power
// switch, see below):
//   Power-down: assert *_ret_save -> assert *_iso_en -> gate clock (*_clk_en=0)
//               -> assert domain reset (*_rst_n=0).
//   Power-up:   release domain reset (*_rst_n=1) -> ungate clock (*_clk_en=1)
//               -> assert *_ret_restore -> de-assert *_iso_en.
// Each direction is walked one action per clk_i cycle through an explicit FSM
// (9 states per domain: ON, 4 power-down actions, OFF, 4 power-up actions) so
// the order above is structurally guaranteed and directly observable/
// assertable by verification. The CPU domain's two isolation states are the
// exception: they WAIT for the isolation handshake described next. A domain's target (from CTRL) is only re-sampled
// while the domain is settled at ON or OFF — a request that changes mid-
// sequence does not reverse the in-flight sequence, it takes effect once the
// current one completes. This avoids ill-defined half-isolated / half-gated
// states.
//
// Isolation handshake (bead 3ogd): the CPU domain runs on cpu_core_clk, an
// independent clock, so "iso_en raised" at this module's port is NOT "the
// clamp is active". soc_top carries cpu_iso_en_o through a 2-flop cdc_sync into
// cpu_core_clk (the clamp control, pmu_cpu_iso_en_sync), whereas cpu_rst_n_o
// reaches the CPU domain through a cdc_reset_sync whose ASSERTION is
// asynchronous: the reset bites on the very core_clk edge this module drops it.
// With the two merely spaced 2 clk_i cycles apart, "isolate first" held only
// while 2 x cpu_core_clk period < 2 x clk_i period. cpu_iso_ack_i closes the
// loop: soc_top synchronises the CPU-domain clamp control BACK into clk_i
// (u_cpu_iso_ack_sync, a cdc_sync) and feeds it here, and the sequencer
//   * power-down: holds DOM_PD_ISO until cpu_iso_ack_i == 1 -- the clamp is
//     observed active in the CPU domain -- and only then gates the clock
//     (DOM_PD_GATE) and asserts reset (DOM_OFF). The ack is the registered
//     output of a synchroniser, so it can only be late, never early: the order
//     holds for ANY ratio between the two clocks.
//   * power-up: holds DOM_PU_ISO (iso_en_o already de-asserted) until
//     cpu_iso_ack_i == 0 before settling at DOM_ON. This is the return-to-zero
//     half of a 4-phase handshake, and it is REQUIRED, not decoration: the
//     de-assert is still travelling through two synchronisers when the walk
//     reaches DOM_ON, so a power-down requested straight away would otherwise
//     meet the previous cycle's still-high ack in DOM_PD_ISO and gate the clock
//     and assert reset with no clamp (a stale ack). STATUS.cpu_domain_on now also
//     means "the clamp has been seen released in the CPU domain".
// Power-up needs NO ack for the iso-release-vs-reset-release order (the UPF's
// last step, de-assert iso, stays last). The release can only be observed by
// the clamp's consumers through paths that are structurally behind the reset
// release: u_cpu_cg is forbidden to open (cpu_gated_clk_en includes
// pmu_cpu_rst_n_cpu_sync) until the reset release is observed in the CPU
// domain, and every sampler of the clamped lines (u_cpu_axi_cdc's s-side, the
// CPU) runs on cpu_gated_clk. A clamp released one cpu_core_clk edge early
// (a metastable first stage in silicon) therefore exposes only retained,
// unsampled values on a still-stopped clock; the same-clock 2-flop paths of
// the reset and the clamp keep the nominal order. The hazard on the way up is
// "iso released too EARLY", which the 3-clk_i-cycle gap already makes the
// non-nominal case; the way down is "iso applied too LATE", unbounded in the
// ratio, hence the ack there.
// The GPU domain needs no ack: u_gpu is on clk_i/core_clk, the clamp control is
// the PMU's own flop (pmu_gpu_iso_en, no synchroniser) and gpu_rst_n is another
// flop on the same edge, so the 2-cycle spacing is exact. Internally its ack is
// iso_en_q itself (satisfied the cycle it is raised, and dropped the cycle it is
// released), which makes both waits zero-length and leaves its walk unchanged.
// Timeout: a wait on an ack that can never come (CPU PLL domain dead:
// cpu_core_rst_n low holds the clamp synchroniser at 0; reachable by
// firmware writing APB_PLL2 pll_enable=0) would hang the always-on PMU in
// DOM_PD_ISO with STATUS.busy stuck. After ISO_ACK_TIMEOUT clk_i cycles in one
// wait the sequencer proceeds as if acked and sets STATUS[3]
// (cpu_iso_ack_timeout), sticky until the next CPU power-down begins. Proceeding
// is safe in exactly the case that produces it: a domain whose clock/reset is
// dead is not driving anything the clamp would hold. ISO_ACK_TIMEOUT must exceed
// the worst-case ack round trip, ~(3 x R + 3) clk_i cycles for a cpu_core_clk
// R times slower than clk_i (3 cpu edges to cross, 3 clk_i edges back); the
// default 255 covers R up to ~80. If it is too small the timeout fires on a
// live domain and the ordering guarantee is lost, loudly (STATUS[3]).
//
// Registered outputs (bead ktwt): every *_clk_en_o / *_iso_en_o / *_rst_n_o /
// *_ret_save_o / *_ret_restore_o is the Q of a dedicated flop, never a
// combinational decode of the binary dom_state_q. soc_top feeds these to
// cdc_sync D pins, to the ASYNC clear of u_cpu_pmu_rst_sync and (GPU) to an
// async reset and an isolation mux select, where a decode glitch is an event
// (a Vivado CDC triage found glitch-capable transitions on 4 of the 9 state
// changes, including a runt reset on DOM_PU_RESTORE -> DOM_PU_ISO). The flops
// load the decode of the NEXT state, so every output is visible in exactly the
// cycle the old combinational decode showed it: no latency change, the UPF
// order and the one-action-per-cycle walk are untouched. The reset values are
// the DOM_ON decode (see "Reset defaults" below).
//
// Retention scope (explicit no-op): cpu_ret_save_o/cpu_ret_restore_o (and GPU
// equivalents) are emitted in the correct order for verification to assert,
// but there is no retention-cell silicon in this model (phase5_soc.upf header,
// "Retention: NONE"). Because the domain's reset is only
// ever asserted while its clock is already gated (DOM_PD_GATE precedes DOM_OFF)
// and is always released before the clock is ungated (DOM_PU_RST precedes
// DOM_PU_CLK), the domain's own flops never see an active clock edge while
// held in reset. What that buys depends on the domain's reset style (bead
// 4a7i):
//   - CPU domain (SYNCHRONOUS reset, `always_ff @(posedge clk)`): a reset
//     that is asserted and released entirely while the clock is gated never
//     takes effect, so CPU flop state (e.g. MSTATUS/MTVEC/PC) survives a PMU
//     off->on cycle. This is a BEHAVIOURAL-MODEL ARTIFACT of clock-gating
//     instead of supply removal, not retention.
//   - GPU domain (ASYNCHRONOUS reset, `always_ff @(posedge clk or negedge
//     rst_n)` in gpu_top / gpu_compute_unit / warp_scheduler / ...): asserting
//     pmu_gpu_rst_n clears the flops immediately despite the gated clock, so
//     GPU state (irq latch, GPU_CTRL.irq_enable, STATUS.done, ...) is LOST
//     across a PMU off->on cycle. Repro: tb/cocotb/soc/test_soc_integration.py
//     ::test_soc_gpu_isolation_via_pmu.
// Neither domain models real retention. Real silicon with no retention cells
// (the Phase 5 case) loses state in both domains on supply-off, so the GPU
// behaviour is the realistic one. Software must re-initialise the GPU after
// every PMU power-up and must not rely on CPU state surviving either.
//
// Isolation: cpu_iso_en_o / gpu_iso_en_o are ACTIVE-HIGH (phase5_soc.upf
// ISO_CPU/ISO_GPU, `-isolation_sense high`, `-clamp_value 0`, `-applies_to
// outputs`, `-location parent`) — this module only computes the *_iso_en
// control signal; the actual output-clamp muxes live in soc_top (outside
// u_cpu/u_gpu, in the always-on PD_PERIPH domain), per the UPF's
// `-location parent` placement. See soc_top.sv for the clamp scope/rationale.
//
// This module deliberately does NOT emit cpu_pg_ctrl/gpu_pg_ctrl (power-
// switch control signals). phase5_soc.upf therefore has no create_power_switch
// either (bead h3lm: its former PSW_CPU/PSW_GPU named these nonexistent ports
// and used invalid options); VDD_CPU/VDD_GPU are modelled as supply ports. Real power
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
//           [3]    cpu_iso_ack_timeout — STICKY. 1 when a CPU isolation-ack
//                                  wait expired (ISO_ACK_TIMEOUT cycles with no
//                                  ack / no ack release; see "Isolation
//                                  handshake"). Cleared by reset and when the
//                                  next CPU power-down begins.
//           [31:4] reserved (RO 0)
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
    parameter int unsigned ADDR_W = 12,  // local byte address width (4 KB slot)
    // Cycles the CPU isolation-ack wait may last before the sequencer proceeds and flags
    // STATUS[3] (see "Isolation handshake"). >= 2; elaboration guard below.
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

    // Registered sequencing outputs (ktwt). These drive cdc_sync D pins and the
    // ASYNC clear of u_cpu_pmu_rst_sync in soc_top, and (GPU) the async reset
    // and the handshake isolation mux of the GPU domain. A combinational
    // decode of the 4-bit binary dom_state_q can glitch when several state
    // bits change on one edge (4 of the 9 transitions; a runt reset on
    // DOM_PU_RESTORE -> DOM_PU_ISO), and a glitch on an async clear or a
    // synchroniser D pin is a real event. Each output is therefore the Q of
    // its own flop, loaded with the decode of the NEXT state: the value seen
    // at cycle t is exactly decode(dom_state_q at t), so no output moves one
    // cycle earlier or later than in the combinational version (UPF order and
    // test_pmu's per-cycle expectations are unchanged).
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

    // Isolation handshake (bead 3ogd, see header). iso_ack_w[d] is the acknowledge the sequencer
    // waits on; wait_hit[d] is the (CPU only) timeout expiring in a wait state; both are inputs
    // to the NEXT-state logic only, never to an output decode.
    logic iso_ack_w [N_DOM];
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
                    DOM_PD_SAVE:    dom_state_d[d] = DOM_PD_ISO;
                    // Hold until the clamp is acknowledged (or the wait times out).
                    DOM_PD_ISO:     dom_state_d[d] = (iso_ack_w[d] || wait_hit[d]) ? DOM_PD_GATE
                                                                                   : DOM_PD_ISO;
                    DOM_PD_GATE:    dom_state_d[d] = DOM_OFF;
                    DOM_OFF:        dom_state_d[d] = dom_target_on[d] ? DOM_PU_RST : DOM_OFF;
                    DOM_PU_RST:     dom_state_d[d] = DOM_PU_CLK;
                    DOM_PU_CLK:     dom_state_d[d] = DOM_PU_RESTORE;
                    DOM_PU_RESTORE: dom_state_d[d] = DOM_PU_ISO;
                    // Hold until the release is acknowledged (4-phase RZ; see header).
                    DOM_PU_ISO:     dom_state_d[d] = (!iso_ack_w[d] || wait_hit[d]) ? DOM_ON
                                                                                    : DOM_PU_ISO;
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
                    DOM_PD_ISO: begin
                        clk_en_d[d] = 1'b1;
                        iso_en_d[d] = 1'b1;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                    DOM_PD_GATE: begin
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
                    DOM_PU_CLK: begin
                        clk_en_d[d] = 1'b1;
                        iso_en_d[d] = 1'b1;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b0;
                    end
                    DOM_PU_RESTORE: begin
                        clk_en_d[d] = 1'b1;
                        iso_en_d[d] = 1'b1;
                        rst_n_d[d] = 1'b1;
                        ret_save_d[d] = 1'b0;
                        ret_restore_d[d] = 1'b1;
                    end
                    DOM_PU_ISO: begin
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

            // ── State + output registers (synchronous reset -- see header) ──
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

                assign iso_ack_w[d] = cpu_iso_ack_i;

                // In DOM_PD_ISO the wait is on ack rising, in DOM_PU_ISO on ack falling.
                assign wait_active =
                    ((dom_state_q[d] == DOM_PD_ISO) && !iso_ack_w[d]) ||
                    ((dom_state_q[d] == DOM_PU_ISO) &&  iso_ack_w[d]);
                assign wait_hit[d] = wait_active && (wait_cnt_q == CW'(ISO_ACK_TIMEOUT - 1));

                always_ff @(posedge clk_i) begin
                    if (!rst_n_i) begin
                        wait_cnt_q       <= '0;
                        cpu_iso_ack_to_q <= 1'b0;
                    end else begin
                        // Counts the cycles spent waiting; any cycle that is not a wait (ack seen,
                        // or another state) restarts it, so every wait gets the full timeout.
                        if (wait_active && !wait_hit[d]) wait_cnt_q <= wait_cnt_q + CW'(1);
                        else                             wait_cnt_q <= '0;
                        // Sticky until the next CPU power-down begins.
                        if (dom_state_q[d] == DOM_ON && !dom_target_on[d]) cpu_iso_ack_to_q <= 1'b0;
                        else if (wait_hit[d])                              cpu_iso_ack_to_q <= 1'b1;
                    end
                end
            end else begin : g_ack_none
                // Same-clock domain: the clamp control IS the PMU flop, so it is "acknowledged"
                // the cycle it is raised and "released" the cycle it is dropped. Both waits are
                // zero-length and there is no timeout to flag.
                assign iso_ack_w[d] = iso_en_q[d];
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
