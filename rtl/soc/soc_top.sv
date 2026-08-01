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
//   Debug plane   : APB3 debug slave exposed at top-level ports.
//
//   Clock seam (Phase 7 M-c; GH #92 — dual PLL / two reference clock roots):
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
//     Scope note: the CPU (u_cpu / u_cpu_cg) still runs on core_clk /
//       cpu_gated_clk in THIS PR — cpu_core_clk / cpu_core_rst_n are generated
//       but have no consumer until GH #93 re-sources u_cpu_cg from them (scoped
//       lint waiver below). In a single-clock build, tie cpu_clk_i == clk_i and
//       cpu_rst_n_i == rst_n_i at the integration site (see tb_soc_top.sv /
//       tb_soc_pll.sv for the reference tie-off).
//     CDC hazard surfaced by this exploration, left for GH #93 to solve: once
//       GH #93 re-sources u_cpu_cg from cpu_core_clk, the PMU's
//       pmu_cpu_clk_en / pmu_cpu_rst_n (generated in the core_clk/system
//       domain, see PMU sequencing nets below) will cross into the CPU domain
//       unsynchronised. The intended primitives for that crossing are
//       rtl/soc/cdc/cdc_2ff_sync.sv (control bit) and
//       rtl/soc/cdc/cdc_reset_sync.sv (reset), landed in GH #91. NOT fixed
//       here — CPU stays on core_clk in this PR, so no crossing exists yet.
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
    // (u_cpu_pll_sub). The CPU itself is NOT yet re-sourced from this domain
    // — that is GH #93's scope; here the reference clock + PLL are wired up
    // so PD has two genuine clock roots (GH #94) and the output (cpu_core_clk)
    // is intentionally unconsumed (see scoped waiver below). In a
    // single-clock build, tie cpu_clk_i == clk_i and cpu_rst_n_i == rst_n_i.
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
    // GH #92: second (CPU-domain) PLL subsystem
    //   cpu_clk_i → u_cpu_pll_sub.clk_i  (independent reference clock root)
    //   cpu_core_clk / cpu_core_rst_n / cpu_pll_locked are produced but have
    //   NO consumer in this PR — the CPU stays on core_clk/cpu_gated_clk
    //   until GH #93 re-sources u_cpu_cg from cpu_core_clk. Scoped waiver
    //   below (not a bare dangling net): only cpu_pll_locked is genuinely
    //   consumed, by being exported at cpu_pll_locked_o.
    // =========================================================================
    /* verilator lint_off UNUSEDSIGNAL */
    // cpu_core_clk / cpu_core_rst_n: unconsumed until GH #93 re-sources
    // u_cpu_cg from the CPU-domain PLL instead of core_clk.
    logic cpu_core_clk;
    logic cpu_core_rst_n;
    /* verilator lint_on  UNUSEDSIGNAL */
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
    localparam int unsigned N_APB_SLV = APB_N_SLAVES; // 6

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

    // Per-domain reset actually applied to u_cpu / u_gpu: core_rst_n ANDed
    // with the PMU's per-domain reset. Default (pmu_*_rst_n=1 at PMU reset,
    // DOM_ON) makes this identical to core_rst_n -- no behavior change for
    // the existing soc_all regression.
    logic cpu_domain_rst_n, gpu_domain_rst_n;
    assign cpu_domain_rst_n = core_rst_n & pmu_cpu_rst_n;
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
    // M0: CPU (rv32i_cpu_top) → crossbar M0
    // =========================================================================
    rv32i_cpu_top #(
        .RESET_PC (32'h0000_1000)
    ) u_cpu (
        .clk_i                      (cpu_gated_clk),
        .rst_n_i                    (cpu_domain_rst_n),
        // AXI4 master → crossbar M0 (raw; clamped by ISO_CPU below)
        .axi_awaddr_o               (xbar_m_awaddr  [0]),
        .axi_awlen_o                (xbar_m_awlen   [0]),
        .axi_awsize_o               (xbar_m_awsize  [0]),
        .axi_awburst_o              (xbar_m_awburst [0]),
        .axi_awvalid_o              (cpu_axi_awvalid_raw),
        .axi_awready_i              (xbar_m_awready [0]),
        .axi_wdata_o                (xbar_m_wdata   [0]),
        .axi_wstrb_o                (xbar_m_wstrb   [0]),
        .axi_wlast_o                (xbar_m_wlast   [0]),
        .axi_wvalid_o               (cpu_axi_wvalid_raw),
        .axi_wready_i               (xbar_m_wready  [0]),
        .axi_bresp_i                (xbar_m_bresp   [0]),
        .axi_bvalid_i               (xbar_m_bvalid  [0]),
        .axi_bready_o               (cpu_axi_bready_raw),
        .axi_araddr_o               (xbar_m_araddr  [0]),
        .axi_arlen_o                (xbar_m_arlen   [0]),
        .axi_arsize_o               (xbar_m_arsize  [0]),
        .axi_arburst_o              (xbar_m_arburst [0]),
        .axi_arvalid_o              (cpu_axi_arvalid_raw),
        .axi_arready_i              (xbar_m_arready [0]),
        .axi_rdata_i                (xbar_m_rdata   [0]),
        .axi_rresp_i                (xbar_m_rresp   [0]),
        .axi_rvalid_i               (xbar_m_rvalid  [0]),
        .axi_rlast_i                (xbar_m_rlast   [0]),
        .axi_rready_o               (cpu_axi_rready_raw),
        // APB3 debug slave (exposed at soc_top ports; not isolation-clamped —
        // stalling a debug access into a gated CPU domain is expected/OK)
        .apb_paddr_i                (apb_paddr_i),
        .apb_psel_i                 (apb_psel_i),
        .apb_penable_i              (apb_penable_i),
        .apb_pwrite_i               (apb_pwrite_i),
        .apb_pwdata_i               (apb_pwdata_i),
        .apb_prdata_o               (apb_prdata_o),
        .apb_pready_o               (apb_pready_o),
        .apb_pslverr_o              (apb_pslverr_o),
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
        // Interrupt inputs
        .ext_irq_i                  (ext_irq),
        .timer_irq_i                (timer_irq)
    );

    // ISO_CPU functional-isolation clamp (`-location parent`, clamp_value 0):
    // forces the CPU->fabric handshake + commit observability to 0 while
    // pmu_cpu_iso_en is asserted. See clamp-scope note above u_cpu.
    assign xbar_m_awvalid [0] = pmu_cpu_iso_en ? 1'b0 : cpu_axi_awvalid_raw;
    assign xbar_m_wvalid  [0] = pmu_cpu_iso_en ? 1'b0 : cpu_axi_wvalid_raw;
    assign xbar_m_arvalid [0] = pmu_cpu_iso_en ? 1'b0 : cpu_axi_arvalid_raw;
    assign xbar_m_bready  [0] = pmu_cpu_iso_en ? 1'b0 : cpu_axi_bready_raw;
    assign xbar_m_rready  [0] = pmu_cpu_iso_en ? 1'b0 : cpu_axi_rready_raw;
    assign commit_valid_o     = pmu_cpu_iso_en ? 1'b0 : cpu_commit_valid_raw;

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
        // APB peripheral ports (all 6 slaves)
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
    // GH #92: second pll_subsystem instance — CPU-domain reference clock.
    //
    // Same bootstrap rule as u_pll_sub above: u_cpu_pll_sub and everything
    // inside it run on cpu_clk_i / cpu_rst_n_i (its own raw reference), never
    // on a generated clock. cpu_core_clk / cpu_core_rst_n are produced here
    // but have no consumer until GH #93 (see scoped UNUSEDSIGNAL waiver on
    // the net declarations above). cpu_pll_locked IS consumed — exported at
    // cpu_pll_locked_o for observability, mirroring pll_locked_o.
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
        // APB4 slave ← apb_interconnect APB_PLL2 slot.
        //
        // ⚠️ UNSYNCHRONISED CDC — READ BEFORE DRIVING cpu_clk_i != clk_i.
        // apb_interconnect is purely combinational (no clock port, see
        // soc_bus.sv "APB interconnect"); the APB transaction is driven by
        // axil_to_apb in the core_clk domain, while this instance samples
        // psel/penable and returns pready/prdata in the cpu_clk_i domain.
        // Whenever cpu_clk_i != clk_i that handshake crosses a clock boundary
        // with no synchroniser, so an APB access to the PLL2 config registers
        // (0x2000_9000-9FFF) can be corrupted or can hang the APB master.
        //
        // This is the same mechanism as GH #86 (APB_PLL in RNM mode), but for
        // PLL2 it is live in the DEFAULT STUB build as soon as the two
        // reference clocks differ — #86's "STUB makes core_clk == clk_i so no
        // CDC exists" argument does NOT rescue this slot.
        //
        // Safe today: every current testbench ties cpu_clk_i == clk_i (see
        // tb_soc_top.sv / tb_soc_pll.sv), so the two domains are one physical
        // clock and no crossing exists. Firmware/tests MUST NOT access the
        // PLL2 register block while the references differ until an async APB
        // bridge (or command CDC with synchronised valid/ready) is added.
        // Tracked for GH #93/#95 alongside the pmu_cpu_* crossing noted in the
        // clock-seam block above.
        .psel        (apb_psel    [APB_PLL2]),
        .penable     (apb_penable [APB_PLL2]),
        .pwrite      (apb_pwrite  [APB_PLL2]),
        .paddr       (apb_paddr   [APB_PLL2][11:0]),
        .pwdata      (apb_pwdata  [APB_PLL2]),
        .pstrb       (apb_pstrb   [APB_PLL2]),
        .prdata      (apb_prdata  [APB_PLL2]),
        .pready      (apb_pready  [APB_PLL2]),
        .pslverr     (apb_pslverr [APB_PLL2]),
        // PLL outputs — unconsumed until GH #93 (cpu_core_clk/cpu_core_rst_n)
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

    // CPU/GPU integrated clock gates (glitch-free ICG) — gate core_clk before
    // it reaches u_cpu / u_gpu, enabled by the PMU's per-domain clk_en. At
    // pmu.sv reset default (clk_en=1) these are transparent, so cpu_gated_clk
    // / gpu_gated_clk == core_clk with no firmware PMU writes.
    rv32i_clock_gate u_cpu_cg (.en(pmu_cpu_clk_en), .clk(core_clk), .gclk(cpu_gated_clk));
    rv32i_clock_gate u_gpu_cg (.en(pmu_gpu_clk_en), .clk(core_clk), .gclk(gpu_gated_clk));

endmodule : soc_top
