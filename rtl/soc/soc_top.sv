// soc_top.sv
// Phase 5 (M8) / Phase 7 (M-c) / APB migration PR-7 — RV32I + GPU-Lite SoC top-level.
//
// Architecture:
//   Data plane  : AXI4 crossbar, N_MASTERS=4, N_SLAVES=3
//     M0 = CPU (rv32i_cpu_top AXI4 master)
//     M1 = GPU ifetch (axilite_to_axi4 read-only adapter)
//     M2 = GPU data  (gpu_top m_axi_*)
//     M3 = DMA       (dma_engine m_*)
//     S0 = Boot ROM  (boot_rom, 0x0000_1000–0x0000_1FFF)
//     S1 = SRAM ctrl (sram_controller, 0x0000_2000–0x0FFF_FFFF)
//     S2 = Periph    (axi4_to_axilite → axi_lite_interconnect, 0x2000_1000–9FFF)
//
//   Control plane : axi4_to_axilite → axi_lite_interconnect (N_SLAVES=3)
//     AXIL_GPU=0        @ 0x2000_1000–1FFF  (AXI-Lite direct)
//     AXIL_APB_BRIDGE=1 @ 0x2000_2000–9FFF  (axil_to_apb → apb_interconnect)
//     AXIL_DMA=2        @ 0x2000_5000–5FFF  (AXI-Lite direct; last-match wins
//                                             over APB_BRIDGE window overlap)
//
//   APB sub-tree (7 slaves behind axil_to_apb bridge):
//     APB_UART=0  @ 0x2000_2000–2FFF  uart_controller
//     APB_SPI=1   @ 0x2000_3000–3FFF  spi_controller
//     APB_TIMER=2 @ 0x2000_4000–4FFF  timer
//     APB_IRQ=3   @ 0x2000_6000–6FFF  interrupt_controller
//     APB_PLL=4   @ 0x2000_7000–7FFF  pll_apb_regs (clk_i domain — system/fabric PLL)
//     APB_PMU=5   @ 0x2000_8000–8FFF  pmu (core_clk domain; GH #99/#100)
//     APB_PLL2=6  @ 0x2000_9000–9FFF  pll_apb_regs (cpu_clk_i domain — CPU-domain
//                                      PLL, GH #92; output unconsumed until GH #93)
//
//   Debug plane   : APB3 debug slave exposed at top-level ports, bridged into
//     the CPU domain by apb_cdc_bridge (u_apb_dbg_cdc, GH #95) — see the
//     clock-seam note below.
//
//   Clock seam (Phase 7 M-c / GH #92 dual PLL; GH #93 makes the CPU domain
//   real — two genuine, non-identical clock roots with one intentional CDC
//   boundary at the CPU<->fabric AXI4 interface):
//     clk_i is the external SYSTEM/FABRIC reference clock (100 MHz crystal/XO).
//       pll_clkgen converts it to core_clk (1.282 GHz in RNM; ref passthrough
//       in stub). All child instances except the CPU run on core_clk.
//       core_rst_n = rst_n_i & pll_locked so children are held in reset until
//       PLL locks. PLL_IMPL parameter selects "STUB" (default, synth-safe) or
//       "RNM" (M-c cosim).
//     cpu_clk_i is a SECOND, independent CPU-domain reference clock input
//       (GH #92), feeding its own pll_subsystem instance (u_cpu_pll_sub) to
//       produce cpu_core_clk / cpu_core_rst_n / cpu_pll_locked. This gives PD
//       two genuine, non-identical clock roots for the two create_clock
//       statements in GH #94 (pll_clkgen_stub.sv is a pure ref_clk passthrough
//       with no divide/multiply, so two instances fed from ONE reference would
//       be bit-identical clocks with zero real CDC coverage).
//     GH #93: the CPU (u_cpu) and its clock gate (u_cpu_cg) now run on
//       cpu_core_clk / cpu_gated_clk instead of core_clk. Every signal that
//       crosses the cpu_core_clk <-> core_clk boundary is enumerated below —
//       nothing crosses unsynchronised:
//         * CPU AXI4 master <-> crossbar M0: rtl/soc/async_axi_fifo.sv
//           (u_cpu_axi_cdc) — dual-clock gray-FIFO bridge, GH #91.
//           GH #95 / bead claude_verilog_test-2k8 fix: its s_rst_n_i is
//           cpu_core_rst_n (this domain's true POR/PLL-lock reset), NOT
//           cpu_domain_rst_n — a PMU-driven power-cycle must RETAIN this
//           bridge's state exactly like it retains u_cpu, not hard-flush it;
//           see the full rationale at u_cpu_axi_cdc's instantiation below.
//         * APB_PLL2 (u_cpu_pll_sub) <-> apb_interconnect: rtl/soc/
//           apb_cdc_bridge.sv (u_apb_pll2_cdc, new in GH #93) — 2-phase
//           toggle handshake; see that file's header for the protocol.
//         * pmu_cpu_clk_en (core_clk, drives u_cpu_cg's enable): synchronised
//           INVERTED, as pmu_cpu_clk_dis_sync (cdc_2ff_sync of ~pmu_cpu_clk_en),
//           clocked by cpu_core_clk (NOT cpu_gated_clk — see the bootstrap-
//           deadlock note above u_cpu_clk_dis_sync below). GH #93-fix
//           (originally landed as pmu_cpu_clk_en_sync, non-inverted): a
//           non-inverted enable sync resets to 0 (disabled) while
//           cpu_core_rst_n is low, stopping cpu_gated_clk for the CPU's
//           entire reset window and making u_cpu's synchronous reset
//           unloadable. Inverting so the synchronised value is "disabled"
//           (0 = not disabled = clock runs) makes cdc_2ff_sync's reset-to-0
//           behavior the SAFE state instead of the unsafe one. See the
//           detailed ordering note above u_cpu_clk_dis_sync below.
//         * pmu_cpu_rst_n (core_clk, ANDed into cpu_domain_rst_n): cdc_reset_sync
//           clocked by cpu_core_clk.
//         * pmu_cpu_iso_en (core_clk, clamps the CPU->fabric handshake):
//           cdc_2ff_sync clocked by cpu_core_clk; the clamp itself now lives
//           at the async_axi_fifo s_* (CPU-domain) face — see clamp-scope
//           note below.
//         * ext_irq / timer_irq (core_clk, level-held sources — see
//           interrupt_controller.sv / timer.sv headers): cdc_2ff_sync each,
//           clocked by cpu_core_clk.
//         * apb_* top-level debug port (core_clk, chip-boundary bus) <->
//           u_cpu's APB3 debug slave: rtl/soc/apb_cdc_bridge.sv
//           (u_apb_dbg_cdc, GH #95 fix, bead claude_verilog_test-eg2) — same
//           2-phase toggle handshake as u_apb_pll2_cdc, s-face core_clk,
//           m-face cpu_gated_clk/cpu_domain_rst_n. Closes the cdc_snitch
//           BAD=233 finding left when GH #93 moved u_cpu onto cpu_gated_clk
//           without re-homing this chip-boundary bus.
//       In a single-clock build, tie cpu_clk_i == clk_i and cpu_rst_n_i ==
//       rst_n_i at the integration site (see tb_soc_top.sv / tb_soc_pll.sv for
//       the reference tie-off) — every crossing above degenerates to a 1:1
//       ratio synchroniser, which async_axi_fifo / cdc_2ff_sync / cdc_reset_sync
//       all handle correctly (no bypass path; see async_axi_fifo.sv header).
//     Known hazard NOT fixed here (documented, reported to the user): the
//       PMU's CPU power-down sequence has no drain/quiesce step. This
//       paragraph pre-dates the GH #95 / bead claude_verilog_test-2k8 fix
//       below u_cpu_axi_cdc's instantiation — that fix rewired
//       u_cpu_axi_cdc's s_rst_n_i from cpu_domain_rst_n to cpu_core_rst_n,
//       which CLOSES the specific mechanism this paragraph originally
//       described (pmu_cpu_rst_n asserting no longer hard-flushes this CDC
//       bridge, since cpu_core_rst_n does not respond to pmu_cpu_rst_n). The
//       BROADER gap remains open, do not read the above as resolving it:
//       axi4_crossbar's per-slave engine (locked to one master for a
//       transaction's lifetime, see axi4_crossbar.sv:9-12,26-27) has no
//       drain FSM at all, so a genuine mid-burst reset event of the crossbar
//       or SRAM/boot-ROM slave side (a true cold reset, not a PMU power-
//       cycle) can still leave a slave engine waiting for a B/R response
//       that will never arrive, wedging that engine. This hazard already
//       existed in the single-clock design and is unrelated to the CDC
//       bridge's own retain-vs-flush behavior; it is Phase 6 scope (PULP-
//       style axi_isolate: count outstanding transactions, assert
//       isolated_o only at zero, then reset) — no drain FSM added here.
//
//   Power management (Pre-Phase-6 #5, GH #98/#99/#100 — behavioral PMU only,
//   see docs/POWER_DOMAIN_EVALUATION.md):
//     pmu (APB_PMU slot) sequences PD_CPU/PD_GPU per phase5_soc.upf: drives
//     cpu_clk_en/gpu_clk_en into rv32i_clock_gate cells that gate core_clk
//     before it reaches u_cpu/u_gpu, cpu_iso_en/gpu_iso_en into output-clamp
//     muxes on the CPU/GPU->fabric handshake signals (ISO_CPU/ISO_GPU,
//     `-location parent`, clamp_value 0), and per-domain resets ANDed with
//     core_rst_n. Reset default (NORMAL, both domains DOM_ON) is functionally
//     identical to the pre-PMU wiring, so soc_all is unaffected unless
//     firmware writes pmu CTRL. Real power-switch/retention silicon remains
//     out of scope (UPF-sim-tooling gated) — see pmu.sv header.
//
//   IRQ routing:
//     irq_src_i = {gpu_irq_o[4], dma_irq[3], timer_irq[2], spi_irq[1], uart_irq[0]}
//     interrupt_controller.irq_o → CPU ext_irq_i (MEIP)
//     timer.irq_o                → CPU timer_irq_i (MTIP, direct)
//
// Rules: no logic beyond wiring; clk/rst_n rooted at clk_i/rst_n_i (except the
// PMU clock-gate/isolation/reset muxing on the CPU/GPU domains, documented above).
// M7 perf-counter observability outputs from CPU left unconnected (M7 bead).
//
// Lint target: verilator -Wall 0 errors 0 warnings.

`default_nettype none

module soc_top
    import axi_pkg::*;
    import soc_addr_map_pkg::*;
    import soc_periph_map_pkg::*;
#(
    // Boot ROM hex image.  Empty string → ROM initialises to zero.
    // Set at elaboration time by the cocotb test wrapper (tb_soc_top).
    parameter string MEM_INIT_FILE = "",

    // Behavioral SRAM depth in 32-bit words (Phase 5 M10 benchmark support).
    // Forwarded into the sram_controller MEM_WORDS parameter below.
    parameter int unsigned SRAM_MEM_WORDS = 1024,

    // PLL implementation selector (Phase 7 M-c).
    //   "STUB" (default) — synthesisable digital stub; out_clk = ref_clk.
    //   "RNM"            — real-number model; use only for M-c AMS co-sim.
    parameter string PLL_IMPL = "STUB"
) (
    // clk_i is the SYSTEM/FABRIC reference clock input (100 MHz crystal / XO).
    // Internally the SoC runs on core_clk derived from the PLL.
    // In STUB mode core_clk == clk_i (lock counter fires after 16 cycles).
    input  logic clk_i,
    input  logic rst_n_i,

    // cpu_clk_i / cpu_rst_n_i (GH #92): a SECOND, independent CPU-domain
    // reference clock/reset pair, feeding its own pll_subsystem instance
    // (u_cpu_pll_sub). GH #93: the CPU (u_cpu) is now re-sourced from this
    // domain (cpu_core_clk / cpu_gated_clk) — every crossing back into the
    // core_clk fabric domain is synchronised (see clock-seam header note
    // above). In a single-clock build, tie cpu_clk_i == clk_i and
    // cpu_rst_n_i == rst_n_i.
    input  logic cpu_clk_i,
    input  logic cpu_rst_n_i,

    // ── APB3 debug slave (pass-through to CPU) ───────────────────────────────
    input  logic [11:0] apb_paddr_i,
    input  logic        apb_psel_i,
    input  logic        apb_penable_i,
    input  logic        apb_pwrite_i,
    input  logic [31:0] apb_pwdata_i,
    output logic [31:0] apb_prdata_o,
    output logic        apb_pready_o,
    output logic        apb_pslverr_o,

    // ── UART ─────────────────────────────────────────────────────────────────
    output logic uart_tx_o,
    input  logic uart_rx_i,

    // ── SPI ──────────────────────────────────────────────────────────────────
    output logic spi_sclk_o,
    output logic spi_mosi_o,
    input  logic spi_miso_i,
    output logic spi_cs_n_o,

    // ── Observability (subset; M7 perf counters added later) ─────────────────
    output logic        commit_valid_o,
    output logic [31:0] commit_pc_o,
    output logic [31:0] commit_insn_o,
    output logic        gpu_irq_o,

    // ── PLL status (Phase 7 M-c; GH #92 adds the CPU-domain PLL) ──────────────
    output logic        pll_locked_o,       // 1 when system/fabric PLL has acquired lock
    output logic        cpu_pll_locked_o    // 1 when CPU-domain PLL has acquired lock
);

    // =========================================================================
    // Local parameters
    // =========================================================================
    localparam int unsigned N_MASTERS   = 4;
    localparam int unsigned AW          = AXI_ADDR_WIDTH;
    localparam int unsigned DW          = AXI_DATA_WIDTH;
    localparam int unsigned SW          = AXI_STRB_WIDTH;
    localparam int unsigned IW          = AXI_ID_WIDTH;
    localparam int unsigned LENW        = AXI_LEN_WIDTH;

    // =========================================================================
    // Phase 7 M-c / Pre-Phase-6 #3: PLL subsystem
    //   clk_i  → pll_subsystem.clk_i
    //   core_clk   = pll_subsystem.core_clk   (all children run on this)
    //   core_rst_n = pll_subsystem.core_rst_n  (rst_n_i & pll_locked)
    //
    // pll_clkgen + pll_apb_regs + reset glue are consolidated inside
    // pll_subsystem (rtl/soc/pll/pll_subsystem.sv).
    // The clk_i-domain rule is preserved: pll_subsystem runs entirely on
    // clk_i / rst_n_i (see pll_subsystem.sv header for the full rationale).
    // =========================================================================
    logic core_clk;     // PLL output clock — feeds all child clk ports
    logic core_rst_n;   // gated reset: rst_n_i & pll_locked (from pll_subsystem)
    logic pll_locked;   // raw PLL lock flag — export to top-level port

    // =========================================================================
    // GH #92/#93: second (CPU-domain) PLL subsystem — now the CPU's real
    // clock root.
    //   cpu_clk_i → u_cpu_pll_sub.clk_i  (independent reference clock root)
    //   cpu_core_clk / cpu_core_rst_n feed u_cpu_cg and the CPU-domain reset
    //   tree below (GH #93 — see "PMU sequencing nets" / "CPU-domain reset
    //   tree" sections further down). cpu_pll_locked is exported at
    //   cpu_pll_locked_o.
    // =========================================================================
    logic cpu_core_clk;
    logic cpu_core_rst_n;
    logic cpu_pll_locked;   // raw CPU-domain PLL lock flag — export to top-level port

    // =========================================================================
    // Crossbar master-facing nets (no ID, unpacked arrays [N_MASTERS])
    // =========================================================================
    // Write address
    logic [N_MASTERS-1:0][AW-1:0] xbar_m_awaddr;
    logic [N_MASTERS-1:0][LENW-1:0] xbar_m_awlen;
    logic [N_MASTERS-1:0][2:0] xbar_m_awsize;
    logic [N_MASTERS-1:0][1:0] xbar_m_awburst;
    logic [N_MASTERS-1:0] xbar_m_awvalid;
    logic [N_MASTERS-1:0] xbar_m_awready;
    // Write data
    logic [N_MASTERS-1:0][DW-1:0] xbar_m_wdata;
    logic [N_MASTERS-1:0][SW-1:0] xbar_m_wstrb;
    logic [N_MASTERS-1:0] xbar_m_wlast;
    logic [N_MASTERS-1:0] xbar_m_wvalid;
    logic [N_MASTERS-1:0] xbar_m_wready;
    // Write response
    logic [N_MASTERS-1:0][1:0] xbar_m_bresp;
    logic [N_MASTERS-1:0] xbar_m_bvalid;
    logic [N_MASTERS-1:0] xbar_m_bready;
    // Read address
    logic [N_MASTERS-1:0][AW-1:0] xbar_m_araddr;
    logic [N_MASTERS-1:0][LENW-1:0] xbar_m_arlen;
    logic [N_MASTERS-1:0][2:0] xbar_m_arsize;
    logic [N_MASTERS-1:0][1:0] xbar_m_arburst;
    logic [N_MASTERS-1:0] xbar_m_arvalid;
    logic [N_MASTERS-1:0] xbar_m_arready;
    // Read data
    logic [N_MASTERS-1:0][DW-1:0] xbar_m_rdata;
    logic [N_MASTERS-1:0][1:0] xbar_m_rresp;
    logic [N_MASTERS-1:0] xbar_m_rlast;
    logic [N_MASTERS-1:0] xbar_m_rvalid;
    logic [N_MASTERS-1:0] xbar_m_rready;

    // =========================================================================
    // soc_bus flat slave-facing nets: ROM (S0) and SRAM (S1)
    // SLV_PERIPH (S2) is consumed inside soc_bus; no wires needed here.
    // =========================================================================
    // --- ROM (SLV_ROM) ---
    logic [IW-1:0]   bus_rom_awid;
    logic [AW-1:0]   bus_rom_awaddr;
    logic [LENW-1:0] bus_rom_awlen;
    logic [2:0]      bus_rom_awsize;
    logic [1:0]      bus_rom_awburst;
    logic            bus_rom_awvalid;
    logic            bus_rom_awready;
    logic [DW-1:0]   bus_rom_wdata;
    logic [SW-1:0]   bus_rom_wstrb;
    logic            bus_rom_wlast;
    logic            bus_rom_wvalid;
    logic            bus_rom_wready;
    logic [IW-1:0]   bus_rom_bid;
    logic [1:0]      bus_rom_bresp;
    logic            bus_rom_bvalid;
    logic            bus_rom_bready;
    logic [IW-1:0]   bus_rom_arid;
    logic [AW-1:0]   bus_rom_araddr;
    logic [LENW-1:0] bus_rom_arlen;
    logic [2:0]      bus_rom_arsize;
    logic [1:0]      bus_rom_arburst;
    logic            bus_rom_arvalid;
    logic            bus_rom_arready;
    logic [IW-1:0]   bus_rom_rid;
    logic [DW-1:0]   bus_rom_rdata;
    logic [1:0]      bus_rom_rresp;
    logic            bus_rom_rlast;
    logic            bus_rom_rvalid;
    logic            bus_rom_rready;
    // --- SRAM (SLV_SRAM) ---
    logic [IW-1:0]   bus_mem_awid;
    logic [AW-1:0]   bus_mem_awaddr;
    logic [LENW-1:0] bus_mem_awlen;
    logic [2:0]      bus_mem_awsize;
    logic [1:0]      bus_mem_awburst;
    logic            bus_mem_awvalid;
    logic            bus_mem_awready;
    logic [DW-1:0]   bus_mem_wdata;
    logic [SW-1:0]   bus_mem_wstrb;
    logic            bus_mem_wlast;
    logic            bus_mem_wvalid;
    logic            bus_mem_wready;
    logic [IW-1:0]   bus_mem_bid;
    logic [1:0]      bus_mem_bresp;
    logic            bus_mem_bvalid;
    logic            bus_mem_bready;
    logic [IW-1:0]   bus_mem_arid;
    logic [AW-1:0]   bus_mem_araddr;
    logic [LENW-1:0] bus_mem_arlen;
    logic [2:0]      bus_mem_arsize;
    logic [1:0]      bus_mem_arburst;
    logic            bus_mem_arvalid;
    logic            bus_mem_arready;
    logic [IW-1:0]   bus_mem_rid;
    logic [DW-1:0]   bus_mem_rdata;
    logic [1:0]      bus_mem_rresp;
    logic            bus_mem_rlast;
    logic            bus_mem_rvalid;
    logic            bus_mem_rready;

    // =========================================================================
    // APB nets: soc_bus apb_* ports → 5 APB peripherals
    // (previously apb_interconnect → peripherals; now routed through soc_bus)
    // =========================================================================
    localparam int unsigned N_APB_SLV = APB_N_SLAVES; // 7

    // Per-slave APB nets from soc_bus to each peripheral
    logic        apb_psel    [N_APB_SLV];
    logic        apb_penable [N_APB_SLV];
    logic        apb_pwrite  [N_APB_SLV];
    logic [31:0] apb_paddr   [N_APB_SLV];
    logic [31:0] apb_pwdata  [N_APB_SLV];
    logic [3:0]  apb_pstrb   [N_APB_SLV];
    logic [31:0] apb_prdata  [N_APB_SLV];
    logic        apb_pready  [N_APB_SLV];
    logic        apb_pslverr [N_APB_SLV];

    // =========================================================================
    // Pre-Phase-6 #5 (GH #98/#99/#100) — PMU sequencing nets
    // =========================================================================
    // CPU/GPU domain sequencing outputs from pmu (core_clk domain, PD_PERIPH).
    logic pmu_cpu_clk_en, pmu_gpu_clk_en;
    logic pmu_cpu_iso_en, pmu_gpu_iso_en;
    logic pmu_cpu_rst_n,  pmu_gpu_rst_n;
    /* verilator lint_off UNUSEDSIGNAL */
    logic pmu_cpu_ret_save, pmu_cpu_ret_restore;
    logic pmu_gpu_ret_save, pmu_gpu_ret_restore;
    /* verilator lint_on  UNUSEDSIGNAL */

    // Gated clocks (rv32i_clock_gate, glitch-free ICG) feeding u_cpu / u_gpu.
    logic cpu_gated_clk, gpu_gated_clk;

    // =========================================================================
    // GH #93: CPU-domain CDC synchronisers for the PMU control signals.
    //
    // pmu_cpu_clk_en / pmu_cpu_rst_n / pmu_cpu_iso_en are all generated in
    // the core_clk domain (by u_pmu below) but now gate/reset/clamp CPU-domain
    // (cpu_core_clk) logic, so each needs its own crossing.
    //
    // u_cpu_clk_dis_sync clock choice (bootstrap-deadlock avoidance): this
    // synchroniser MUST be clocked by cpu_core_clk, the UNGATED PLL output —
    // never by cpu_gated_clk. cpu_gated_clk is itself gated by this
    // synchroniser's own (inverted) output (via u_cpu_cg below); clocking the
    // synchroniser from its own gated output would mean the enable that
    // opens the gate can only advance once the gate is already open, a
    // circular dependency that never resolves. cpu_core_clk is the PLL's raw,
    // never-gated output, so it is always available to drive this crossing.
    //
    // ---- BUG (fixed here) + reset-release ordering, with cycle counts -----
    // The original (non-inverted) u_cpu_clk_en_sync synchronised pmu_cpu_clk_en
    // directly and was reset by cpu_core_rst_n. cdc_2ff_sync resets its flop
    // chain to 0 (see cdc_2ff_sync.sv), so that synchroniser's output was 0
    // (clock DISABLED) for the entire time cpu_core_rst_n was low, and for
    // STAGES=2 more cpu_core_clk edges after cpu_core_rst_n released (pipeline
    // fill latency) before it could reach 1. Meanwhile pmu_cpu_rst_n defaults
    // to 1 at the PMU's own reset (DOM_ON, see pmu.sv reset-defaults comment),
    // so u_cpu_pmu_rst_sync's chain filled to 1 within STAGES=2 cpu_core_clk
    // edges of cpu_core_clk simply toggling — independent of, and much faster
    // than, cpu_core_rst_n's release. Net effect: cpu_domain_rst_n
    // (= cpu_core_rst_n & pmu_cpu_rst_n_cpu_sync) tracked cpu_core_rst_n almost
    // exactly, releasing on the SAME edge cpu_core_rst_n released — the exact
    // edge at which cpu_gated_clk was still 2 cycles away from resuming. Zero
    // cpu_gated_clk edges ever occurred while cpu_domain_rst_n was low, so
    // u_cpu's `if (!rst_n_i) ... else ...` synchronous reset never executed
    // its reset branch.
    //
    // Fix: synchronise the INVERTED enable, pmu_cpu_clk_dis_sync = sync(
    // ~pmu_cpu_clk_en). cdc_2ff_sync's reset-to-0 value now means "NOT
    // disabled", i.e. the safe/reset state is "clock running", not "clock
    // stopped". u_cpu_cg's en input is ~pmu_cpu_clk_dis_sync.
    //
    // Revised ordering (cold-boot / PLL-(re)lock, the scenario this bug
    // report is about): while cpu_core_rst_n is low, pmu_cpu_clk_dis_sync is
    // held at its async-reset value of 0 (not disabled), so
    // cpu_gated_clk = cpu_core_clk unconditionally for the ENTIRE duration
    // cpu_core_rst_n (and therefore cpu_domain_rst_n, which can only release
    // no earlier than cpu_core_rst_n) is low — i.e. as many cpu_gated_clk
    // edges as cpu_core_rst_n's assertion lasts (STUB_LOCK_CYCLES=16 in the
    // PLL stub, or the real PLL's lock time), far more than the 1 edge
    // u_cpu's synchronous reset needs to load RESET_PC and its other reset
    // values. cpu_core_rst_n releases; pmu_cpu_rst_n_cpu_sync is already 1
    // (per the analysis above); cpu_domain_rst_n releases on that same edge,
    // and cpu_gated_clk has been ticking every cycle before, through, and
    // after that edge — no gap, so the release edge itself is also cleanly
    // observed by u_cpu. Only afterward, once firmware ever asserts
    // pmu_cpu_clk_en=0, does pmu_cpu_clk_dis_sync begin tracking it (2-cycle
    // pipeline latency), which is the normal, intended clock-gating path.
    //
    // GH #90 bead 542 fix (live PMU power-cycle ordering hazard, found during
    // the GH #93 sanity check above and deliberately deferred at the time):
    // pmu.sv's per-domain sequencer asserts rst_n_w=1 one full core_clk cycle
    // BEFORE it asserts clk_en_w=1 on the power-UP path (DOM_PU_RST releases
    // reset; DOM_PU_CLK, the next state, ungates the clock) — and mirrors
    // that on power-DOWN (clk_en_w drops one cycle before rst_n_w drops).
    // This ordering is NOT a pmu.sv implementation choice: docs/
    // POWER_DOMAIN_EVALUATION.md section 3 and pmu.sv's own header fix this
    // order as the UPF-mandated sequence, and it is the mechanism that lets
    // this behavioral model preserve CPU architectural state (PC/MSTATUS/
    // MTVEC) across an off->on cycle WITHOUT real retention-cell silicon: as
    // long as u_cpu's clock never ticks while its domain reset is asserted,
    // its synchronous `if (!rst_n)` branch never executes during a PMU
    // power-cycle, so its flops simply hold whatever value they had before
    // the domain went quiet. Editing pmu.sv's state order to fix this bead
    // would either violate that documented UPF sequencing or defeat the
    // retention-by-construction trick (see pmu.sv header) — so this fix is
    // deliberately in soc_top.sv, not pmu.sv.
    //
    // Hazard: pmu_cpu_rst_n and pmu_cpu_clk_en are two independently-timed
    // core_clk-domain signals crossing into the asynchronous, independently-
    // clocked (GH #92 dual-PLL) cpu_core_clk domain through two SEPARATE
    // synchronisers (u_cpu_pmu_rst_sync / u_cpu_clk_dis_sync above). Two
    // independent synchronisers do not preserve a source-side 1-cycle
    // offset — after crossing, either signal can settle first, in either
    // direction, for any relative skew. If pmu_cpu_clk_dis_sync clears
    // (clock re-enabled) at or before pmu_cpu_rst_n_cpu_sync releases, the
    // CPU domain would see a clock edge while cpu_domain_rst_n is still low,
    // its synchronous reset branch would fire, and the "retained" PC/state
    // this power-cycle was supposed to preserve would be silently
    // overwritten with RESET_PC/RESET_VAL instead — a data-corrupting CDC
    // race, not merely a missed reset.
    //
    // Fix: gate u_cpu_cg's enable with the ALREADY cpu_core_clk-domain-native
    // pmu_cpu_rst_n_cpu_sync (see cpu_gated_clk_en below, used at the u_cpu_cg
    // instantiation), so cpu_gated_clk is structurally forbidden from ticking
    // whenever the CPU-domain-observed PMU reset is asserted — regardless of
    // what pmu_cpu_clk_dis_sync (the independent clk-enable synchroniser) is
    // doing. This is a same-domain combinational AND of two flops already
    // registered on cpu_core_clk (pmu_cpu_rst_n_cpu_sync from
    // u_cpu_pmu_rst_sync, ~pmu_cpu_clk_dis_sync from u_cpu_clk_dis_sync) — it
    // adds no new CDC crossing and does not touch pmu.sv or any rtl/soc/cdc/*
    // primitive.
    //
    // Worst-case skew tolerance: UNBOUNDED. The fix does not rely on
    // bounding, matching, or reasoning about the relative latency of the two
    // independent synchronisers at all — it makes cpu_domain-observed PMU
    // reset the master gating term for the CPU's own clock, so no amount of
    // relative skew between u_cpu_pmu_rst_sync and u_cpu_clk_dis_sync can
    // produce a clock edge while that reset is asserted. It is symmetric
    // across both directions: on power-up, the gate cannot open until
    // pmu_cpu_rst_n_cpu_sync is already 1; on power-down, the gate closes the
    // instant pmu_cpu_rst_n_cpu_sync drops to 0, even if
    // pmu_cpu_clk_dis_sync has not yet caught up to reflect clk_en_w=0.
    //
    // Cold-boot regression check (GH #93's own fix, re-verified here): during
    // cpu_core_rst_n=0 (PLL not locked), the PMU's own dom_state_q is held at
    // its synchronous reset default DOM_ON (pmu.sv's rst_n_i is core_rst_n),
    // so pmu_cpu_rst_n=1 constant throughout — pmu_cpu_rst_n_cpu_sync tracks
    // to 1 well within cold boot's multi-cycle PLL-lock window and stays
    // there. cpu_gated_clk_en is therefore unaffected by this fix during cold
    // boot (gated only by ~pmu_cpu_clk_dis_sync, exactly as GH #93 left it) —
    // this fix only changes behavior once the PMU's OWN FSM genuinely drives
    // pmu_cpu_rst_n low, which happens only on a live, firmware-initiated
    // power-cycle.
    //
    // Test-suite note: test_pmu.py's DUT (tb_pmu.sv) instantiates pmu.sv
    // standalone with no CDC and no soc_top glue, so its per-cycle ordering
    // assertions exercise pmu.sv's own (unchanged) FSM outputs only and are
    // unaffected by this fix. soc_multiclock / soc_pll_multiclock exercise
    // soc_top's synchronisers at a divergent clock ratio but do not drive a
    // live PMU power-cycle, so they do not currently cover this path either
    // (see "Residual risk" callout in CLAUDE.md's GH #90 status entry).
    // =========================================================================
    logic pmu_cpu_clk_dis_sync;
    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (2)
    ) u_cpu_clk_dis_sync (
        .clk_i   (cpu_core_clk),
        .rst_n_i (cpu_core_rst_n),
        .d_i     (~pmu_cpu_clk_en),
        .q_o     (pmu_cpu_clk_dis_sync)
    );

    // pmu_cpu_iso_en: clamps the CPU->fabric AXI handshake at the
    // async_axi_fifo s_* (CPU-domain) face — see clamp-scope note below.
    // Clocked/reset the same way as u_cpu_clk_dis_sync, for the same reason
    // (this clamp gates signals that feed u_cpu_axi_cdc's s_* inputs, which
    // run on cpu_gated_clk; cpu_core_clk is the safe, always-running root).
    //
    // Safe-reset-value sanity check (GH #93-fix review): unlike the clk_en
    // crossing above, this one is NOT inverted, and that is correct.
    // cdc_2ff_sync resets pmu_cpu_iso_en_sync to 0 = "not isolated", which
    // matches pmu_cpu_iso_en's own PMU-side reset default (DOM_ON: iso_en_w=0,
    // see pmu.sv reset-defaults comment) — the synchroniser's safe state and
    // the source signal's safe state agree, so there is no cold-boot window
    // where this crossing disagrees with its source the way the un-inverted
    // clk_en sync did. (Whether "not isolated" is itself the physically safe
    // choice for isolation cells in general is a separate, pre-existing
    // design decision — see the ISO_CPU clamp-scope note below — not one this
    // fix revisits.)
    logic pmu_cpu_iso_en_sync;
    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (2)
    ) u_cpu_iso_en_sync (
        .clk_i   (cpu_core_clk),
        .rst_n_i (cpu_core_rst_n),
        .d_i     (pmu_cpu_iso_en),
        .q_o     (pmu_cpu_iso_en_sync)
    );

    // pmu_cpu_rst_n: synchronised into the cpu_core_clk domain with
    // cdc_reset_sync (async-assert / sync-deassert) — this is exactly the
    // "per-domain PMU reset" reuse cdc_reset_sync.sv's header anticipates.
    //
    // Ordering sanity check (GH #93-fix review): rst_n_i here is deliberately
    // pmu_cpu_rst_n, NOT cpu_core_rst_n. cdc_reset_sync's rst_n_i is the
    // SOURCE async reset event being synchronised into clk_i's domain (see
    // cdc_reset_sync.sv header and its other two uses inside
    // async_axi_fifo.sv, which feed it s_rst_n_i/m_rst_n_i — the real per-
    // domain reset events, never a foreign domain's reset). cpu_core_rst_n is
    // already NATIVE to the cpu_core_clk destination domain (produced by
    // u_cpu_pll_sub, synchronous to cpu_core_clk already), so it needs no
    // synchroniser of its own; it is combined with pmu_cpu_rst_n_cpu_sync by
    // the plain AND below instead. Feeding cpu_core_rst_n into this
    // synchroniser's rst_n_i in place of pmu_cpu_rst_n would be wrong (it
    // would synchronise the wrong signal) and feeding it in ADDITION (e.g. as
    // an extra async clear) would be redundant — cpu_domain_rst_n's
    // combinational AND already asserts whenever EITHER source is low. No
    // ordering surprise: this is the correct, intentional use of the
    // primitive.
    logic pmu_cpu_rst_n_cpu_sync;
    cdc_reset_sync #(
        .STAGES (2)
    ) u_cpu_pmu_rst_sync (
        .clk_i   (cpu_core_clk),
        .rst_n_i (pmu_cpu_rst_n),
        .rst_n_o (pmu_cpu_rst_n_cpu_sync)
    );

    // ext_irq / timer_irq: level-held sources (see interrupt_controller.sv /
    // timer.sv — irq_o is `|masked` / `irq_en & irq_pending_q`, both sticky
    // until explicitly cleared, never a single-cycle pulse), so a plain 2-FF
    // level synchroniser cannot miss the assertion — see soc_top.sv header
    // "IRQ routing" note.
    logic ext_irq_cpu_sync, timer_irq_cpu_sync;
    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (2)
    ) u_ext_irq_sync (
        .clk_i   (cpu_core_clk),
        .rst_n_i (cpu_core_rst_n),
        .d_i     (ext_irq),
        .q_o     (ext_irq_cpu_sync)
    );
    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (2)
    ) u_timer_irq_sync (
        .clk_i   (cpu_core_clk),
        .rst_n_i (cpu_core_rst_n),
        .d_i     (timer_irq),
        .q_o     (timer_irq_cpu_sync)
    );

    // =========================================================================
    // GH #93: per-domain reset trees.
    //
    // CPU domain: recomposed entirely from CPU-domain-synchronised sources —
    // cpu_core_rst_n (this domain's own PLL-lock reset) ANDed with
    // pmu_cpu_rst_n_cpu_sync (the PMU's per-domain reset, synchronised
    // above). core_rst_n does NOT appear in this expression any more; the CPU
    // domain reset is now fully rooted in its own clock domain.
    //
    // GPU/fabric domain: left UNCHANGED (core_rst_n & pmu_gpu_rst_n, no new
    // reset synchroniser added). Rationale: the GPU/bus/peripherals all still
    // share the single core_clk domain (only the CPU moved), so there is no
    // new clock boundary here to synchronise across, and gpu_domain_rst_n's
    // existing timing has 142/142 soc_all regression history behind it.
    // Inserting a cdc_reset_sync here would add STAGES cycles of reset-
    // deassert latency to every peripheral for zero CDC benefit and is
    // deliberately NOT done, to avoid perturbing that regression baseline.
    //
    // GH #93-fix note: cpu_domain_rst_n release timing (cold boot) and the
    // requirement that u_cpu see clock edges throughout its assertion are
    // analysed in full above u_cpu_clk_dis_sync — that is where the reset-
    // release ordering and cycle counts for this signal are documented, not
    // here, to keep the analysis next to the fix it justifies.
    //
    // GH #95 / bead claude_verilog_test-2k8 note: cpu_domain_rst_n correctly
    // remains u_cpu's own reset (retention-by-construction: it folds in the
    // PMU's retention-hold signal, which never fires cpu_gated_clk while
    // asserted — see u_cpu_cg's gating note above) and u_apb_dbg_cdc's m_*
    // face reset. It is DELIBERATELY NOT used as u_cpu_axi_cdc's s_rst_n_i —
    // that CDC bridge uses cpu_core_rst_n instead, because the bridge must
    // retain (not hard-flush) its in-flight state across a PMU power-cycle
    // just like u_cpu does. See the full rationale at u_cpu_axi_cdc's
    // instantiation below.
    // =========================================================================
    logic cpu_domain_rst_n, gpu_domain_rst_n;
    assign cpu_domain_rst_n = cpu_core_rst_n & pmu_cpu_rst_n_cpu_sync;
    assign gpu_domain_rst_n = core_rst_n & pmu_gpu_rst_n;

    // ISO_CPU / ISO_GPU clamp scope (functional isolation, `-location parent`,
    // clamp_value 0): the master-side AXI4 request/accept handshake signals
    // that leave each domain toward the always-on fabric, plus the domain's
    // top-level observability/IRQ outputs. Address/data/control payload bits
    // are NOT individually clamped -- they are qualified by the corresponding
    // valid signal (already forced to 0 below) and are therefore don't-care
    // downstream once valid=0, so clamping them adds no functional isolation
    // value in this cycle-accurate behavioral model. Slave-side (control-
    // register) response ports of u_gpu / the CPU debug port are likewise not
    // clamped: an access into a powered-down domain's registers stalling while
    // the domain is off is acceptable/expected behavior for a sequencing-only
    // PMU (docs/POWER_DOMAIN_EVALUATION.md) -- full per-port isolation-cell
    // coverage is part of the deferred true-power-gating scope.
    //
    // GH #93: ISO_CPU's clamp point MOVED from xbar_m_*[0] (the fabric side
    // of the old direct connection) to u_cpu_axi_cdc's s_* (CPU-domain) face
    // below — the clamp is CPU-domain infrastructure (it isolates PD_CPU's
    // output), so it belongs on the CPU side of the CDC bridge, not the
    // fabric side. It is qualified by pmu_cpu_iso_en_sync (cpu_core_clk-
    // synchronised, see PMU sequencing nets above), not the raw core_clk
    // pmu_cpu_iso_en. ISO_GPU is unaffected (GPU stays in the core_clk
    // domain; no bridge, no re-sync needed).
    logic cpu_axi_awvalid_raw, cpu_axi_wvalid_raw, cpu_axi_arvalid_raw;
    logic cpu_axi_bready_raw, cpu_axi_rready_raw;
    logic cpu_commit_valid_raw;

    logic gpu_axi_awvalid_raw, gpu_axi_wvalid_raw, gpu_axi_arvalid_raw;
    logic gpu_axi_bready_raw, gpu_axi_rready_raw;
    logic gpu_gif_arvalid_raw;
    logic gpu_irq_raw;

    // =========================================================================
    // AXI-Lite flat wires for GPU ctrl and DMA ctrl (ring slaves 0 and 2).
    // These were axil_s_*[AXIL_GPU] and axil_s_*[AXIL_DMA] in the old soc_top;
    // soc_bus now exposes them as flat ports (axil_gpu_* / axil_dma_*).
    // =========================================================================
    logic [AW-1:0] bus_axil_gpu_awaddr;
    logic [2:0]    bus_axil_gpu_awprot;
    logic          bus_axil_gpu_awvalid;
    logic          bus_axil_gpu_awready;
    logic [DW-1:0] bus_axil_gpu_wdata;
    logic [SW-1:0] bus_axil_gpu_wstrb;
    logic          bus_axil_gpu_wvalid;
    logic          bus_axil_gpu_wready;
    logic [1:0]    bus_axil_gpu_bresp;
    logic          bus_axil_gpu_bvalid;
    logic          bus_axil_gpu_bready;
    logic [AW-1:0] bus_axil_gpu_araddr;
    logic [2:0]    bus_axil_gpu_arprot;
    logic          bus_axil_gpu_arvalid;
    logic          bus_axil_gpu_arready;
    logic [DW-1:0] bus_axil_gpu_rdata;
    logic [1:0]    bus_axil_gpu_rresp;
    logic          bus_axil_gpu_rvalid;
    logic          bus_axil_gpu_rready;

    logic [AW-1:0] bus_axil_dma_awaddr;
    logic [2:0]    bus_axil_dma_awprot;
    logic          bus_axil_dma_awvalid;
    logic          bus_axil_dma_awready;
    logic [DW-1:0] bus_axil_dma_wdata;
    logic [SW-1:0] bus_axil_dma_wstrb;
    logic          bus_axil_dma_wvalid;
    logic          bus_axil_dma_wready;
    logic [1:0]    bus_axil_dma_bresp;
    logic          bus_axil_dma_bvalid;
    logic          bus_axil_dma_bready;
    logic [AW-1:0] bus_axil_dma_araddr;
    logic [2:0]    bus_axil_dma_arprot;
    logic          bus_axil_dma_arvalid;
    logic          bus_axil_dma_arready;
    logic [DW-1:0] bus_axil_dma_rdata;
    logic [1:0]    bus_axil_dma_rresp;
    logic          bus_axil_dma_rvalid;
    logic          bus_axil_dma_rready;

    // =========================================================================
    // axilite_to_axi4 adapter (GPU ifetch → crossbar M1)
    // =========================================================================
    // Signals on the AXI4 side (connect to crossbar M1)
    logic [IW-1:0]   gif_axi_awid;
    logic [AW-1:0]   gif_axi_awaddr;
    logic [LENW-1:0] gif_axi_awlen;
    logic [2:0]      gif_axi_awsize;
    logic [1:0]      gif_axi_awburst;
    logic            gif_axi_awvalid;
    logic            gif_axi_awready;
    logic [DW-1:0]   gif_axi_wdata;
    logic [SW-1:0]   gif_axi_wstrb;
    logic            gif_axi_wlast;
    logic            gif_axi_wvalid;
    logic            gif_axi_wready;
    logic [IW-1:0]   gif_axi_bid;
    logic [1:0]      gif_axi_bresp;
    logic            gif_axi_bvalid;
    logic            gif_axi_bready;
    logic [IW-1:0]   gif_axi_arid;
    logic [AW-1:0]   gif_axi_araddr;
    logic [LENW-1:0] gif_axi_arlen;
    logic [2:0]      gif_axi_arsize;
    logic [1:0]      gif_axi_arburst;
    logic            gif_axi_arvalid;
    logic            gif_axi_arready;
    logic [IW-1:0]   gif_axi_rid;
    logic [DW-1:0]   gif_axi_rdata;
    logic [1:0]      gif_axi_rresp;
    logic            gif_axi_rlast;
    logic            gif_axi_rvalid;
    logic            gif_axi_rready;

    // Crossbar master-facing ports are ID-less (IDs exist only on the slave
    // side). The GPU-ifetch adapter is read-only and ignores both the
    // write-response ID and the read-data ID, so tie them to 0 to give these
    // adapter-input wires a defined driver.
    assign gif_axi_bid = '0;
    assign gif_axi_rid = '0;

    // DMA drives AXI4 transaction IDs, but the crossbar master-facing ports are
    // ID-less. Sink them into dedicated unused nets (rather than open pins) so
    // the connection is explicit; these nets are intentionally unread.
    logic [IW-1:0]   dma_axi_awid_unused;
    logic [IW-1:0]   dma_axi_arid_unused;

    // GPU ifetch AXI-Lite master side (connect to gpu_top m_axil_if_*)
    logic [AW-1:0]   gif_axil_araddr;
    logic            gif_axil_arvalid;
    logic            gif_axil_arready;
    logic [DW-1:0]   gif_axil_rdata;
    logic [1:0]      gif_axil_rresp;
    logic            gif_axil_rvalid;
    logic            gif_axil_rready;

    // =========================================================================
    // IRQ signals
    // =========================================================================
    logic uart_irq;
    logic spi_irq;
    logic timer_irq;
    logic dma_irq;
    // gpu_irq_o is exposed at top-level port; driven by gpu_top

    logic ext_irq;    // interrupt_controller output → CPU ext_irq_i

    // =========================================================================
    // CPU debug observability (M7 leaves these unconnected at top — tie off)
    // =========================================================================
    /* verilator lint_off UNUSEDSIGNAL */
    logic        cpu_trap_taken;
    logic [3:0]  cpu_trap_cause;
    logic [31:0] cpu_debug_rs1;
    logic [31:0] cpu_debug_rs2;
    logic        cpu_debug_branch_taken;
    logic        cpu_debug_take_branch_jump;
    logic        cpu_debug_pc_src;
    logic [3:0]  cpu_debug_state;
    logic        cpu_debug_ebreak;
    /* verilator lint_on  UNUSEDSIGNAL */

    // =========================================================================
    // GH #95 fix (bead claude_verilog_test-eg2): APB3 debug-port CDC bridge.
    //
    // The top-level apb_* debug ports fed u_cpu DIRECTLY until this fix. GH
    // #93 moved u_cpu onto cpu_gated_clk, so this chip-boundary bus silently
    // migrated from the fabric (core_clk) domain into the CPU domain with no
    // synchroniser — a cdc_snitch BAD=233 finding (all one root cause:
    // apb_paddr_i/apb_pwdata_i/psel/penable/pwrite captured unsynchronised by
    // u_cpu.dbg_pc_wr_data/dbg_ctrl_reg/dbg_reg_wr_en/halt_latch_q).
    //
    // Fix: a second apb_cdc_bridge instance, u_apb_dbg_cdc, restores the
    // pre-#93 external contract ("drive apb_* synchronously to clk_i") by
    // bridging INTO the CPU domain instead of redefining that contract.
    // Modelled on ARM CoreSight SoC-400's DAPBUS async bridge (DDI 0480F
    // §4.2.6/§4.2.8): the debug port clock is asynchronous to the block it
    // drives by construction (an external probe cannot guarantee edge
    // alignment with cpu_clk_i), and the async bridge is what lets debug stay
    // power-isolated from the domain it accesses.
    //   s-face: core_clk / core_rst_n — matches every other fabric-domain
    //     block (same domain as apb_interconnect / axil_to_apb).
    //   m-face: cpu_gated_clk / cpu_domain_rst_n — matches u_cpu itself, so a
    //     PMU-gated CPU correctly stalls debug accesses (already the
    //     documented intent below: "stalling ... into a gated CPU domain is
    //     expected/OK"). NOT cpu_clk_i/cpu_rst_n_i raw (unlike u_apb_pll2_cdc,
    //     whose bootstrap reasoning at its instantiation does not apply here).
    //
    // APB3/APB4 pstrb mismatch: apb_cdc_bridge is APB4 (has pstrb); the CPU's
    // debug slave (rv32i_cpu_top) is APB3 (no pstrb port) and — confirmed by
    // inspection of rv32i_cpu_top.sv's debug-write block — every debug
    // register write captures the full 32-bit apb_pwdata_i unconditionally
    // (`dbg_ctrl_reg <= apb_pwdata_i;` etc.), with no per-byte/strobe-
    // qualified partial write anywhere in that logic. s_pstrb_i is therefore
    // tied to all-ones (full-word strobe, matching the top-level apb_* ports'
    // own lack of a pstrb signal) and m_pstrb_o is sunk to a dedicated unused
    // net (the CPU has no pstrb input to connect it to).
    // =========================================================================
    logic        dbg_bridge_m_psel, dbg_bridge_m_penable, dbg_bridge_m_pwrite;
    logic [11:0] dbg_bridge_m_paddr;
    logic [31:0] dbg_bridge_m_pwdata, dbg_bridge_m_prdata;
    logic        dbg_bridge_m_pready, dbg_bridge_m_pslverr;
    logic [3:0]  dbg_bridge_m_pstrb_unused;

    apb_cdc_bridge #(
        .ADDR_W (12)
    ) u_apb_dbg_cdc (
        .s_clk_i     (core_clk),
        .s_rst_n_i   (core_rst_n),
        .s_psel_i    (apb_psel_i),
        .s_penable_i (apb_penable_i),
        .s_pwrite_i  (apb_pwrite_i),
        .s_paddr_i   (apb_paddr_i),
        .s_pwdata_i  (apb_pwdata_i),
        .s_pstrb_i   (4'hF),
        .s_prdata_o  (apb_prdata_o),
        .s_pready_o  (apb_pready_o),
        .s_pslverr_o (apb_pslverr_o),

        .m_clk_i     (cpu_gated_clk),
        .m_rst_n_i   (cpu_domain_rst_n),
        .m_psel_o    (dbg_bridge_m_psel),
        .m_penable_o (dbg_bridge_m_penable),
        .m_pwrite_o  (dbg_bridge_m_pwrite),
        .m_paddr_o   (dbg_bridge_m_paddr),
        .m_pwdata_o  (dbg_bridge_m_pwdata),
        .m_pstrb_o   (dbg_bridge_m_pstrb_unused),
        .m_prdata_i  (dbg_bridge_m_prdata),
        .m_pready_i  (dbg_bridge_m_pready),
        .m_pslverr_i (dbg_bridge_m_pslverr)
    );

    // =========================================================================
    // GH #93: CPU-domain face of the CPU<->crossbar-M0 AXI4 CDC bridge.
    // u_cpu's AXI4 master now terminates here (not at xbar_m_*[0] directly);
    // u_cpu_axi_cdc's m_* face (fabric domain) drives xbar_m_*[0] below.
    // =========================================================================
    logic [AW-1:0]   cpu_bridge_s_awaddr;
    logic [LENW-1:0] cpu_bridge_s_awlen;
    logic [2:0]      cpu_bridge_s_awsize;
    logic [1:0]      cpu_bridge_s_awburst;
    logic            cpu_bridge_s_awvalid, cpu_bridge_s_awready;
    logic [DW-1:0]   cpu_bridge_s_wdata;
    logic [SW-1:0]   cpu_bridge_s_wstrb;
    logic            cpu_bridge_s_wlast;
    logic            cpu_bridge_s_wvalid, cpu_bridge_s_wready;
    logic [1:0]      cpu_bridge_s_bresp;
    logic            cpu_bridge_s_bvalid, cpu_bridge_s_bready;
    logic [AW-1:0]   cpu_bridge_s_araddr;
    logic [LENW-1:0] cpu_bridge_s_arlen;
    logic [2:0]      cpu_bridge_s_arsize;
    logic [1:0]      cpu_bridge_s_arburst;
    logic            cpu_bridge_s_arvalid, cpu_bridge_s_arready;
    logic [DW-1:0]   cpu_bridge_s_rdata;
    logic [1:0]      cpu_bridge_s_rresp;
    logic            cpu_bridge_s_rlast;
    logic            cpu_bridge_s_rvalid, cpu_bridge_s_rready;

    // =========================================================================
    // M0: CPU (rv32i_cpu_top) → u_cpu_axi_cdc (CDC bridge) → crossbar M0
    // =========================================================================
    rv32i_cpu_top #(
        .RESET_PC (32'h0000_1000)
    ) u_cpu (
        .clk_i                      (cpu_gated_clk),
        .rst_n_i                    (cpu_domain_rst_n),
        // AXI4 master → u_cpu_axi_cdc s_* face (raw; clamped by ISO_CPU below)
        .axi_awaddr_o               (cpu_bridge_s_awaddr),
        .axi_awlen_o                (cpu_bridge_s_awlen),
        .axi_awsize_o               (cpu_bridge_s_awsize),
        .axi_awburst_o              (cpu_bridge_s_awburst),
        .axi_awvalid_o              (cpu_axi_awvalid_raw),
        .axi_awready_i              (cpu_bridge_s_awready),
        .axi_wdata_o                (cpu_bridge_s_wdata),
        .axi_wstrb_o                (cpu_bridge_s_wstrb),
        .axi_wlast_o                (cpu_bridge_s_wlast),
        .axi_wvalid_o               (cpu_axi_wvalid_raw),
        .axi_wready_i               (cpu_bridge_s_wready),
        .axi_bresp_i                (cpu_bridge_s_bresp),
        .axi_bvalid_i               (cpu_bridge_s_bvalid),
        .axi_bready_o               (cpu_axi_bready_raw),
        .axi_araddr_o               (cpu_bridge_s_araddr),
        .axi_arlen_o                (cpu_bridge_s_arlen),
        .axi_arsize_o               (cpu_bridge_s_arsize),
        .axi_arburst_o              (cpu_bridge_s_arburst),
        .axi_arvalid_o              (cpu_axi_arvalid_raw),
        .axi_arready_i              (cpu_bridge_s_arready),
        .axi_rdata_i                (cpu_bridge_s_rdata),
        .axi_rresp_i                (cpu_bridge_s_rresp),
        .axi_rvalid_i               (cpu_bridge_s_rvalid),
        .axi_rlast_i                (cpu_bridge_s_rlast),
        .axi_rready_o               (cpu_axi_rready_raw),
        // APB3 debug slave — GH #95 fix: now fed from u_apb_dbg_cdc's m_*
        // (CPU-domain) face instead of the top-level apb_* ports directly
        // (see u_apb_dbg_cdc above). Not isolation-clamped — stalling a
        // debug access into a gated CPU domain is expected/OK.
        .apb_paddr_i                (dbg_bridge_m_paddr),
        .apb_psel_i                 (dbg_bridge_m_psel),
        .apb_penable_i              (dbg_bridge_m_penable),
        .apb_pwrite_i               (dbg_bridge_m_pwrite),
        .apb_pwdata_i               (dbg_bridge_m_pwdata),
        .apb_prdata_o               (dbg_bridge_m_prdata),
        .apb_pready_o               (dbg_bridge_m_pready),
        .apb_pslverr_o              (dbg_bridge_m_pslverr),
        // Commit observability (partially exposed at top)
        .commit_valid_o             (cpu_commit_valid_raw),
        .commit_pc_o                (commit_pc_o),
        .commit_insn_o              (commit_insn_o),
        .trap_taken_o               (cpu_trap_taken),
        .trap_cause_o               (cpu_trap_cause),
        // Debug outputs (M7 deferred — tie off internally)
        .debug_rs1_data_o           (cpu_debug_rs1),
        .debug_rs2_data_o           (cpu_debug_rs2),
        .debug_branch_taken_o       (cpu_debug_branch_taken),
        .debug_take_branch_jump_o   (cpu_debug_take_branch_jump),
        .debug_pc_src_o             (cpu_debug_pc_src),
        .debug_state_o              (cpu_debug_state),
        .debug_ebreak_o             (cpu_debug_ebreak),
        // Interrupt inputs — GH #93: synchronised into the CPU domain (see
        // PMU sequencing nets above; both sources are level-held, not pulses)
        .ext_irq_i                  (ext_irq_cpu_sync),
        .timer_irq_i                (timer_irq_cpu_sync)
    );

    // ISO_CPU functional-isolation clamp (`-location parent`, clamp_value 0):
    // forces the CPU->fabric handshake + commit observability to 0 while
    // pmu_cpu_iso_en_sync is asserted. See clamp-scope note above u_cpu.
    // GH #93: now applied at u_cpu_axi_cdc's s_* (CPU-domain) inputs instead
    // of xbar_m_*[0] directly.
    assign cpu_bridge_s_awvalid = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_awvalid_raw;
    assign cpu_bridge_s_wvalid  = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_wvalid_raw;
    assign cpu_bridge_s_arvalid = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_arvalid_raw;
    assign cpu_bridge_s_bready  = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_bready_raw;
    assign cpu_bridge_s_rready  = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_rready_raw;
    assign commit_valid_o       = pmu_cpu_iso_en_sync ? 1'b0 : cpu_commit_valid_raw;

    // =========================================================================
    // GH #93: dual-clock AXI4 CDC bridge — CPU domain (cpu_gated_clk) <->
    // fabric domain (core_clk), the SoC's one intentional CDC boundary
    // (docs/3PLL_CDC_EVALUATION.md). m_rst_n_i matches crossbar M0's domain
    // (core_rst_n), unchanged. async_axi_fifo internally ANDs s_rst_n_i and
    // m_rst_n_i together for its two cdc_reset_sync instances (see
    // async_axi_fifo.sv header) — this bridge's hard-flush reset is discussed
    // in the clock-seam header note above (known hazard, not fixed here).
    //
    // GH #95 / bead claude_verilog_test-2k8 fix: s_rst_n_i is
    // cpu_core_rst_n, DELIBERATELY NOT cpu_domain_rst_n. Do not "fix" this
    // back — see the full retain-vs-flush rationale below.
    //
    // RETAIN vs FLUSH — the actual bug this rewiring closes: a PMU-driven
    // live CPU-domain power-cycle must RETAIN u_cpu's architectural state
    // (that is the entire point of clock-gate-only power-down — see
    // pmu_cpu_rst_n_cpu_sync's ordering note above u_cpu_cg: u_cpu is
    // synchronous-reset and cpu_gated_clk is forbidden from ticking while
    // that reset is asserted, so u_cpu structurally never reboots). But
    // cpu_domain_rst_n = cpu_core_rst_n & pmu_cpu_rst_n_cpu_sync ALSO drops
    // to 0 for the PMU's own retention-hold reset (pmu_cpu_rst_n_cpu_sync),
    // not just for a genuine POR/PLL-unlock event. Wiring s_rst_n_i to
    // cpu_domain_rst_n therefore hard-FLUSHED this bridge's gray-code
    // pointers and any FIFO'd beats on every PMU power-down — a HARD FLUSH
    // is a fabricated, asynchronous, mid-transaction abort (see the "Reset
    // here is a HARD FLUSH" note in async_axi_fifo.sv's header), the exact
    // opposite of the retention the CPU side of the same power-cycle
    // guarantees. On resume, u_cpu's cache/AXI-arbiter FSM (rv32i_cache_arbiter.sv)
    // was still correctly waiting for the response to its outstanding
    // request (its own state WAS retained, per the CPU-side contract), but
    // the bridge that was supposed to deliver that response had already
    // discarded it — permanent deadlock (bead 2k8: instrumented evidence
    // showed dc_stall stuck at 1 forever post-resume with arvalid=0,
    // rvalid=0, i.e. the D-cache's AR handshake had already completed and it
    // was blocked waiting in the R phase for a beat the flush erased).
    //
    // Fix: s_rst_n_i = cpu_core_rst_n, the CPU's TRUE reset (POR + PLL lock
    // only — see cpu_core_rst_n's declaration comment above), so the
    // bridge's CPU-side face retains exactly like the CPU it serves and
    // asserts ONLY for the same events that would legitimately reboot u_cpu
    // (never for a PMU power-cycle, which leaves cpu_core_rst_n at 1
    // throughout). u_cpu itself, u_apb_dbg_cdc's m_rst_n_i, and the ISO_CPU
    // clamp all correctly stay on cpu_domain_rst_n / pmu_cpu_iso_en_sync —
    // this fix touches ONLY u_cpu_axi_cdc's s_rst_n_i.
    //
    // Safety re-verified (bead 2k8 task; do not re-derive, but do re-check
    // if this bridge's parameters or the arbiter's grant policy ever change):
    //   1. R-FIFO depth sufficiency: rv32i_cache_arbiter.sv's grant_q FSM
    //      (GRANT_NONE/GRANT_IC_RD/GRANT_DC_RD/GRANT_DC_WR) holds a single
    //      grant until RLAST (read) or BVALID+BREADY (write) before it can
    //      grant again, so at most ONE outstanding read burst exists at a
    //      time = 4 beats for a 16 B cache line. async_axi_fifo's R_DEPTH
    //      defaults to 8 and this instantiation below does not override any
    //      *_DEPTH parameter — 2x margin, confirmed.
    //   2. Cross-coupled reset root stays legitimate: rst_both_n =
    //      s_rst_n_i & m_rst_n_i becomes cpu_core_rst_n & core_rst_n — both
    //      still POR/PLL-lock-derived (see their respective declaration
    //      comments above), still a common root, satisfying the same
    //      contract OpenTitan's prim_sync_reqack and AMD PG059 require.
    //   3. No retention mode is lost: PMU power-down never reset u_cpu even
    //      before this fix (gated clock + synchronous reset already made it
    //      retention-by-construction on the CPU side), so nothing depended
    //      on the bridge flushing during a power-cycle.
    //   Also re-verified: async_axi_fifo.sv's ">= SYNC_STAGES+1 periods of
    //   the OTHER clock" reset contract still holds for s_rst_n_i under the
    //   new wiring — cpu_core_rst_n's low window is a SUBSET of
    //   cpu_domain_rst_n's old low window (cpu_domain_rst_n additionally
    //   drops for PMU-only events cpu_core_rst_n does not), and s_clk_i
    //   (cpu_gated_clk) is proven (see u_cpu_clk_dis_sync's ordering note
    //   above) to tick throughout cpu_core_rst_n's own low window — the same
    //   property the pre-fix analysis below this note used to rely on.
    //
    // NOT fixed by this change (still open, still accepted, Phase 6 scope):
    // the no-drain/quiesce gap at soc_top.sv:83-93 — a mid-burst CPU AXI
    // transaction in flight when the PMU clock-gates is unaddressed by this
    // rewiring; it can still leave a crossbar SLAVE engine wedged on a
    // response that will never come, independent of whether this CDC
    // bridge's own pointers are retained. The upstream fix is PULP-style
    // axi_isolate (count outstanding transactions, assert isolated_o only at
    // zero, then reset) — not implemented here.
    //
    // async_axi_fifo.sv's contract requires each of s_rst_n_i/m_rst_n_i to be
    // held low for >= SYNC_STAGES+1 periods of the OTHER face's clock (see
    // async_axi_fifo.sv header). Before the GH #93-fix above, this was
    // VIOLATED for s_rst_n_i (= cpu_domain_rst_n as it was wired THEN): s_clk_i
    // is cpu_gated_clk, which the pre-fix clk_en sync stopped completely for
    // the entire time cpu_domain_rst_n was low — i.e. s_clk_i saw ZERO
    // periods (not SYNC_STAGES+1) during s_rst_n_i's assertion. With the
    // GH #93 u_cpu_clk_dis_sync fix, cpu_gated_clk = cpu_core_clk runs
    // unconditionally throughout the entire cpu_core_rst_n-low window (see
    // the ordering note above u_cpu_clk_dis_sync), so s_clk_i ticks
    // throughout s_rst_n_i's assertion under the CURRENT (cpu_core_rst_n)
    // wiring too — the contract is met for the cold-boot/PLL-relock case.
    // =========================================================================
    async_axi_fifo u_cpu_axi_cdc (
        .s_clk_i     (cpu_gated_clk),
        .s_rst_n_i   (cpu_core_rst_n),
        .s_awaddr_i  (cpu_bridge_s_awaddr),
        .s_awlen_i   (cpu_bridge_s_awlen),
        .s_awsize_i  (cpu_bridge_s_awsize),
        .s_awburst_i (cpu_bridge_s_awburst),
        .s_awvalid_i (cpu_bridge_s_awvalid),
        .s_awready_o (cpu_bridge_s_awready),
        .s_wdata_i   (cpu_bridge_s_wdata),
        .s_wstrb_i   (cpu_bridge_s_wstrb),
        .s_wlast_i   (cpu_bridge_s_wlast),
        .s_wvalid_i  (cpu_bridge_s_wvalid),
        .s_wready_o  (cpu_bridge_s_wready),
        .s_bresp_o   (cpu_bridge_s_bresp),
        .s_bvalid_o  (cpu_bridge_s_bvalid),
        .s_bready_i  (cpu_bridge_s_bready),
        .s_araddr_i  (cpu_bridge_s_araddr),
        .s_arlen_i   (cpu_bridge_s_arlen),
        .s_arsize_i  (cpu_bridge_s_arsize),
        .s_arburst_i (cpu_bridge_s_arburst),
        .s_arvalid_i (cpu_bridge_s_arvalid),
        .s_arready_o (cpu_bridge_s_arready),
        .s_rdata_o   (cpu_bridge_s_rdata),
        .s_rresp_o   (cpu_bridge_s_rresp),
        .s_rlast_o   (cpu_bridge_s_rlast),
        .s_rvalid_o  (cpu_bridge_s_rvalid),
        .s_rready_i  (cpu_bridge_s_rready),

        .m_clk_i     (core_clk),
        .m_rst_n_i   (core_rst_n),
        .m_awaddr_o  (xbar_m_awaddr  [0]),
        .m_awlen_o   (xbar_m_awlen   [0]),
        .m_awsize_o  (xbar_m_awsize  [0]),
        .m_awburst_o (xbar_m_awburst [0]),
        .m_awvalid_o (xbar_m_awvalid [0]),
        .m_awready_i (xbar_m_awready [0]),
        .m_wdata_o   (xbar_m_wdata   [0]),
        .m_wstrb_o   (xbar_m_wstrb   [0]),
        .m_wlast_o   (xbar_m_wlast   [0]),
        .m_wvalid_o  (xbar_m_wvalid  [0]),
        .m_wready_i  (xbar_m_wready  [0]),
        .m_bresp_i   (xbar_m_bresp   [0]),
        .m_bvalid_i  (xbar_m_bvalid  [0]),
        .m_bready_o  (xbar_m_bready  [0]),
        .m_araddr_o  (xbar_m_araddr  [0]),
        .m_arlen_o   (xbar_m_arlen   [0]),
        .m_arsize_o  (xbar_m_arsize  [0]),
        .m_arburst_o (xbar_m_arburst [0]),
        .m_arvalid_o (xbar_m_arvalid [0]),
        .m_arready_i (xbar_m_arready [0]),
        .m_rdata_i   (xbar_m_rdata   [0]),
        .m_rresp_i   (xbar_m_rresp   [0]),
        .m_rlast_i   (xbar_m_rlast   [0]),
        .m_rvalid_i  (xbar_m_rvalid  [0]),
        .m_rready_o  (xbar_m_rready  [0])
    );

    // =========================================================================
    // M1: GPU ifetch adapter (axilite_to_axi4) → crossbar M1
    // =========================================================================
    axilite_to_axi4 u_gif_adapter (
        .clk                        (core_clk),
        .rst_n                      (core_rst_n),
        // AXI4-Lite slave ← gpu_top m_axil_if_*
        .s_axil_araddr              (gif_axil_araddr),
        .s_axil_arvalid             (gif_axil_arvalid),
        .s_axil_arready             (gif_axil_arready),
        .s_axil_rdata               (gif_axil_rdata),
        .s_axil_rresp               (gif_axil_rresp),
        .s_axil_rvalid              (gif_axil_rvalid),
        .s_axil_rready              (gif_axil_rready),
        // AXI4 master → crossbar M1
        .m_axi_awid                 (gif_axi_awid),
        .m_axi_awaddr               (gif_axi_awaddr),
        .m_axi_awlen                (gif_axi_awlen),
        .m_axi_awsize               (gif_axi_awsize),
        .m_axi_awburst              (gif_axi_awburst),
        .m_axi_awvalid              (gif_axi_awvalid),
        .m_axi_awready              (gif_axi_awready),
        .m_axi_wdata                (gif_axi_wdata),
        .m_axi_wstrb                (gif_axi_wstrb),
        .m_axi_wlast                (gif_axi_wlast),
        .m_axi_wvalid               (gif_axi_wvalid),
        .m_axi_wready               (gif_axi_wready),
        .m_axi_bid                  (gif_axi_bid),
        .m_axi_bresp                (gif_axi_bresp),
        .m_axi_bvalid               (gif_axi_bvalid),
        .m_axi_bready               (gif_axi_bready),
        .m_axi_arid                 (gif_axi_arid),
        .m_axi_araddr               (gif_axi_araddr),
        .m_axi_arlen                (gif_axi_arlen),
        .m_axi_arsize               (gif_axi_arsize),
        .m_axi_arburst              (gif_axi_arburst),
        .m_axi_arvalid              (gif_axi_arvalid),
        .m_axi_arready              (gif_axi_arready),
        .m_axi_rid                  (gif_axi_rid),
        .m_axi_rdata                (gif_axi_rdata),
        .m_axi_rresp                (gif_axi_rresp),
        .m_axi_rlast                (gif_axi_rlast),
        .m_axi_rvalid               (gif_axi_rvalid),
        .m_axi_rready               (gif_axi_rready)
    );

    // Wire gif adapter AXI4 side → crossbar M1 (no-ID master port)
    assign xbar_m_awaddr  [1] = gif_axi_awaddr;
    assign xbar_m_awlen   [1] = gif_axi_awlen;
    assign xbar_m_awsize  [1] = gif_axi_awsize;
    assign xbar_m_awburst [1] = gif_axi_awburst;
    assign xbar_m_awvalid [1] = gif_axi_awvalid;
    assign gif_axi_awready    = xbar_m_awready [1];
    assign xbar_m_wdata   [1] = gif_axi_wdata;
    assign xbar_m_wstrb   [1] = gif_axi_wstrb;
    assign xbar_m_wlast   [1] = gif_axi_wlast;
    assign xbar_m_wvalid  [1] = gif_axi_wvalid;
    assign gif_axi_wready     = xbar_m_wready  [1];
    assign gif_axi_bresp      = xbar_m_bresp   [1];
    assign gif_axi_bvalid     = xbar_m_bvalid  [1];
    assign xbar_m_bready  [1] = gif_axi_bready;
    assign xbar_m_araddr  [1] = gif_axi_araddr;
    assign xbar_m_arlen   [1] = gif_axi_arlen;
    assign xbar_m_arsize  [1] = gif_axi_arsize;
    assign xbar_m_arburst [1] = gif_axi_arburst;
    assign xbar_m_arvalid [1] = gif_axi_arvalid;
    assign gif_axi_arready    = xbar_m_arready [1];
    assign gif_axi_rdata      = xbar_m_rdata   [1];
    assign gif_axi_rresp      = xbar_m_rresp   [1];
    assign gif_axi_rlast      = xbar_m_rlast   [1];
    assign gif_axi_rvalid     = xbar_m_rvalid  [1];
    assign xbar_m_rready  [1] = gif_axi_rready;

    // =========================================================================
    // GPU top (gpu_top) — M2 (data AXI4), AXIL_GPU (ctrl slave)
    // =========================================================================
    gpu_top #(
        .GPU_ENABLE_COALESCE (1'b0)
    ) u_gpu (
        .clk                        (gpu_gated_clk),
        .rst_n                      (gpu_domain_rst_n),
        // AXI4-Lite ctrl slave ← soc_bus axil_gpu_* (ring slot AXIL_GPU=0);
        // slave-side response port not isolation-clamped (see clamp-scope
        // note above) — stalling a ctrl access into a gated GPU is expected.
        .s_axil_awaddr              (bus_axil_gpu_awaddr[11:0]),
        .s_axil_awvalid             (bus_axil_gpu_awvalid),
        .s_axil_awready             (bus_axil_gpu_awready),
        .s_axil_wdata               (bus_axil_gpu_wdata),
        .s_axil_wstrb               (bus_axil_gpu_wstrb),
        .s_axil_wvalid              (bus_axil_gpu_wvalid),
        .s_axil_wready              (bus_axil_gpu_wready),
        .s_axil_bresp               (bus_axil_gpu_bresp),
        .s_axil_bvalid              (bus_axil_gpu_bvalid),
        .s_axil_bready              (bus_axil_gpu_bready),
        .s_axil_araddr              (bus_axil_gpu_araddr[11:0]),
        .s_axil_arvalid             (bus_axil_gpu_arvalid),
        .s_axil_arready             (bus_axil_gpu_arready),
        .s_axil_rdata               (bus_axil_gpu_rdata),
        .s_axil_rresp               (bus_axil_gpu_rresp),
        .s_axil_rvalid              (bus_axil_gpu_rvalid),
        .s_axil_rready              (bus_axil_gpu_rready),
        // AXI4-Lite ifetch master → gif adapter slave (raw; clamped below)
        .m_axil_if_araddr           (gif_axil_araddr),
        .m_axil_if_arvalid          (gpu_gif_arvalid_raw),
        .m_axil_if_arready          (gif_axil_arready),
        .m_axil_if_rdata            (gif_axil_rdata),
        .m_axil_if_rresp            (gif_axil_rresp),
        .m_axil_if_rvalid           (gif_axil_rvalid),
        .m_axil_if_rready           (gif_axil_rready),
        // AXI4 data master → crossbar M2 (raw; clamped below)
        .m_axi_araddr               (xbar_m_araddr  [2]),
        .m_axi_arvalid              (gpu_axi_arvalid_raw),
        .m_axi_arready              (xbar_m_arready [2]),
        .m_axi_rdata                (xbar_m_rdata   [2]),
        .m_axi_rresp                (xbar_m_rresp   [2]),
        .m_axi_rvalid               (xbar_m_rvalid  [2]),
        .m_axi_rready               (gpu_axi_rready_raw),
        .m_axi_awaddr               (xbar_m_awaddr  [2]),
        .m_axi_awvalid              (gpu_axi_awvalid_raw),
        .m_axi_awready              (xbar_m_awready [2]),
        .m_axi_wdata                (xbar_m_wdata   [2]),
        .m_axi_wstrb                (xbar_m_wstrb   [2]),
        .m_axi_wvalid               (gpu_axi_wvalid_raw),
        .m_axi_wready               (xbar_m_wready  [2]),
        .m_axi_bresp                (xbar_m_bresp   [2]),
        .m_axi_bvalid               (xbar_m_bvalid  [2]),
        .m_axi_bready               (gpu_axi_bready_raw),
        // IRQ
        .gpu_irq_o                  (gpu_irq_raw)
    );

    // GPU AXI4 data master has no len/size/burst/last at gpu_top port level;
    // tie the crossbar's M2 burst fields to single-beat defaults.
    assign xbar_m_awlen   [2] = '0;
    assign xbar_m_awsize  [2] = AXI_SIZE_4B;
    assign xbar_m_awburst [2] = AXI_BURST_INCR;
    assign xbar_m_wlast   [2] = 1'b1;   // always last (single beat)
    assign xbar_m_arlen   [2] = '0;
    assign xbar_m_arsize  [2] = AXI_SIZE_4B;
    assign xbar_m_arburst [2] = AXI_BURST_INCR;

    // ISO_GPU functional-isolation clamp (`-location parent`, clamp_value 0):
    // forces the GPU->fabric handshake + IRQ to 0 while pmu_gpu_iso_en is
    // asserted. See clamp-scope note above u_gpu.
    assign xbar_m_awvalid [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_awvalid_raw;
    assign xbar_m_wvalid  [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_wvalid_raw;
    assign xbar_m_arvalid [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_arvalid_raw;
    assign xbar_m_bready  [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_bready_raw;
    assign xbar_m_rready  [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_rready_raw;
    assign gif_axil_arvalid   = pmu_gpu_iso_en ? 1'b0 : gpu_gif_arvalid_raw;
    assign gpu_irq_o          = pmu_gpu_iso_en ? 1'b0 : gpu_irq_raw;

    // =========================================================================
    // M3: DMA engine (dma_engine) → crossbar M3 + interconnect AXIL_DMA
    // =========================================================================
    dma_engine #(
        .ADDR_W (12)
    ) u_dma (
        .clk                        (core_clk),
        .rst_n                      (core_rst_n),
        // AXI4-Lite ctrl slave ← soc_bus axil_dma_* (ring slot AXIL_DMA=2)
        .s_axil_awaddr              (bus_axil_dma_awaddr[11:0]),
        .s_axil_awprot              (bus_axil_dma_awprot),
        .s_axil_awvalid             (bus_axil_dma_awvalid),
        .s_axil_awready             (bus_axil_dma_awready),
        .s_axil_wdata               (bus_axil_dma_wdata),
        .s_axil_wstrb               (bus_axil_dma_wstrb),
        .s_axil_wvalid              (bus_axil_dma_wvalid),
        .s_axil_wready              (bus_axil_dma_wready),
        .s_axil_bresp               (bus_axil_dma_bresp),
        .s_axil_bvalid              (bus_axil_dma_bvalid),
        .s_axil_bready              (bus_axil_dma_bready),
        .s_axil_araddr              (bus_axil_dma_araddr[11:0]),
        .s_axil_arprot              (bus_axil_dma_arprot),
        .s_axil_arvalid             (bus_axil_dma_arvalid),
        .s_axil_arready             (bus_axil_dma_arready),
        .s_axil_rdata               (bus_axil_dma_rdata),
        .s_axil_rresp               (bus_axil_dma_rresp),
        .s_axil_rvalid              (bus_axil_dma_rvalid),
        .s_axil_rready              (bus_axil_dma_rready),
        // AXI4 burst master → crossbar M3
        .m_awid                     (dma_axi_awid_unused),         // ID unused by crossbar (no-ID master port)
        .m_awaddr                   (xbar_m_awaddr  [3]),
        .m_awlen                    (xbar_m_awlen   [3]),
        .m_awsize                   (xbar_m_awsize  [3]),
        .m_awburst                  (xbar_m_awburst [3]),
        .m_awvalid                  (xbar_m_awvalid [3]),
        .m_awready                  (xbar_m_awready [3]),
        .m_wdata                    (xbar_m_wdata   [3]),
        .m_wstrb                    (xbar_m_wstrb   [3]),
        .m_wlast                    (xbar_m_wlast   [3]),
        .m_wvalid                   (xbar_m_wvalid  [3]),
        .m_wready                   (xbar_m_wready  [3]),
        .m_bid                      ('0),   // crossbar M-facing port has no bid
        .m_bresp                    (xbar_m_bresp   [3]),
        .m_bvalid                   (xbar_m_bvalid  [3]),
        .m_bready                   (xbar_m_bready  [3]),
        .m_arid                     (dma_axi_arid_unused),         // ID unused by crossbar (no-ID master port)
        .m_araddr                   (xbar_m_araddr  [3]),
        .m_arlen                    (xbar_m_arlen   [3]),
        .m_arsize                   (xbar_m_arsize  [3]),
        .m_arburst                  (xbar_m_arburst [3]),
        .m_arvalid                  (xbar_m_arvalid [3]),
        .m_arready                  (xbar_m_arready [3]),
        .m_rid                      ('0),   // crossbar M-facing port has no rid
        .m_rdata                    (xbar_m_rdata   [3]),
        .m_rresp                    (xbar_m_rresp   [3]),
        .m_rlast                    (xbar_m_rlast   [3]),
        .m_rvalid                   (xbar_m_rvalid  [3]),
        .m_rready                   (xbar_m_rready  [3]),
        // IRQ
        .irq_o                      (dma_irq)
    );

    // =========================================================================
    // SoC bus fabric — wraps axi4_crossbar + axi4_to_axilite +
    //   axi_lite_interconnect + axil_to_apb + apb_interconnect
    // =========================================================================
    soc_bus #(
        .N_MASTERS  (N_MASTERS)
    ) u_bus (
        .clk            (core_clk),
        .rst_n          (core_rst_n),
        // AXI4 master-facing (CPU, GPU-ifetch, GPU-data, DMA)
        .m_awaddr       (xbar_m_awaddr),
        .m_awlen        (xbar_m_awlen),
        .m_awsize       (xbar_m_awsize),
        .m_awburst      (xbar_m_awburst),
        .m_awvalid      (xbar_m_awvalid),
        .m_awready      (xbar_m_awready),
        .m_wdata        (xbar_m_wdata),
        .m_wstrb        (xbar_m_wstrb),
        .m_wlast        (xbar_m_wlast),
        .m_wvalid       (xbar_m_wvalid),
        .m_wready       (xbar_m_wready),
        .m_bresp        (xbar_m_bresp),
        .m_bvalid       (xbar_m_bvalid),
        .m_bready       (xbar_m_bready),
        .m_araddr       (xbar_m_araddr),
        .m_arlen        (xbar_m_arlen),
        .m_arsize       (xbar_m_arsize),
        .m_arburst      (xbar_m_arburst),
        .m_arvalid      (xbar_m_arvalid),
        .m_arready      (xbar_m_arready),
        .m_rdata        (xbar_m_rdata),
        .m_rresp        (xbar_m_rresp),
        .m_rlast        (xbar_m_rlast),
        .m_rvalid       (xbar_m_rvalid),
        .m_rready       (xbar_m_rready),
        // AXI4 slave-facing — ROM (S0) and SRAM (S1) via flat ports
        .rom_awid       (bus_rom_awid),
        .rom_awaddr     (bus_rom_awaddr),
        .rom_awlen      (bus_rom_awlen),
        .rom_awsize     (bus_rom_awsize),
        .rom_awburst    (bus_rom_awburst),
        .rom_awvalid    (bus_rom_awvalid),
        .rom_awready    (bus_rom_awready),
        .rom_wdata      (bus_rom_wdata),
        .rom_wstrb      (bus_rom_wstrb),
        .rom_wlast      (bus_rom_wlast),
        .rom_wvalid     (bus_rom_wvalid),
        .rom_wready     (bus_rom_wready),
        .rom_bid        (bus_rom_bid),
        .rom_bresp      (bus_rom_bresp),
        .rom_bvalid     (bus_rom_bvalid),
        .rom_bready     (bus_rom_bready),
        .rom_arid       (bus_rom_arid),
        .rom_araddr     (bus_rom_araddr),
        .rom_arlen      (bus_rom_arlen),
        .rom_arsize     (bus_rom_arsize),
        .rom_arburst    (bus_rom_arburst),
        .rom_arvalid    (bus_rom_arvalid),
        .rom_arready    (bus_rom_arready),
        .rom_rid        (bus_rom_rid),
        .rom_rdata      (bus_rom_rdata),
        .rom_rresp      (bus_rom_rresp),
        .rom_rlast      (bus_rom_rlast),
        .rom_rvalid     (bus_rom_rvalid),
        .rom_rready     (bus_rom_rready),
        .mem_awid       (bus_mem_awid),
        .mem_awaddr     (bus_mem_awaddr),
        .mem_awlen      (bus_mem_awlen),
        .mem_awsize     (bus_mem_awsize),
        .mem_awburst    (bus_mem_awburst),
        .mem_awvalid    (bus_mem_awvalid),
        .mem_awready    (bus_mem_awready),
        .mem_wdata      (bus_mem_wdata),
        .mem_wstrb      (bus_mem_wstrb),
        .mem_wlast      (bus_mem_wlast),
        .mem_wvalid     (bus_mem_wvalid),
        .mem_wready     (bus_mem_wready),
        .mem_bid        (bus_mem_bid),
        .mem_bresp      (bus_mem_bresp),
        .mem_bvalid     (bus_mem_bvalid),
        .mem_bready     (bus_mem_bready),
        .mem_arid       (bus_mem_arid),
        .mem_araddr     (bus_mem_araddr),
        .mem_arlen      (bus_mem_arlen),
        .mem_arsize     (bus_mem_arsize),
        .mem_arburst    (bus_mem_arburst),
        .mem_arvalid    (bus_mem_arvalid),
        .mem_arready    (bus_mem_arready),
        .mem_rid        (bus_mem_rid),
        .mem_rdata      (bus_mem_rdata),
        .mem_rresp      (bus_mem_rresp),
        .mem_rlast      (bus_mem_rlast),
        .mem_rvalid     (bus_mem_rvalid),
        .mem_rready     (bus_mem_rready),
        // AXI-Lite GPU ctrl (ring slot AXIL_GPU=0)
        .axil_gpu_awaddr    (bus_axil_gpu_awaddr),
        .axil_gpu_awprot    (bus_axil_gpu_awprot),
        .axil_gpu_awvalid   (bus_axil_gpu_awvalid),
        .axil_gpu_awready   (bus_axil_gpu_awready),
        .axil_gpu_wdata     (bus_axil_gpu_wdata),
        .axil_gpu_wstrb     (bus_axil_gpu_wstrb),
        .axil_gpu_wvalid    (bus_axil_gpu_wvalid),
        .axil_gpu_wready    (bus_axil_gpu_wready),
        .axil_gpu_bresp     (bus_axil_gpu_bresp),
        .axil_gpu_bvalid    (bus_axil_gpu_bvalid),
        .axil_gpu_bready    (bus_axil_gpu_bready),
        .axil_gpu_araddr    (bus_axil_gpu_araddr),
        .axil_gpu_arprot    (bus_axil_gpu_arprot),
        .axil_gpu_arvalid   (bus_axil_gpu_arvalid),
        .axil_gpu_arready   (bus_axil_gpu_arready),
        .axil_gpu_rdata     (bus_axil_gpu_rdata),
        .axil_gpu_rresp     (bus_axil_gpu_rresp),
        .axil_gpu_rvalid    (bus_axil_gpu_rvalid),
        .axil_gpu_rready    (bus_axil_gpu_rready),
        // AXI-Lite DMA ctrl (ring slot AXIL_DMA=2)
        .axil_dma_awaddr    (bus_axil_dma_awaddr),
        .axil_dma_awprot    (bus_axil_dma_awprot),
        .axil_dma_awvalid   (bus_axil_dma_awvalid),
        .axil_dma_awready   (bus_axil_dma_awready),
        .axil_dma_wdata     (bus_axil_dma_wdata),
        .axil_dma_wstrb     (bus_axil_dma_wstrb),
        .axil_dma_wvalid    (bus_axil_dma_wvalid),
        .axil_dma_wready    (bus_axil_dma_wready),
        .axil_dma_bresp     (bus_axil_dma_bresp),
        .axil_dma_bvalid    (bus_axil_dma_bvalid),
        .axil_dma_bready    (bus_axil_dma_bready),
        .axil_dma_araddr    (bus_axil_dma_araddr),
        .axil_dma_arprot    (bus_axil_dma_arprot),
        .axil_dma_arvalid   (bus_axil_dma_arvalid),
        .axil_dma_arready   (bus_axil_dma_arready),
        .axil_dma_rdata     (bus_axil_dma_rdata),
        .axil_dma_rresp     (bus_axil_dma_rresp),
        .axil_dma_rvalid    (bus_axil_dma_rvalid),
        .axil_dma_rready    (bus_axil_dma_rready),
        // APB peripheral ports (all 7 slaves)
        .apb_psel       (apb_psel),
        .apb_penable    (apb_penable),
        .apb_pwrite     (apb_pwrite),
        .apb_paddr      (apb_paddr),
        .apb_pwdata     (apb_pwdata),
        .apb_pstrb      (apb_pstrb),
        .apb_prdata     (apb_prdata),
        .apb_pready     (apb_pready),
        .apb_pslverr    (apb_pslverr)
    );

    // =========================================================================
    // S0: Boot ROM (boot_rom) ← crossbar SLV_ROM
    // =========================================================================
    boot_rom #(
        .MEM_WORDS    (1024),
        .MEM_INIT_FILE(MEM_INIT_FILE)
    ) u_boot_rom (
        .clk          (core_clk),
        .rst_n        (core_rst_n),
        .s_awid       (bus_rom_awid),
        .s_awaddr     (bus_rom_awaddr),
        .s_awlen      (bus_rom_awlen),
        .s_awsize     (bus_rom_awsize),
        .s_awburst    (bus_rom_awburst),
        .s_awvalid    (bus_rom_awvalid),
        .s_awready    (bus_rom_awready),
        .s_wdata      (bus_rom_wdata),
        .s_wstrb      (bus_rom_wstrb),
        .s_wlast      (bus_rom_wlast),
        .s_wvalid     (bus_rom_wvalid),
        .s_wready     (bus_rom_wready),
        .s_bid        (bus_rom_bid),
        .s_bresp      (bus_rom_bresp),
        .s_bvalid     (bus_rom_bvalid),
        .s_bready     (bus_rom_bready),
        .s_arid       (bus_rom_arid),
        .s_araddr     (bus_rom_araddr),
        .s_arlen      (bus_rom_arlen),
        .s_arsize     (bus_rom_arsize),
        .s_arburst    (bus_rom_arburst),
        .s_arvalid    (bus_rom_arvalid),
        .s_arready    (bus_rom_arready),
        .s_rid        (bus_rom_rid),
        .s_rdata      (bus_rom_rdata),
        .s_rresp      (bus_rom_rresp),
        .s_rlast      (bus_rom_rlast),
        .s_rvalid     (bus_rom_rvalid),
        .s_rready     (bus_rom_rready)
    );

    // =========================================================================
    // S1: SRAM controller (sram_controller) ← crossbar SLV_SRAM
    // =========================================================================
    sram_controller #(
        .MEM_WORDS    (SRAM_MEM_WORDS)
    ) u_sram (
        .clk          (core_clk),
        .rst_n        (core_rst_n),
        .s_awid       (bus_mem_awid),
        .s_awaddr     (bus_mem_awaddr),
        .s_awlen      (bus_mem_awlen),
        .s_awsize     (bus_mem_awsize),
        .s_awburst    (bus_mem_awburst),
        .s_awvalid    (bus_mem_awvalid),
        .s_awready    (bus_mem_awready),
        .s_wdata      (bus_mem_wdata),
        .s_wstrb      (bus_mem_wstrb),
        .s_wlast      (bus_mem_wlast),
        .s_wvalid     (bus_mem_wvalid),
        .s_wready     (bus_mem_wready),
        .s_bid        (bus_mem_bid),
        .s_bresp      (bus_mem_bresp),
        .s_bvalid     (bus_mem_bvalid),
        .s_bready     (bus_mem_bready),
        .s_arid       (bus_mem_arid),
        .s_araddr     (bus_mem_araddr),
        .s_arlen      (bus_mem_arlen),
        .s_arsize     (bus_mem_arsize),
        .s_arburst    (bus_mem_arburst),
        .s_arvalid    (bus_mem_arvalid),
        .s_arready    (bus_mem_arready),
        .s_rid        (bus_mem_rid),
        .s_rdata      (bus_mem_rdata),
        .s_rresp      (bus_mem_rresp),
        .s_rlast      (bus_mem_rlast),
        .s_rvalid     (bus_mem_rvalid),
        .s_rready     (bus_mem_rready)
    );

    // (S2/periph, AXI-Lite ring, APB bridge, and APB interconnect are now
    //  all inside soc_bus u_bus above.)

    // =========================================================================
    // UART — APB slave (apb_psel[APB_UART])
    // =========================================================================
    uart_controller #(
        .ADDR_W (12)
    ) u_uart (
        .clk        (core_clk),
        .rst_n      (core_rst_n),
        .psel       (apb_psel    [APB_UART]),
        .penable    (apb_penable [APB_UART]),
        .pwrite     (apb_pwrite  [APB_UART]),
        .paddr      (apb_paddr   [APB_UART][11:0]),
        .pwdata     (apb_pwdata  [APB_UART]),
        .pstrb      (apb_pstrb   [APB_UART]),
        .prdata     (apb_prdata  [APB_UART]),
        .pready     (apb_pready  [APB_UART]),
        .pslverr    (apb_pslverr [APB_UART]),
        .uart_tx_o  (uart_tx_o),
        .uart_rx_i  (uart_rx_i),
        .irq_o      (uart_irq)
    );

    // =========================================================================
    // SPI — APB slave (apb_psel[APB_SPI])
    // =========================================================================
    spi_controller #(
        .ADDR_W (12)
    ) u_spi (
        .clk        (core_clk),
        .rst_n      (core_rst_n),
        .psel       (apb_psel    [APB_SPI]),
        .penable    (apb_penable [APB_SPI]),
        .pwrite     (apb_pwrite  [APB_SPI]),
        .paddr      (apb_paddr   [APB_SPI][11:0]),
        .pwdata     (apb_pwdata  [APB_SPI]),
        .pstrb      (apb_pstrb   [APB_SPI]),
        .prdata     (apb_prdata  [APB_SPI]),
        .pready     (apb_pready  [APB_SPI]),
        .pslverr    (apb_pslverr [APB_SPI]),
        .spi_sclk_o (spi_sclk_o),
        .spi_mosi_o (spi_mosi_o),
        .spi_miso_i (spi_miso_i),
        .spi_cs_n_o (spi_cs_n_o),
        .irq_o      (spi_irq)
    );

    // =========================================================================
    // Timer — APB slave (apb_psel[APB_TIMER])
    // =========================================================================
    timer #(
        .ADDR_W (12)
    ) u_timer (
        .clk     (core_clk),
        .rst_n   (core_rst_n),
        .psel    (apb_psel    [APB_TIMER]),
        .penable (apb_penable [APB_TIMER]),
        .pwrite  (apb_pwrite  [APB_TIMER]),
        .paddr   (apb_paddr   [APB_TIMER][11:0]),
        .pwdata  (apb_pwdata  [APB_TIMER]),
        .pstrb   (apb_pstrb   [APB_TIMER]),
        .prdata  (apb_prdata  [APB_TIMER]),
        .pready  (apb_pready  [APB_TIMER]),
        .pslverr (apb_pslverr [APB_TIMER]),
        .irq_o   (timer_irq)   // → CPU timer_irq_i (MTIP)
    );

    // =========================================================================
    // Interrupt controller — APB slave (apb_psel[APB_IRQ])
    // irq_src_i[4:0] = {GPU[4], DMA[3], TIMER[2]=0, SPI[1], UART[0]}
    // TIMER slot tied 0: timer IRQ goes directly to CPU MTIP; routing it here
    // too would double-count the event.
    // =========================================================================
    interrupt_controller #(
        .ADDR_W    (12),
        .N_SOURCES (5)
    ) u_irq_ctrl (
        .clk        (core_clk),
        .rst_n      (core_rst_n),
        .psel       (apb_psel    [APB_IRQ]),
        .penable    (apb_penable [APB_IRQ]),
        .pwrite     (apb_pwrite  [APB_IRQ]),
        .paddr      (apb_paddr   [APB_IRQ][11:0]),
        .pwdata     (apb_pwdata  [APB_IRQ]),
        .pstrb      (apb_pstrb   [APB_IRQ]),
        .prdata     (apb_prdata  [APB_IRQ]),
        .pready     (apb_pready  [APB_IRQ]),
        .pslverr    (apb_pslverr [APB_IRQ]),
        .irq_src_i  ({gpu_irq_o, dma_irq, 1'b0, spi_irq, uart_irq}),
        .irq_o      (ext_irq)
    );

    // =========================================================================
    // Pre-Phase-6 #3: PLL subsystem (pll_clkgen + pll_apb_regs + reset glue)
    //
    // pll_subsystem encapsulates:
    //   • pll_clkgen (STUB or RNM via PLL_IMPL)
    //   • pll_apb_regs (APB4 config slave for CONTROL/STATUS registers)
    //   • pll_rst_n = rst_n_i & pll_enable
    //   • core_rst_n = rst_n_i & pll_locked
    //
    // IMPORTANT — clock-domain rule (preserved from prior inline form):
    //   u_pll_sub and all logic inside it run on clk_i / rst_n_i.
    //   They are the SOURCE of core_clk and pll_locked; placing them on
    //   core_clk creates a bootstrap deadlock.  See pll_subsystem.sv header
    //   for the full rationale and RNM-mode CDC deferral note.
    // =========================================================================
    pll_subsystem #(
        .PLL_IMPL        (PLL_IMPL),
        .STUB_LOCK_CYCLES(16),
        .ADDR_W          (12)
    ) u_pll_sub (
        // Reference clock domain — NOT core_clk (see note above)
        .clk_i       (clk_i),
        .rst_n_i     (rst_n_i),
        // APB4 slave ← apb_interconnect APB_PLL slot (runs on clk_i in STUB)
        .psel        (apb_psel    [APB_PLL]),
        .penable     (apb_penable [APB_PLL]),
        .pwrite      (apb_pwrite  [APB_PLL]),
        .paddr       (apb_paddr   [APB_PLL][11:0]),
        .pwdata      (apb_pwdata  [APB_PLL]),
        .pstrb       (apb_pstrb   [APB_PLL]),
        .prdata      (apb_prdata  [APB_PLL]),
        .pready      (apb_pready  [APB_PLL]),
        .pslverr     (apb_pslverr [APB_PLL]),
        // PLL outputs → soc_top distribution
        .core_clk    (core_clk),
        .core_rst_n  (core_rst_n),
        .pll_locked_o(pll_locked)
    );

    // Export PLL lock status to top-level port
    assign pll_locked_o = pll_locked;

    // =========================================================================
    // GH #93: APB4 CDC bridge for the APB_PLL2 slot.
    //
    // apb_interconnect is purely combinational (no clock port, see
    // soc_bus.sv "5. APB interconnect"); the APB transaction is driven by
    // axil_to_apb in the core_clk domain, while u_cpu_pll_sub samples
    // psel/penable and returns pready/prdata in the cpu_clk_i domain. Once
    // GH #93 makes cpu_clk_i a genuinely independent reference (no longer
    // required to equal clk_i for correctness elsewhere), that handshake
    // would cross a clock boundary with no synchroniser — the same
    // mechanism as GH #86 (APB_PLL in RNM mode), but live in the DEFAULT
    // STUB build as soon as the two reference clocks differ.
    //
    // Fixed here (not deferred): apb_cdc_bridge.sv implements a 2-phase
    // toggle handshake between the two domains — see that file's header for
    // the full protocol and CDC argument. Source (s_*) face is core_clk
    // (matches apb_interconnect/axil_to_apb); destination (m_*) face is
    // cpu_clk_i (matches u_cpu_pll_sub's own clk_i — pll_subsystem.sv:11-17's
    // bootstrap rule requires its APB regs run on the raw reference, not
    // cpu_core_clk).
    // =========================================================================
    logic        pll2_m_psel, pll2_m_penable, pll2_m_pwrite;
    logic [11:0] pll2_m_paddr;
    logic [31:0] pll2_m_pwdata, pll2_m_prdata;
    logic [3:0]  pll2_m_pstrb;
    logic        pll2_m_pready, pll2_m_pslverr;

    apb_cdc_bridge #(
        .ADDR_W (12)
    ) u_apb_pll2_cdc (
        .s_clk_i     (core_clk),
        .s_rst_n_i   (core_rst_n),
        .s_psel_i    (apb_psel    [APB_PLL2]),
        .s_penable_i (apb_penable [APB_PLL2]),
        .s_pwrite_i  (apb_pwrite  [APB_PLL2]),
        .s_paddr_i   (apb_paddr   [APB_PLL2][11:0]),
        .s_pwdata_i  (apb_pwdata  [APB_PLL2]),
        .s_pstrb_i   (apb_pstrb   [APB_PLL2]),
        .s_prdata_o  (apb_prdata  [APB_PLL2]),
        .s_pready_o  (apb_pready  [APB_PLL2]),
        .s_pslverr_o (apb_pslverr [APB_PLL2]),

        .m_clk_i     (cpu_clk_i),
        .m_rst_n_i   (cpu_rst_n_i),
        .m_psel_o    (pll2_m_psel),
        .m_penable_o (pll2_m_penable),
        .m_pwrite_o  (pll2_m_pwrite),
        .m_paddr_o   (pll2_m_paddr),
        .m_pwdata_o  (pll2_m_pwdata),
        .m_pstrb_o   (pll2_m_pstrb),
        .m_prdata_i  (pll2_m_prdata),
        .m_pready_i  (pll2_m_pready),
        .m_pslverr_i (pll2_m_pslverr)
    );

    // =========================================================================
    // GH #92/#93: second pll_subsystem instance — CPU-domain reference clock,
    // now the CPU's real clock root.
    //
    // Same bootstrap rule as u_pll_sub above: u_cpu_pll_sub and everything
    // inside it run on cpu_clk_i / cpu_rst_n_i (its own raw reference), never
    // on a generated clock. cpu_core_clk / cpu_core_rst_n feed u_cpu_cg and
    // the CPU-domain reset tree (see PMU sequencing nets above). cpu_pll_locked
    // is exported at cpu_pll_locked_o for observability, mirroring pll_locked_o.
    // =========================================================================
    pll_subsystem #(
        .PLL_IMPL        (PLL_IMPL),
        .STUB_LOCK_CYCLES(16),
        .ADDR_W          (12)
    ) u_cpu_pll_sub (
        // Reference clock domain — the CPU-domain reference, NOT core_clk
        // and NOT cpu_core_clk (see bootstrap-deadlock note above).
        .clk_i       (cpu_clk_i),
        .rst_n_i     (cpu_rst_n_i),
        // APB4 slave ← u_apb_pll2_cdc m_* face (cpu_clk_i domain — see CDC
        // bridge note above).
        .psel        (pll2_m_psel),
        .penable     (pll2_m_penable),
        .pwrite      (pll2_m_pwrite),
        .paddr       (pll2_m_paddr),
        .pwdata      (pll2_m_pwdata),
        .pstrb       (pll2_m_pstrb),
        .prdata      (pll2_m_prdata),
        .pready      (pll2_m_pready),
        .pslverr     (pll2_m_pslverr),
        // PLL outputs — feed u_cpu_cg and the CPU-domain reset tree (GH #93)
        .core_clk    (cpu_core_clk),
        .core_rst_n  (cpu_core_rst_n),
        .pll_locked_o(cpu_pll_locked)
    );

    // Export CPU-domain PLL lock status to top-level port
    assign cpu_pll_locked_o = cpu_pll_locked;

    // =========================================================================
    // Pre-Phase-6 #5 (GH #98/#99/#100): PMU (behavioral power-mode sequencer)
    //
    // Runs on core_clk/core_rst_n (PD_PERIPH, always-on) — the PMU sequences
    // the CPU/GPU domains, so it must never itself be clock-gated or held in
    // one of the domain resets it drives. See pmu.sv header for the register
    // map, FSM, and reset-style rationale.
    // =========================================================================
    pmu #(
        .ADDR_W (12)
    ) u_pmu (
        .clk_i               (core_clk),
        .rst_n_i             (core_rst_n),
        // APB4 slave ← apb_interconnect APB_PMU slot
        .psel                (apb_psel    [APB_PMU]),
        .penable             (apb_penable [APB_PMU]),
        .pwrite              (apb_pwrite  [APB_PMU]),
        .paddr               (apb_paddr   [APB_PMU][11:0]),
        .pwdata              (apb_pwdata  [APB_PMU]),
        .pstrb               (apb_pstrb   [APB_PMU]),
        .prdata              (apb_prdata  [APB_PMU]),
        .pready              (apb_pready  [APB_PMU]),
        .pslverr             (apb_pslverr [APB_PMU]),
        // CPU domain sequencing (PD_CPU)
        .cpu_clk_en_o        (pmu_cpu_clk_en),
        .cpu_iso_en_o        (pmu_cpu_iso_en),
        .cpu_rst_n_o         (pmu_cpu_rst_n),
        .cpu_ret_save_o      (pmu_cpu_ret_save),
        .cpu_ret_restore_o   (pmu_cpu_ret_restore),
        // GPU domain sequencing (PD_GPU)
        .gpu_clk_en_o        (pmu_gpu_clk_en),
        .gpu_iso_en_o        (pmu_gpu_iso_en),
        .gpu_rst_n_o         (pmu_gpu_rst_n),
        .gpu_ret_save_o      (pmu_gpu_ret_save),
        .gpu_ret_restore_o   (pmu_gpu_ret_restore)
    );

    // CPU/GPU integrated clock gates (glitch-free ICG), enabled by the PMU's
    // per-domain clk_en. At pmu.sv reset default (clk_en=1) these are
    // transparent, so cpu_gated_clk == cpu_core_clk / gpu_gated_clk ==
    // core_clk with no firmware PMU writes.
    //
    // GH #93: u_cpu_cg is re-sourced from cpu_core_clk (the CPU's own PLL
    // output) instead of core_clk, gated by ~pmu_cpu_clk_dis_sync (already
    // synchronised into the cpu_core_clk domain above, INVERTED for reset
    // safety — see the ordering note above u_cpu_clk_dis_sync — GH #93-fix).
    // u_gpu_cg is UNCHANGED (still core_clk / pmu_gpu_clk_en directly; the
    // GPU did not move domains, so its clk_en/rst_n share one clock domain
    // with the PMU FSM that drives them — no independent-synchroniser race
    // is possible there, so it needs no equivalent of the AND below).
    //
    // GH #90 bead 542 fix: u_cpu_cg's enable is additionally ANDed with
    // pmu_cpu_rst_n_cpu_sync (see the detailed hazard/skew-tolerance writeup
    // above u_cpu_clk_dis_sync) so cpu_gated_clk cannot tick while the
    // CPU-domain-observed PMU reset is asserted, regardless of the relative
    // timing of the two independent CDC synchronisers feeding this logic.
    //
    // ICG glitch-safety (rv32i_clock_gate.sv): en is latched transparent-low
    // and ANDed with clk, so `en` may only be sampled while clk is low —
    // any change to `en` while clk is high is invisible to gclk until the
    // next low phase, which is exactly what makes this ICG glitch-free
    // regardless of what drives `en`. cpu_gated_clk_en is a combinational AND
    // of two flop outputs both registered on cpu_core_clk (the same clk
    // driving this gate) — ~pmu_cpu_clk_dis_sync (u_cpu_clk_dis_sync) and
    // pmu_cpu_rst_n_cpu_sync (u_cpu_pmu_rst_sync) — so it is a clean,
    // synchronously-timed signal with no combinational glitch hazard of its
    // own, same as the single-signal case it replaces — safe to drive `en`
    // directly.
    logic cpu_gated_clk_en;
    assign cpu_gated_clk_en = ~pmu_cpu_clk_dis_sync & pmu_cpu_rst_n_cpu_sync;

    rv32i_clock_gate u_cpu_cg (.en(cpu_gated_clk_en), .clk(cpu_core_clk), .gclk(cpu_gated_clk));
    rv32i_clock_gate u_gpu_cg (.en(pmu_gpu_clk_en), .clk(core_clk), .gclk(gpu_gated_clk));

endmodule : soc_top
