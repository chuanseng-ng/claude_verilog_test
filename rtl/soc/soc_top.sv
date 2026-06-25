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
//     S2 = Periph    (axi4_to_axilite → axi_lite_interconnect, 0x2000_1000–7FFF)
//
//   Control plane : axi4_to_axilite → axi_lite_interconnect (N_SLAVES=3)
//     AXIL_GPU=0        @ 0x2000_1000–1FFF  (AXI-Lite direct)
//     AXIL_APB_BRIDGE=1 @ 0x2000_2000–7FFF  (axil_to_apb → apb_interconnect)
//     AXIL_DMA=2        @ 0x2000_5000–5FFF  (AXI-Lite direct; last-match wins
//                                             over APB_BRIDGE window overlap)
//
//   APB sub-tree (5 slaves behind axil_to_apb bridge):
//     APB_UART=0  @ 0x2000_2000–2FFF  uart_controller
//     APB_SPI=1   @ 0x2000_3000–3FFF  spi_controller
//     APB_TIMER=2 @ 0x2000_4000–4FFF  timer
//     APB_IRQ=3   @ 0x2000_6000–6FFF  interrupt_controller
//     APB_PLL=4   @ 0x2000_7000–7FFF  pll_apb_regs (clk_i domain)
//
//   Debug plane   : APB3 debug slave exposed at top-level ports.
//
//   Clock seam (Phase 7 M-c):
//     clk_i is the external reference clock (100 MHz crystal/XO).
//     pll_clkgen converts it to core_clk (1.282 GHz in RNM; ref passthrough in stub).
//     All child instances run on core_clk.
//     core_rst_n = rst_n_i & pll_locked so children are held in reset until PLL locks.
//     PLL_IMPL parameter selects "STUB" (default, synth-safe) or "RNM" (M-c cosim).
//
//   IRQ routing:
//     irq_src_i = {gpu_irq_o[4], dma_irq[3], timer_irq[2], spi_irq[1], uart_irq[0]}
//     interrupt_controller.irq_o → CPU ext_irq_i (MEIP)
//     timer.irq_o                → CPU timer_irq_i (MTIP, direct)
//
// Rules: no logic beyond wiring; clk/rst_n rooted at clk_i/rst_n_i.
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
    // Note: `parameter string` is hidden under `__pnr__` because Synlig UHDM
    // (this version of Yosys) creates empty-named RTLIL wires for string-typed
    // parameters, causing kernel/rtlil.cc:2150 assert.  PnR always uses the
    // integer stub (MEM_INIT_FILE unused; boot ROM inits to zero in synthesis).
`ifndef __pnr__
    parameter string MEM_INIT_FILE = "",
`else
    parameter int unsigned MEM_INIT_FILE = 0,  // unused in PnR — boot ROM = 0
`endif

    // PLL implementation selector (Phase 7 M-c).
    //   "STUB" (default) — synthesisable digital stub; out_clk = ref_clk.
    //   "RNM"            — real-number model; use only for M-c AMS co-sim.
    // Hidden under `__pnr__` for same Synlig reason as MEM_INIT_FILE.
    // PnR always synthesises STUB behaviour (pll_rnm.sv excluded from flow).
`ifndef __pnr__
    parameter string PLL_IMPL = "STUB",
`else
    parameter int unsigned PLL_IMPL = 0,        // 0 = STUB in PnR
`endif

    // Behavioral SRAM depth in 32-bit words (power of two).
    // Default 1024 (4 KB) matches the existing regression/PD baseline.
    // Override to 65536 (256 KB) for M10 cache-capacity benchmarks.
    parameter int unsigned SRAM_MEM_WORDS = 1024
) (
    // clk_i is the reference clock input (100 MHz crystal / XO).
    // Internally the SoC runs on core_clk derived from the PLL.
    // In STUB mode core_clk == clk_i (lock counter fires after 16 cycles).
    input  logic clk_i,
    input  logic rst_n_i,

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

    // ── PLL status (Phase 7 M-c) ─────────────────────────────────────────────
    output logic        pll_locked_o    // 1 when PLL has acquired lock
);

    // =========================================================================
    // Local parameters
    // =========================================================================
    localparam int unsigned N_MASTERS   = 4;
    localparam int unsigned N_SLAVES    = SOC_N_SLAVES;    // 3
    localparam int unsigned N_AXIL_SLV  = AXIL_N_SLAVES;  // 3 (PR-7: GPU, APB_BRIDGE, DMA)
    localparam int unsigned AW          = AXI_ADDR_WIDTH;
    localparam int unsigned DW          = AXI_DATA_WIDTH;
    localparam int unsigned SW          = AXI_STRB_WIDTH;
    localparam int unsigned IW          = AXI_ID_WIDTH;
    localparam int unsigned LENW        = AXI_LEN_WIDTH;

    // =========================================================================
    // Phase 7 M-c: PLL clock seam
    //   clk_i  → pll_clkgen.ref_clk_i
    //   core_clk   = pll_clkgen.out_clk_o  (all children run on this)
    //   pll_locked = pll_clkgen.locked_o
    //   core_rst_n = rst_n_i & pll_locked  (children held in reset until lock)
    //
    // pll_apb_regs drives pll_enable, feedback_div, post_div_sel; PLL rst_n
    // is gated by pll_enable so firmware can keep the PLL in reset on boot.
    // =========================================================================
    logic       core_clk;       // PLL output clock — feeds all child clk ports
    logic       core_rst_n;     // gated reset: rst_n_i & pll_locked
    logic       pll_locked;     // raw PLL lock flag

    // PLL config signals driven by pll_apb_regs
    logic       pll_enable;     // CONTROL[0]: 1 = de-assert PLL reset
    logic [3:0] pll_fb_div;     // CONTROL[7:4]: feedback divider (0 → N=13)
    logic [1:0] pll_post_div;   // CONTROL[9:8]: post-divider select

    // PLL rst_n: de-assert only when top-level rst_n_i AND pll_enable both high
    logic pll_rst_n;
    assign pll_rst_n  = rst_n_i & pll_enable;

    // core_rst_n: hold children in reset until PLL locks
    assign core_rst_n = rst_n_i & pll_locked;

    // Export lock status
    assign pll_locked_o = pll_locked;

    // =========================================================================
    // Crossbar master-facing nets (no ID, packed 2D arrays [N_MASTERS-1:0])
    // Packed form required for Synlig/UHDM RTLIL emission (Yosys synthesis).
    // =========================================================================
    // Write address
    logic [N_MASTERS-1:0][AW-1:0]   xbar_m_awaddr;
    logic [N_MASTERS-1:0][LENW-1:0] xbar_m_awlen;
    logic [N_MASTERS-1:0][2:0]      xbar_m_awsize;
    logic [N_MASTERS-1:0][1:0]      xbar_m_awburst;
    logic [N_MASTERS-1:0]           xbar_m_awvalid;
    logic [N_MASTERS-1:0]           xbar_m_awready;
    // Write data
    logic [N_MASTERS-1:0][DW-1:0]   xbar_m_wdata;
    logic [N_MASTERS-1:0][SW-1:0]   xbar_m_wstrb;
    logic [N_MASTERS-1:0]           xbar_m_wlast;
    logic [N_MASTERS-1:0]           xbar_m_wvalid;
    logic [N_MASTERS-1:0]           xbar_m_wready;
    // Write response
    logic [N_MASTERS-1:0][1:0]      xbar_m_bresp;
    logic [N_MASTERS-1:0]           xbar_m_bvalid;
    logic [N_MASTERS-1:0]           xbar_m_bready;
    // Read address
    logic [N_MASTERS-1:0][AW-1:0]   xbar_m_araddr;
    logic [N_MASTERS-1:0][LENW-1:0] xbar_m_arlen;
    logic [N_MASTERS-1:0][2:0]      xbar_m_arsize;
    logic [N_MASTERS-1:0][1:0]      xbar_m_arburst;
    logic [N_MASTERS-1:0]           xbar_m_arvalid;
    logic [N_MASTERS-1:0]           xbar_m_arready;
    // Read data
    logic [N_MASTERS-1:0][DW-1:0]   xbar_m_rdata;
    logic [N_MASTERS-1:0][1:0]      xbar_m_rresp;
    logic [N_MASTERS-1:0]           xbar_m_rlast;
    logic [N_MASTERS-1:0]           xbar_m_rvalid;
    logic [N_MASTERS-1:0]           xbar_m_rready;

    // =========================================================================
    // Crossbar slave-facing nets (full AXI4 with ID, packed 2D [N_SLAVES-1:0])
    // Packed form required for Synlig/UHDM RTLIL emission (Yosys synthesis).
    // =========================================================================
    logic [N_SLAVES-1:0][IW-1:0]   xbar_s_awid;
    logic [N_SLAVES-1:0][AW-1:0]   xbar_s_awaddr;
    logic [N_SLAVES-1:0][LENW-1:0] xbar_s_awlen;
    logic [N_SLAVES-1:0][2:0]      xbar_s_awsize;
    logic [N_SLAVES-1:0][1:0]      xbar_s_awburst;
    logic [N_SLAVES-1:0]           xbar_s_awvalid;
    logic [N_SLAVES-1:0]           xbar_s_awready;
    logic [N_SLAVES-1:0][DW-1:0]   xbar_s_wdata;
    logic [N_SLAVES-1:0][SW-1:0]   xbar_s_wstrb;
    logic [N_SLAVES-1:0]           xbar_s_wlast;
    logic [N_SLAVES-1:0]           xbar_s_wvalid;
    logic [N_SLAVES-1:0]           xbar_s_wready;
    logic [N_SLAVES-1:0][IW-1:0]   xbar_s_bid;
    logic [N_SLAVES-1:0][1:0]      xbar_s_bresp;
    logic [N_SLAVES-1:0]           xbar_s_bvalid;
    logic [N_SLAVES-1:0]           xbar_s_bready;
    logic [N_SLAVES-1:0][IW-1:0]   xbar_s_arid;
    logic [N_SLAVES-1:0][AW-1:0]   xbar_s_araddr;
    logic [N_SLAVES-1:0][LENW-1:0] xbar_s_arlen;
    logic [N_SLAVES-1:0][2:0]      xbar_s_arsize;
    logic [N_SLAVES-1:0][1:0]      xbar_s_arburst;
    logic [N_SLAVES-1:0]           xbar_s_arvalid;
    logic [N_SLAVES-1:0]           xbar_s_arready;
    logic [N_SLAVES-1:0][IW-1:0]   xbar_s_rid;
    logic [N_SLAVES-1:0][DW-1:0]   xbar_s_rdata;
    logic [N_SLAVES-1:0][1:0]      xbar_s_rresp;
    logic [N_SLAVES-1:0]           xbar_s_rlast;
    logic [N_SLAVES-1:0]           xbar_s_rvalid;
    logic [N_SLAVES-1:0]           xbar_s_rready;

    // =========================================================================
    // axi4_to_axilite bridge (crossbar S2 → axi_lite_interconnect master)
    // =========================================================================
    logic [AW-1:0]   periph_axil_awaddr;
    logic [2:0]      periph_axil_awprot;
    logic            periph_axil_awvalid;
    logic            periph_axil_awready;
    logic [DW-1:0]   periph_axil_wdata;
    logic [SW-1:0]   periph_axil_wstrb;
    logic            periph_axil_wvalid;
    logic            periph_axil_wready;
    logic [1:0]      periph_axil_bresp;
    logic            periph_axil_bvalid;
    logic            periph_axil_bready;
    logic [AW-1:0]   periph_axil_araddr;
    logic [2:0]      periph_axil_arprot;
    logic            periph_axil_arvalid;
    logic            periph_axil_arready;
    logic [DW-1:0]   periph_axil_rdata;
    logic [1:0]      periph_axil_rresp;
    logic            periph_axil_rvalid;
    logic            periph_axil_rready;

    // =========================================================================
    // axi_lite_interconnect slave-facing nets (packed 2D [N_AXIL_SLV-1:0])
    // Packed form required for Synlig/UHDM RTLIL emission (Yosys synthesis).
    // =========================================================================
    logic [N_AXIL_SLV-1:0][AW-1:0] axil_s_awaddr;
    logic [N_AXIL_SLV-1:0][2:0]    axil_s_awprot;
    logic [N_AXIL_SLV-1:0]         axil_s_awvalid;
    logic [N_AXIL_SLV-1:0]         axil_s_awready;
    logic [N_AXIL_SLV-1:0][DW-1:0] axil_s_wdata;
    logic [N_AXIL_SLV-1:0][SW-1:0] axil_s_wstrb;
    logic [N_AXIL_SLV-1:0]         axil_s_wvalid;
    logic [N_AXIL_SLV-1:0]         axil_s_wready;
    logic [N_AXIL_SLV-1:0][1:0]    axil_s_bresp;
    logic [N_AXIL_SLV-1:0]         axil_s_bvalid;
    logic [N_AXIL_SLV-1:0]         axil_s_bready;
    logic [N_AXIL_SLV-1:0][AW-1:0] axil_s_araddr;
    logic [N_AXIL_SLV-1:0][2:0]    axil_s_arprot;
    logic [N_AXIL_SLV-1:0]         axil_s_arvalid;
    logic [N_AXIL_SLV-1:0]         axil_s_arready;
    logic [N_AXIL_SLV-1:0][DW-1:0] axil_s_rdata;
    logic [N_AXIL_SLV-1:0][1:0]    axil_s_rresp;
    logic [N_AXIL_SLV-1:0]         axil_s_rvalid;
    logic [N_AXIL_SLV-1:0]         axil_s_rready;

    // =========================================================================
    // APB nets: axil_to_apb bridge master → apb_interconnect → 5 APB slaves
    // =========================================================================
    localparam int unsigned N_APB_SLV = APB_N_SLAVES; // 5

    // Bridge single APB master output
    logic        apb_m_psel;
    logic        apb_m_penable;
    logic        apb_m_pwrite;
    logic [31:0] apb_m_paddr;
    logic [31:0] apb_m_pwdata;
    logic [3:0]  apb_m_pstrb;
    logic [31:0] apb_m_prdata;   // response back from interconnect
    logic        apb_m_pready;
    logic        apb_m_pslverr;

    // Per-slave APB nets from apb_interconnect to each peripheral
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
    // Intermediate wires: decouple xbar_m_*[0] indexing from port connections
    // so Synlig UHDM does not emit anonymous bit-slice wires (rtlil.cc:2150).
    // =========================================================================
    logic [AW-1:0]   cpu_m_awaddr;
    logic [LENW-1:0] cpu_m_awlen;
    logic [2:0]      cpu_m_awsize;
    logic [1:0]      cpu_m_awburst;
    logic            cpu_m_awvalid;
    logic            cpu_m_awready;
    logic [DW-1:0]   cpu_m_wdata;
    logic [SW-1:0]   cpu_m_wstrb;
    logic            cpu_m_wlast;
    logic            cpu_m_wvalid;
    logic            cpu_m_wready;
    logic [1:0]      cpu_m_bresp;
    logic            cpu_m_bvalid;
    logic            cpu_m_bready;
    logic [AW-1:0]   cpu_m_araddr;
    logic [LENW-1:0] cpu_m_arlen;
    logic [2:0]      cpu_m_arsize;
    logic [1:0]      cpu_m_arburst;
    logic            cpu_m_arvalid;
    logic            cpu_m_arready;
    logic [DW-1:0]   cpu_m_rdata;
    logic [1:0]      cpu_m_rresp;
    logic            cpu_m_rlast;
    logic            cpu_m_rvalid;
    logic            cpu_m_rready;

    rv32i_cpu_top #(
        .RESET_PC (32'h0000_1000)
    ) u_cpu (
        .clk_i                      (core_clk),
        .rst_n_i                    (core_rst_n),
        // AXI4 master → crossbar M0 (via cpu_m_* intermediates)
        .axi_awaddr_o               (cpu_m_awaddr),
        .axi_awlen_o                (cpu_m_awlen),
        .axi_awsize_o               (cpu_m_awsize),
        .axi_awburst_o              (cpu_m_awburst),
        .axi_awvalid_o              (cpu_m_awvalid),
        .axi_awready_i              (cpu_m_awready),
        .axi_wdata_o                (cpu_m_wdata),
        .axi_wstrb_o                (cpu_m_wstrb),
        .axi_wlast_o                (cpu_m_wlast),
        .axi_wvalid_o               (cpu_m_wvalid),
        .axi_wready_i               (cpu_m_wready),
        .axi_bresp_i                (cpu_m_bresp),
        .axi_bvalid_i               (cpu_m_bvalid),
        .axi_bready_o               (cpu_m_bready),
        .axi_araddr_o               (cpu_m_araddr),
        .axi_arlen_o                (cpu_m_arlen),
        .axi_arsize_o               (cpu_m_arsize),
        .axi_arburst_o              (cpu_m_arburst),
        .axi_arvalid_o              (cpu_m_arvalid),
        .axi_arready_i              (cpu_m_arready),
        .axi_rdata_i                (cpu_m_rdata),
        .axi_rresp_i                (cpu_m_rresp),
        .axi_rvalid_i               (cpu_m_rvalid),
        .axi_rlast_i                (cpu_m_rlast),
        .axi_rready_o               (cpu_m_rready),
        // APB3 debug slave (exposed at soc_top ports)
        .apb_paddr_i                (apb_paddr_i),
        .apb_psel_i                 (apb_psel_i),
        .apb_penable_i              (apb_penable_i),
        .apb_pwrite_i               (apb_pwrite_i),
        .apb_pwdata_i               (apb_pwdata_i),
        .apb_prdata_o               (apb_prdata_o),
        .apb_pready_o               (apb_pready_o),
        .apb_pslverr_o              (apb_pslverr_o),
        // Commit observability (partially exposed at top)
        .commit_valid_o             (commit_valid_o),
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
    // cpu_m_* → xbar_m_*[0] assign bridges
    assign xbar_m_awaddr  [0] = cpu_m_awaddr;
    assign xbar_m_awlen   [0] = cpu_m_awlen;
    assign xbar_m_awsize  [0] = cpu_m_awsize;
    assign xbar_m_awburst [0] = cpu_m_awburst;
    assign xbar_m_awvalid [0] = cpu_m_awvalid;
    assign cpu_m_awready       = xbar_m_awready [0];
    assign xbar_m_wdata   [0] = cpu_m_wdata;
    assign xbar_m_wstrb   [0] = cpu_m_wstrb;
    assign xbar_m_wlast   [0] = cpu_m_wlast;
    assign xbar_m_wvalid  [0] = cpu_m_wvalid;
    assign cpu_m_wready        = xbar_m_wready  [0];
    assign cpu_m_bresp         = xbar_m_bresp   [0];
    assign cpu_m_bvalid        = xbar_m_bvalid  [0];
    assign xbar_m_bready  [0] = cpu_m_bready;
    assign xbar_m_araddr  [0] = cpu_m_araddr;
    assign xbar_m_arlen   [0] = cpu_m_arlen;
    assign xbar_m_arsize  [0] = cpu_m_arsize;
    assign xbar_m_arburst [0] = cpu_m_arburst;
    assign xbar_m_arvalid [0] = cpu_m_arvalid;
    assign cpu_m_arready       = xbar_m_arready [0];
    assign cpu_m_rdata         = xbar_m_rdata   [0];
    assign cpu_m_rresp         = xbar_m_rresp   [0];
    assign cpu_m_rlast         = xbar_m_rlast   [0];
    assign cpu_m_rvalid        = xbar_m_rvalid  [0];
    assign xbar_m_rready  [0] = cpu_m_rready;

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
    // Intermediate wires: decouple xbar_m_*[2] and axil_s_*[AXIL_GPU] indexing.
    // =========================================================================
    // M2 data-master intermediates
    logic [AW-1:0]   gpu_m_araddr;
    logic            gpu_m_arvalid;
    logic            gpu_m_arready;
    logic [DW-1:0]   gpu_m_rdata;
    logic [1:0]      gpu_m_rresp;
    logic            gpu_m_rvalid;
    logic            gpu_m_rready;
    logic [AW-1:0]   gpu_m_awaddr;
    logic            gpu_m_awvalid;
    logic            gpu_m_awready;
    logic [DW-1:0]   gpu_m_wdata;
    logic [SW-1:0]   gpu_m_wstrb;
    logic            gpu_m_wvalid;
    logic            gpu_m_wready;
    logic [1:0]      gpu_m_bresp;
    logic            gpu_m_bvalid;
    logic            gpu_m_bready;
    // AXIL_GPU ctrl-slave intermediates
    logic [11:0]     gpu_axil_awaddr;
    logic            gpu_axil_awvalid;
    logic            gpu_axil_awready;
    logic [DW-1:0]   gpu_axil_wdata;
    logic [SW-1:0]   gpu_axil_wstrb;
    logic            gpu_axil_wvalid;
    logic            gpu_axil_wready;
    logic [1:0]      gpu_axil_bresp;
    logic            gpu_axil_bvalid;
    logic            gpu_axil_bready;
    logic [11:0]     gpu_axil_araddr;
    logic            gpu_axil_arvalid;
    logic            gpu_axil_arready;
    logic [DW-1:0]   gpu_axil_rdata;
    logic [1:0]      gpu_axil_rresp;
    logic            gpu_axil_rvalid;
    logic            gpu_axil_rready;

    gpu_top #(
        .GPU_ENABLE_COALESCE (1'b0)
    ) u_gpu (
        .clk                        (core_clk),
        .rst_n                      (core_rst_n),
        // AXI4-Lite ctrl slave ← interconnect AXIL_GPU slot (via gpu_axil_* intermediates)
        .s_axil_awaddr              (gpu_axil_awaddr),
        .s_axil_awvalid             (gpu_axil_awvalid),
        .s_axil_awready             (gpu_axil_awready),
        .s_axil_wdata               (gpu_axil_wdata),
        .s_axil_wstrb               (gpu_axil_wstrb),
        .s_axil_wvalid              (gpu_axil_wvalid),
        .s_axil_wready              (gpu_axil_wready),
        .s_axil_bresp               (gpu_axil_bresp),
        .s_axil_bvalid              (gpu_axil_bvalid),
        .s_axil_bready              (gpu_axil_bready),
        .s_axil_araddr              (gpu_axil_araddr),
        .s_axil_arvalid             (gpu_axil_arvalid),
        .s_axil_arready             (gpu_axil_arready),
        .s_axil_rdata               (gpu_axil_rdata),
        .s_axil_rresp               (gpu_axil_rresp),
        .s_axil_rvalid              (gpu_axil_rvalid),
        .s_axil_rready              (gpu_axil_rready),
        // AXI4-Lite ifetch master → gif adapter slave
        .m_axil_if_araddr           (gif_axil_araddr),
        .m_axil_if_arvalid          (gif_axil_arvalid),
        .m_axil_if_arready          (gif_axil_arready),
        .m_axil_if_rdata            (gif_axil_rdata),
        .m_axil_if_rresp            (gif_axil_rresp),
        .m_axil_if_rvalid           (gif_axil_rvalid),
        .m_axil_if_rready           (gif_axil_rready),
        // AXI4 data master → crossbar M2 (via gpu_m_* intermediates)
        .m_axi_araddr               (gpu_m_araddr),
        .m_axi_arvalid              (gpu_m_arvalid),
        .m_axi_arready              (gpu_m_arready),
        .m_axi_rdata                (gpu_m_rdata),
        .m_axi_rresp                (gpu_m_rresp),
        .m_axi_rvalid               (gpu_m_rvalid),
        .m_axi_rready               (gpu_m_rready),
        .m_axi_awaddr               (gpu_m_awaddr),
        .m_axi_awvalid              (gpu_m_awvalid),
        .m_axi_awready              (gpu_m_awready),
        .m_axi_wdata                (gpu_m_wdata),
        .m_axi_wstrb                (gpu_m_wstrb),
        .m_axi_wvalid               (gpu_m_wvalid),
        .m_axi_wready               (gpu_m_wready),
        .m_axi_bresp                (gpu_m_bresp),
        .m_axi_bvalid               (gpu_m_bvalid),
        .m_axi_bready               (gpu_m_bready),
        // IRQ
        .gpu_irq_o                  (gpu_irq_o)
    );
    // gpu_axil_* ↔ axil_s_*[AXIL_GPU] bridges
    assign gpu_axil_awaddr  = axil_s_awaddr  [AXIL_GPU][11:0];
    assign gpu_axil_awvalid = axil_s_awvalid [AXIL_GPU];
    assign axil_s_awready   [AXIL_GPU] = gpu_axil_awready;
    assign gpu_axil_wdata   = axil_s_wdata   [AXIL_GPU];
    assign gpu_axil_wstrb   = axil_s_wstrb   [AXIL_GPU];
    assign gpu_axil_wvalid  = axil_s_wvalid  [AXIL_GPU];
    assign axil_s_wready    [AXIL_GPU] = gpu_axil_wready;
    assign axil_s_bresp     [AXIL_GPU] = gpu_axil_bresp;
    assign axil_s_bvalid    [AXIL_GPU] = gpu_axil_bvalid;
    assign gpu_axil_bready  = axil_s_bready  [AXIL_GPU];
    assign gpu_axil_araddr  = axil_s_araddr  [AXIL_GPU][11:0];
    assign gpu_axil_arvalid = axil_s_arvalid [AXIL_GPU];
    assign axil_s_arready   [AXIL_GPU] = gpu_axil_arready;
    assign axil_s_rdata     [AXIL_GPU] = gpu_axil_rdata;
    assign axil_s_rresp     [AXIL_GPU] = gpu_axil_rresp;
    assign axil_s_rvalid    [AXIL_GPU] = gpu_axil_rvalid;
    assign gpu_axil_rready  = axil_s_rready  [AXIL_GPU];
    // gpu_m_* ↔ xbar_m_*[2] bridges
    assign xbar_m_araddr  [2] = gpu_m_araddr;
    assign xbar_m_arvalid [2] = gpu_m_arvalid;
    assign gpu_m_arready       = xbar_m_arready [2];
    assign gpu_m_rdata         = xbar_m_rdata   [2];
    assign gpu_m_rresp         = xbar_m_rresp   [2];
    assign gpu_m_rvalid        = xbar_m_rvalid  [2];
    assign xbar_m_rready  [2] = gpu_m_rready;
    assign xbar_m_awaddr  [2] = gpu_m_awaddr;
    assign xbar_m_awvalid [2] = gpu_m_awvalid;
    assign gpu_m_awready       = xbar_m_awready [2];
    assign xbar_m_wdata   [2] = gpu_m_wdata;
    assign xbar_m_wstrb   [2] = gpu_m_wstrb;
    assign xbar_m_wvalid  [2] = gpu_m_wvalid;
    assign gpu_m_wready        = xbar_m_wready  [2];
    assign gpu_m_bresp         = xbar_m_bresp   [2];
    assign gpu_m_bvalid        = xbar_m_bvalid  [2];
    assign xbar_m_bready  [2] = gpu_m_bready;

    // GPU AXI4 data master has no len/size/burst/last at gpu_top port level;
    // tie the crossbar's M2 burst fields to single-beat defaults.
    assign xbar_m_awlen   [2] = '0;
    assign xbar_m_awsize  [2] = AXI_SIZE_4B;
    assign xbar_m_awburst [2] = AXI_BURST_INCR;
    assign xbar_m_wlast   [2] = 1'b1;   // always last (single beat)
    assign xbar_m_arlen   [2] = '0;
    assign xbar_m_arsize  [2] = AXI_SIZE_4B;
    assign xbar_m_arburst [2] = AXI_BURST_INCR;

    // =========================================================================
    // M3: DMA engine (dma_engine) → crossbar M3 + interconnect AXIL_DMA
    // Intermediate wires: decouple xbar_m_*[3] and axil_s_*[AXIL_DMA] indexing.
    // =========================================================================
    // M3 master-bus intermediates
    logic [AW-1:0]   dma_m_awaddr;
    logic [LENW-1:0] dma_m_awlen;
    logic [2:0]      dma_m_awsize;
    logic [1:0]      dma_m_awburst;
    logic            dma_m_awvalid;
    logic            dma_m_awready;
    logic [DW-1:0]   dma_m_wdata;
    logic [SW-1:0]   dma_m_wstrb;
    logic            dma_m_wlast;
    logic            dma_m_wvalid;
    logic            dma_m_wready;
    logic [1:0]      dma_m_bresp;
    logic            dma_m_bvalid;
    logic            dma_m_bready;
    logic [AW-1:0]   dma_m_araddr;
    logic [LENW-1:0] dma_m_arlen;
    logic [2:0]      dma_m_arsize;
    logic [1:0]      dma_m_arburst;
    logic            dma_m_arvalid;
    logic            dma_m_arready;
    logic [DW-1:0]   dma_m_rdata;
    logic [1:0]      dma_m_rresp;
    logic            dma_m_rlast;
    logic            dma_m_rvalid;
    logic            dma_m_rready;
    // AXIL_DMA ctrl-slave intermediates
    logic [11:0]     dma_axil_awaddr;
    logic [2:0]      dma_axil_awprot;
    logic            dma_axil_awvalid;
    logic            dma_axil_awready;
    logic [DW-1:0]   dma_axil_wdata;
    logic [SW-1:0]   dma_axil_wstrb;
    logic            dma_axil_wvalid;
    logic            dma_axil_wready;
    logic [1:0]      dma_axil_bresp;
    logic            dma_axil_bvalid;
    logic            dma_axil_bready;
    logic [11:0]     dma_axil_araddr;
    logic [2:0]      dma_axil_arprot;
    logic            dma_axil_arvalid;
    logic            dma_axil_arready;
    logic [DW-1:0]   dma_axil_rdata;
    logic [1:0]      dma_axil_rresp;
    logic            dma_axil_rvalid;
    logic            dma_axil_rready;

    dma_engine #(
        .ADDR_W (12)
    ) u_dma (
        .clk                        (core_clk),
        .rst_n                      (core_rst_n),
        // AXI4-Lite ctrl slave ← interconnect AXIL_DMA slot (via dma_axil_* intermediates)
        .s_axil_awaddr              (dma_axil_awaddr),
        .s_axil_awprot              (dma_axil_awprot),
        .s_axil_awvalid             (dma_axil_awvalid),
        .s_axil_awready             (dma_axil_awready),
        .s_axil_wdata               (dma_axil_wdata),
        .s_axil_wstrb               (dma_axil_wstrb),
        .s_axil_wvalid              (dma_axil_wvalid),
        .s_axil_wready              (dma_axil_wready),
        .s_axil_bresp               (dma_axil_bresp),
        .s_axil_bvalid              (dma_axil_bvalid),
        .s_axil_bready              (dma_axil_bready),
        .s_axil_araddr              (dma_axil_araddr),
        .s_axil_arprot              (dma_axil_arprot),
        .s_axil_arvalid             (dma_axil_arvalid),
        .s_axil_arready             (dma_axil_arready),
        .s_axil_rdata               (dma_axil_rdata),
        .s_axil_rresp               (dma_axil_rresp),
        .s_axil_rvalid              (dma_axil_rvalid),
        .s_axil_rready              (dma_axil_rready),
        // AXI4 burst master → crossbar M3 (via dma_m_* intermediates)
        .m_awid                     (dma_axi_awid_unused),         // ID unused by crossbar (no-ID master port)
        .m_awaddr                   (dma_m_awaddr),
        .m_awlen                    (dma_m_awlen),
        .m_awsize                   (dma_m_awsize),
        .m_awburst                  (dma_m_awburst),
        .m_awvalid                  (dma_m_awvalid),
        .m_awready                  (dma_m_awready),
        .m_wdata                    (dma_m_wdata),
        .m_wstrb                    (dma_m_wstrb),
        .m_wlast                    (dma_m_wlast),
        .m_wvalid                   (dma_m_wvalid),
        .m_wready                   (dma_m_wready),
        .m_bid                      ('0),   // crossbar M-facing port has no bid
        .m_bresp                    (dma_m_bresp),
        .m_bvalid                   (dma_m_bvalid),
        .m_bready                   (dma_m_bready),
        .m_arid                     (dma_axi_arid_unused),         // ID unused by crossbar (no-ID master port)
        .m_araddr                   (dma_m_araddr),
        .m_arlen                    (dma_m_arlen),
        .m_arsize                   (dma_m_arsize),
        .m_arburst                  (dma_m_arburst),
        .m_arvalid                  (dma_m_arvalid),
        .m_arready                  (dma_m_arready),
        .m_rid                      ('0),   // crossbar M-facing port has no rid
        .m_rdata                    (dma_m_rdata),
        .m_rresp                    (dma_m_rresp),
        .m_rlast                    (dma_m_rlast),
        .m_rvalid                   (dma_m_rvalid),
        .m_rready                   (dma_m_rready),
        // IRQ
        .irq_o                      (dma_irq)
    );
    // dma_axil_* ↔ axil_s_*[AXIL_DMA] bridges
    assign dma_axil_awaddr  = axil_s_awaddr  [AXIL_DMA][11:0];
    assign dma_axil_awprot  = axil_s_awprot  [AXIL_DMA];
    assign dma_axil_awvalid = axil_s_awvalid [AXIL_DMA];
    assign axil_s_awready   [AXIL_DMA] = dma_axil_awready;
    assign dma_axil_wdata   = axil_s_wdata   [AXIL_DMA];
    assign dma_axil_wstrb   = axil_s_wstrb   [AXIL_DMA];
    assign dma_axil_wvalid  = axil_s_wvalid  [AXIL_DMA];
    assign axil_s_wready    [AXIL_DMA] = dma_axil_wready;
    assign axil_s_bresp     [AXIL_DMA] = dma_axil_bresp;
    assign axil_s_bvalid    [AXIL_DMA] = dma_axil_bvalid;
    assign dma_axil_bready  = axil_s_bready  [AXIL_DMA];
    assign dma_axil_araddr  = axil_s_araddr  [AXIL_DMA][11:0];
    assign dma_axil_arprot  = axil_s_arprot  [AXIL_DMA];
    assign dma_axil_arvalid = axil_s_arvalid [AXIL_DMA];
    assign axil_s_arready   [AXIL_DMA] = dma_axil_arready;
    assign axil_s_rdata     [AXIL_DMA] = dma_axil_rdata;
    assign axil_s_rresp     [AXIL_DMA] = dma_axil_rresp;
    assign axil_s_rvalid    [AXIL_DMA] = dma_axil_rvalid;
    assign dma_axil_rready  = axil_s_rready  [AXIL_DMA];
    // dma_m_* ↔ xbar_m_*[3] bridges
    assign xbar_m_awaddr  [3] = dma_m_awaddr;
    assign xbar_m_awlen   [3] = dma_m_awlen;
    assign xbar_m_awsize  [3] = dma_m_awsize;
    assign xbar_m_awburst [3] = dma_m_awburst;
    assign xbar_m_awvalid [3] = dma_m_awvalid;
    assign dma_m_awready       = xbar_m_awready [3];
    assign xbar_m_wdata   [3] = dma_m_wdata;
    assign xbar_m_wstrb   [3] = dma_m_wstrb;
    assign xbar_m_wlast   [3] = dma_m_wlast;
    assign xbar_m_wvalid  [3] = dma_m_wvalid;
    assign dma_m_wready        = xbar_m_wready  [3];
    assign dma_m_bresp         = xbar_m_bresp   [3];
    assign dma_m_bvalid        = xbar_m_bvalid  [3];
    assign xbar_m_bready  [3] = dma_m_bready;
    assign xbar_m_araddr  [3] = dma_m_araddr;
    assign xbar_m_arlen   [3] = dma_m_arlen;
    assign xbar_m_arsize  [3] = dma_m_arsize;
    assign xbar_m_arburst [3] = dma_m_arburst;
    assign xbar_m_arvalid [3] = dma_m_arvalid;
    assign dma_m_arready       = xbar_m_arready [3];
    assign dma_m_rdata         = xbar_m_rdata   [3];
    assign dma_m_rresp         = xbar_m_rresp   [3];
    assign dma_m_rlast         = xbar_m_rlast   [3];
    assign dma_m_rvalid        = xbar_m_rvalid  [3];
    assign xbar_m_rready  [3] = dma_m_rready;

    // =========================================================================
    // AXI4 crossbar
    // =========================================================================
    axi4_crossbar #(
        .N_MASTERS  (N_MASTERS),
        .N_SLAVES   (N_SLAVES),
        .AW         (AW),
        .DW         (DW),
        .SW         (SW),
        .IW         (IW),
        .LENW       (LENW),
        .SLV_BASE   (SOC_SLV_BASE),
        .SLV_LIMIT  (SOC_SLV_LIMIT)
    ) u_xbar (
        .clk        (core_clk),
        .rst_n      (core_rst_n),
        // Master-facing ports
        .m_awaddr   (xbar_m_awaddr),
        .m_awlen    (xbar_m_awlen),
        .m_awsize   (xbar_m_awsize),
        .m_awburst  (xbar_m_awburst),
        .m_awvalid  (xbar_m_awvalid),
        .m_awready  (xbar_m_awready),
        .m_wdata    (xbar_m_wdata),
        .m_wstrb    (xbar_m_wstrb),
        .m_wlast    (xbar_m_wlast),
        .m_wvalid   (xbar_m_wvalid),
        .m_wready   (xbar_m_wready),
        .m_bresp    (xbar_m_bresp),
        .m_bvalid   (xbar_m_bvalid),
        .m_bready   (xbar_m_bready),
        .m_araddr   (xbar_m_araddr),
        .m_arlen    (xbar_m_arlen),
        .m_arsize   (xbar_m_arsize),
        .m_arburst  (xbar_m_arburst),
        .m_arvalid  (xbar_m_arvalid),
        .m_arready  (xbar_m_arready),
        .m_rdata    (xbar_m_rdata),
        .m_rresp    (xbar_m_rresp),
        .m_rlast    (xbar_m_rlast),
        .m_rvalid   (xbar_m_rvalid),
        .m_rready   (xbar_m_rready),
        // Slave-facing ports
        .s_awid     (xbar_s_awid),
        .s_awaddr   (xbar_s_awaddr),
        .s_awlen    (xbar_s_awlen),
        .s_awsize   (xbar_s_awsize),
        .s_awburst  (xbar_s_awburst),
        .s_awvalid  (xbar_s_awvalid),
        .s_awready  (xbar_s_awready),
        .s_wdata    (xbar_s_wdata),
        .s_wstrb    (xbar_s_wstrb),
        .s_wlast    (xbar_s_wlast),
        .s_wvalid   (xbar_s_wvalid),
        .s_wready   (xbar_s_wready),
        .s_bid      (xbar_s_bid),
        .s_bresp    (xbar_s_bresp),
        .s_bvalid   (xbar_s_bvalid),
        .s_bready   (xbar_s_bready),
        .s_arid     (xbar_s_arid),
        .s_araddr   (xbar_s_araddr),
        .s_arlen    (xbar_s_arlen),
        .s_arsize   (xbar_s_arsize),
        .s_arburst  (xbar_s_arburst),
        .s_arvalid  (xbar_s_arvalid),
        .s_arready  (xbar_s_arready),
        .s_rid      (xbar_s_rid),
        .s_rdata    (xbar_s_rdata),
        .s_rresp    (xbar_s_rresp),
        .s_rlast    (xbar_s_rlast),
        .s_rvalid   (xbar_s_rvalid),
        .s_rready   (xbar_s_rready)
    );

    // =========================================================================
    // S0: Boot ROM (boot_rom) ← crossbar SLV_ROM
    // Intermediate wires: decouple xbar_s_*[SLV_ROM] indexing.
    // =========================================================================
    logic [IW-1:0]   rom_s_awid;
    logic [AW-1:0]   rom_s_awaddr;
    logic [LENW-1:0] rom_s_awlen;
    logic [2:0]      rom_s_awsize;
    logic [1:0]      rom_s_awburst;
    logic            rom_s_awvalid;
    logic            rom_s_awready;
    logic [DW-1:0]   rom_s_wdata;
    logic [SW-1:0]   rom_s_wstrb;
    logic            rom_s_wlast;
    logic            rom_s_wvalid;
    logic            rom_s_wready;
    logic [IW-1:0]   rom_s_bid;
    logic [1:0]      rom_s_bresp;
    logic            rom_s_bvalid;
    logic            rom_s_bready;
    logic [IW-1:0]   rom_s_arid;
    logic [AW-1:0]   rom_s_araddr;
    logic [LENW-1:0] rom_s_arlen;
    logic [2:0]      rom_s_arsize;
    logic [1:0]      rom_s_arburst;
    logic            rom_s_arvalid;
    logic            rom_s_arready;
    logic [IW-1:0]   rom_s_rid;
    logic [DW-1:0]   rom_s_rdata;
    logic [1:0]      rom_s_rresp;
    logic            rom_s_rlast;
    logic            rom_s_rvalid;
    logic            rom_s_rready;

    boot_rom #(
        .MEM_WORDS    (1024),
        .MEM_INIT_FILE(MEM_INIT_FILE)
    ) u_boot_rom (
        .clk          (core_clk),
        .rst_n        (core_rst_n),
        .s_awid       (rom_s_awid),
        .s_awaddr     (rom_s_awaddr),
        .s_awlen      (rom_s_awlen),
        .s_awsize     (rom_s_awsize),
        .s_awburst    (rom_s_awburst),
        .s_awvalid    (rom_s_awvalid),
        .s_awready    (rom_s_awready),
        .s_wdata      (rom_s_wdata),
        .s_wstrb      (rom_s_wstrb),
        .s_wlast      (rom_s_wlast),
        .s_wvalid     (rom_s_wvalid),
        .s_wready     (rom_s_wready),
        .s_bid        (rom_s_bid),
        .s_bresp      (rom_s_bresp),
        .s_bvalid     (rom_s_bvalid),
        .s_bready     (rom_s_bready),
        .s_arid       (rom_s_arid),
        .s_araddr     (rom_s_araddr),
        .s_arlen      (rom_s_arlen),
        .s_arsize     (rom_s_arsize),
        .s_arburst    (rom_s_arburst),
        .s_arvalid    (rom_s_arvalid),
        .s_arready    (rom_s_arready),
        .s_rid        (rom_s_rid),
        .s_rdata      (rom_s_rdata),
        .s_rresp      (rom_s_rresp),
        .s_rlast      (rom_s_rlast),
        .s_rvalid     (rom_s_rvalid),
        .s_rready     (rom_s_rready)
    );
    // xbar_s_*[SLV_ROM] ↔ rom_s_* bridges
    assign rom_s_awid       = xbar_s_awid    [SLV_ROM];
    assign rom_s_awaddr     = xbar_s_awaddr  [SLV_ROM];
    assign rom_s_awlen      = xbar_s_awlen   [SLV_ROM];
    assign rom_s_awsize     = xbar_s_awsize  [SLV_ROM];
    assign rom_s_awburst    = xbar_s_awburst [SLV_ROM];
    assign rom_s_awvalid    = xbar_s_awvalid [SLV_ROM];
    assign xbar_s_awready   [SLV_ROM] = rom_s_awready;
    assign rom_s_wdata      = xbar_s_wdata   [SLV_ROM];
    assign rom_s_wstrb      = xbar_s_wstrb   [SLV_ROM];
    assign rom_s_wlast      = xbar_s_wlast   [SLV_ROM];
    assign rom_s_wvalid     = xbar_s_wvalid  [SLV_ROM];
    assign xbar_s_wready    [SLV_ROM] = rom_s_wready;
    assign xbar_s_bid       [SLV_ROM] = rom_s_bid;
    assign xbar_s_bresp     [SLV_ROM] = rom_s_bresp;
    assign xbar_s_bvalid    [SLV_ROM] = rom_s_bvalid;
    assign rom_s_bready     = xbar_s_bready  [SLV_ROM];
    assign rom_s_arid       = xbar_s_arid    [SLV_ROM];
    assign rom_s_araddr     = xbar_s_araddr  [SLV_ROM];
    assign rom_s_arlen      = xbar_s_arlen   [SLV_ROM];
    assign rom_s_arsize     = xbar_s_arsize  [SLV_ROM];
    assign rom_s_arburst    = xbar_s_arburst [SLV_ROM];
    assign rom_s_arvalid    = xbar_s_arvalid [SLV_ROM];
    assign xbar_s_arready   [SLV_ROM] = rom_s_arready;
    assign xbar_s_rid       [SLV_ROM] = rom_s_rid;
    assign xbar_s_rdata     [SLV_ROM] = rom_s_rdata;
    assign xbar_s_rresp     [SLV_ROM] = rom_s_rresp;
    assign xbar_s_rlast     [SLV_ROM] = rom_s_rlast;
    assign xbar_s_rvalid    [SLV_ROM] = rom_s_rvalid;
    assign rom_s_rready     = xbar_s_rready  [SLV_ROM];

    // =========================================================================
    // S1: SRAM controller (sram_controller) ← crossbar SLV_SRAM
    // Intermediate wires: decouple xbar_s_*[SLV_SRAM] indexing.
    // =========================================================================
    logic [IW-1:0]   sram_s_awid;
    logic [AW-1:0]   sram_s_awaddr;
    logic [LENW-1:0] sram_s_awlen;
    logic [2:0]      sram_s_awsize;
    logic [1:0]      sram_s_awburst;
    logic            sram_s_awvalid;
    logic            sram_s_awready;
    logic [DW-1:0]   sram_s_wdata;
    logic [SW-1:0]   sram_s_wstrb;
    logic            sram_s_wlast;
    logic            sram_s_wvalid;
    logic            sram_s_wready;
    logic [IW-1:0]   sram_s_bid;
    logic [1:0]      sram_s_bresp;
    logic            sram_s_bvalid;
    logic            sram_s_bready;
    logic [IW-1:0]   sram_s_arid;
    logic [AW-1:0]   sram_s_araddr;
    logic [LENW-1:0] sram_s_arlen;
    logic [2:0]      sram_s_arsize;
    logic [1:0]      sram_s_arburst;
    logic            sram_s_arvalid;
    logic            sram_s_arready;
    logic [IW-1:0]   sram_s_rid;
    logic [DW-1:0]   sram_s_rdata;
    logic [1:0]      sram_s_rresp;
    logic            sram_s_rlast;
    logic            sram_s_rvalid;
    logic            sram_s_rready;

    sram_controller #(
        .MEM_WORDS    (SRAM_MEM_WORDS)
    ) u_sram (
        .clk          (core_clk),
        .rst_n        (core_rst_n),
        .s_awid       (sram_s_awid),
        .s_awaddr     (sram_s_awaddr),
        .s_awlen      (sram_s_awlen),
        .s_awsize     (sram_s_awsize),
        .s_awburst    (sram_s_awburst),
        .s_awvalid    (sram_s_awvalid),
        .s_awready    (sram_s_awready),
        .s_wdata      (sram_s_wdata),
        .s_wstrb      (sram_s_wstrb),
        .s_wlast      (sram_s_wlast),
        .s_wvalid     (sram_s_wvalid),
        .s_wready     (sram_s_wready),
        .s_bid        (sram_s_bid),
        .s_bresp      (sram_s_bresp),
        .s_bvalid     (sram_s_bvalid),
        .s_bready     (sram_s_bready),
        .s_arid       (sram_s_arid),
        .s_araddr     (sram_s_araddr),
        .s_arlen      (sram_s_arlen),
        .s_arsize     (sram_s_arsize),
        .s_arburst    (sram_s_arburst),
        .s_arvalid    (sram_s_arvalid),
        .s_arready    (sram_s_arready),
        .s_rid        (sram_s_rid),
        .s_rdata      (sram_s_rdata),
        .s_rresp      (sram_s_rresp),
        .s_rlast      (sram_s_rlast),
        .s_rvalid     (sram_s_rvalid),
        .s_rready     (sram_s_rready)
    );
    // xbar_s_*[SLV_SRAM] ↔ sram_s_* bridges
    assign sram_s_awid      = xbar_s_awid    [SLV_SRAM];
    assign sram_s_awaddr    = xbar_s_awaddr  [SLV_SRAM];
    assign sram_s_awlen     = xbar_s_awlen   [SLV_SRAM];
    assign sram_s_awsize    = xbar_s_awsize  [SLV_SRAM];
    assign sram_s_awburst   = xbar_s_awburst [SLV_SRAM];
    assign sram_s_awvalid   = xbar_s_awvalid [SLV_SRAM];
    assign xbar_s_awready   [SLV_SRAM] = sram_s_awready;
    assign sram_s_wdata     = xbar_s_wdata   [SLV_SRAM];
    assign sram_s_wstrb     = xbar_s_wstrb   [SLV_SRAM];
    assign sram_s_wlast     = xbar_s_wlast   [SLV_SRAM];
    assign sram_s_wvalid    = xbar_s_wvalid  [SLV_SRAM];
    assign xbar_s_wready    [SLV_SRAM] = sram_s_wready;
    assign xbar_s_bid       [SLV_SRAM] = sram_s_bid;
    assign xbar_s_bresp     [SLV_SRAM] = sram_s_bresp;
    assign xbar_s_bvalid    [SLV_SRAM] = sram_s_bvalid;
    assign sram_s_bready    = xbar_s_bready  [SLV_SRAM];
    assign sram_s_arid      = xbar_s_arid    [SLV_SRAM];
    assign sram_s_araddr    = xbar_s_araddr  [SLV_SRAM];
    assign sram_s_arlen     = xbar_s_arlen   [SLV_SRAM];
    assign sram_s_arsize    = xbar_s_arsize  [SLV_SRAM];
    assign sram_s_arburst   = xbar_s_arburst [SLV_SRAM];
    assign sram_s_arvalid   = xbar_s_arvalid [SLV_SRAM];
    assign xbar_s_arready   [SLV_SRAM] = sram_s_arready;
    assign xbar_s_rid       [SLV_SRAM] = sram_s_rid;
    assign xbar_s_rdata     [SLV_SRAM] = sram_s_rdata;
    assign xbar_s_rresp     [SLV_SRAM] = sram_s_rresp;
    assign xbar_s_rlast     [SLV_SRAM] = sram_s_rlast;
    assign xbar_s_rvalid    [SLV_SRAM] = sram_s_rvalid;
    assign sram_s_rready    = xbar_s_rready  [SLV_SRAM];

    // =========================================================================
    // S2: axi4_to_axilite bridge ← crossbar SLV_PERIPH → interconnect master
    // Intermediate wires: decouple xbar_s_*[SLV_PERIPH] indexing.
    // =========================================================================
    logic [IW-1:0]   periph_s_awid;
    logic [AW-1:0]   periph_s_awaddr;
    logic [LENW-1:0] periph_s_awlen;
    logic [2:0]      periph_s_awsize;
    logic [1:0]      periph_s_awburst;
    logic            periph_s_awvalid;
    logic            periph_s_awready;
    logic [DW-1:0]   periph_s_wdata;
    logic [SW-1:0]   periph_s_wstrb;
    logic            periph_s_wlast;
    logic            periph_s_wvalid;
    logic            periph_s_wready;
    logic [IW-1:0]   periph_s_bid;
    logic [1:0]      periph_s_bresp;
    logic            periph_s_bvalid;
    logic            periph_s_bready;
    logic [IW-1:0]   periph_s_arid;
    logic [AW-1:0]   periph_s_araddr;
    logic [LENW-1:0] periph_s_arlen;
    logic [2:0]      periph_s_arsize;
    logic [1:0]      periph_s_arburst;
    logic            periph_s_arvalid;
    logic            periph_s_arready;
    logic [IW-1:0]   periph_s_rid;
    logic [DW-1:0]   periph_s_rdata;
    logic [1:0]      periph_s_rresp;
    logic            periph_s_rlast;
    logic            periph_s_rvalid;
    logic            periph_s_rready;

    axi4_to_axilite u_periph_bridge (
        .clk                        (core_clk),
        .rst_n                      (core_rst_n),
        // AXI4 slave ← crossbar SLV_PERIPH (via periph_s_* intermediates)
        .s_awid                     (periph_s_awid),
        .s_awaddr                   (periph_s_awaddr),
        .s_awlen                    (periph_s_awlen),
        .s_awsize                   (periph_s_awsize),
        .s_awburst                  (periph_s_awburst),
        .s_awvalid                  (periph_s_awvalid),
        .s_awready                  (periph_s_awready),
        .s_wdata                    (periph_s_wdata),
        .s_wstrb                    (periph_s_wstrb),
        .s_wlast                    (periph_s_wlast),
        .s_wvalid                   (periph_s_wvalid),
        .s_wready                   (periph_s_wready),
        .s_bid                      (periph_s_bid),
        .s_bresp                    (periph_s_bresp),
        .s_bvalid                   (periph_s_bvalid),
        .s_bready                   (periph_s_bready),
        .s_arid                     (periph_s_arid),
        .s_araddr                   (periph_s_araddr),
        .s_arlen                    (periph_s_arlen),
        .s_arsize                   (periph_s_arsize),
        .s_arburst                  (periph_s_arburst),
        .s_arvalid                  (periph_s_arvalid),
        .s_arready                  (periph_s_arready),
        .s_rid                      (periph_s_rid),
        .s_rdata                    (periph_s_rdata),
        .s_rresp                    (periph_s_rresp),
        .s_rlast                    (periph_s_rlast),
        .s_rvalid                   (periph_s_rvalid),
        .s_rready                   (periph_s_rready),
        // AXI4-Lite master → axi_lite_interconnect
        .m_axil_awaddr              (periph_axil_awaddr),
        .m_axil_awprot              (periph_axil_awprot),
        .m_axil_awvalid             (periph_axil_awvalid),
        .m_axil_awready             (periph_axil_awready),
        .m_axil_wdata               (periph_axil_wdata),
        .m_axil_wstrb               (periph_axil_wstrb),
        .m_axil_wvalid              (periph_axil_wvalid),
        .m_axil_wready              (periph_axil_wready),
        .m_axil_bresp               (periph_axil_bresp),
        .m_axil_bvalid              (periph_axil_bvalid),
        .m_axil_bready              (periph_axil_bready),
        .m_axil_araddr              (periph_axil_araddr),
        .m_axil_arprot              (periph_axil_arprot),
        .m_axil_arvalid             (periph_axil_arvalid),
        .m_axil_arready             (periph_axil_arready),
        .m_axil_rdata               (periph_axil_rdata),
        .m_axil_rresp               (periph_axil_rresp),
        .m_axil_rvalid              (periph_axil_rvalid),
        .m_axil_rready              (periph_axil_rready)
    );
    // xbar_s_*[SLV_PERIPH] ↔ periph_s_* bridges
    assign periph_s_awid    = xbar_s_awid    [SLV_PERIPH];
    assign periph_s_awaddr  = xbar_s_awaddr  [SLV_PERIPH];
    assign periph_s_awlen   = xbar_s_awlen   [SLV_PERIPH];
    assign periph_s_awsize  = xbar_s_awsize  [SLV_PERIPH];
    assign periph_s_awburst = xbar_s_awburst [SLV_PERIPH];
    assign periph_s_awvalid = xbar_s_awvalid [SLV_PERIPH];
    assign xbar_s_awready   [SLV_PERIPH] = periph_s_awready;
    assign periph_s_wdata   = xbar_s_wdata   [SLV_PERIPH];
    assign periph_s_wstrb   = xbar_s_wstrb   [SLV_PERIPH];
    assign periph_s_wlast   = xbar_s_wlast   [SLV_PERIPH];
    assign periph_s_wvalid  = xbar_s_wvalid  [SLV_PERIPH];
    assign xbar_s_wready    [SLV_PERIPH] = periph_s_wready;
    assign xbar_s_bid       [SLV_PERIPH] = periph_s_bid;
    assign xbar_s_bresp     [SLV_PERIPH] = periph_s_bresp;
    assign xbar_s_bvalid    [SLV_PERIPH] = periph_s_bvalid;
    assign periph_s_bready  = xbar_s_bready  [SLV_PERIPH];
    assign periph_s_arid    = xbar_s_arid    [SLV_PERIPH];
    assign periph_s_araddr  = xbar_s_araddr  [SLV_PERIPH];
    assign periph_s_arlen   = xbar_s_arlen   [SLV_PERIPH];
    assign periph_s_arsize  = xbar_s_arsize  [SLV_PERIPH];
    assign periph_s_arburst = xbar_s_arburst [SLV_PERIPH];
    assign periph_s_arvalid = xbar_s_arvalid [SLV_PERIPH];
    assign xbar_s_arready   [SLV_PERIPH] = periph_s_arready;
    assign xbar_s_rid       [SLV_PERIPH] = periph_s_rid;
    assign xbar_s_rdata     [SLV_PERIPH] = periph_s_rdata;
    assign xbar_s_rresp     [SLV_PERIPH] = periph_s_rresp;
    assign xbar_s_rlast     [SLV_PERIPH] = periph_s_rlast;
    assign xbar_s_rvalid    [SLV_PERIPH] = periph_s_rvalid;
    assign periph_s_rready  = xbar_s_rready  [SLV_PERIPH];

    // =========================================================================
    // AXI4-Lite interconnect (1 master → 3 ring slaves: GPU, APB_BRIDGE, DMA)
    // =========================================================================
    axi_lite_interconnect #(
        .N_SLAVES   (N_AXIL_SLV),
        .SLV_BASE   (AXIL_SLV_BASE),
        .SLV_LIMIT  (AXIL_SLV_LIMIT)
    ) u_axil_ic (
        .clk                (core_clk),
        .rst_n              (core_rst_n),
        // Master-facing port (from axi4_to_axilite bridge)
        .m_axil_awaddr      (periph_axil_awaddr),
        .m_axil_awprot      (periph_axil_awprot),
        .m_axil_awvalid     (periph_axil_awvalid),
        .m_axil_awready     (periph_axil_awready),
        .m_axil_wdata       (periph_axil_wdata),
        .m_axil_wstrb       (periph_axil_wstrb),
        .m_axil_wvalid      (periph_axil_wvalid),
        .m_axil_wready      (periph_axil_wready),
        .m_axil_bresp       (periph_axil_bresp),
        .m_axil_bvalid      (periph_axil_bvalid),
        .m_axil_bready      (periph_axil_bready),
        .m_axil_araddr      (periph_axil_araddr),
        .m_axil_arprot      (periph_axil_arprot),
        .m_axil_arvalid     (periph_axil_arvalid),
        .m_axil_arready     (periph_axil_arready),
        .m_axil_rdata       (periph_axil_rdata),
        .m_axil_rresp       (periph_axil_rresp),
        .m_axil_rvalid      (periph_axil_rvalid),
        .m_axil_rready      (periph_axil_rready),
        // Slave-facing ports (GPU, APB_BRIDGE, DMA)
        .s_axil_awaddr      (axil_s_awaddr),
        .s_axil_awprot      (axil_s_awprot),
        .s_axil_awvalid     (axil_s_awvalid),
        .s_axil_awready     (axil_s_awready),
        .s_axil_wdata       (axil_s_wdata),
        .s_axil_wstrb       (axil_s_wstrb),
        .s_axil_wvalid      (axil_s_wvalid),
        .s_axil_wready      (axil_s_wready),
        .s_axil_bresp       (axil_s_bresp),
        .s_axil_bvalid      (axil_s_bvalid),
        .s_axil_bready      (axil_s_bready),
        .s_axil_araddr      (axil_s_araddr),
        .s_axil_arprot      (axil_s_arprot),
        .s_axil_arvalid     (axil_s_arvalid),
        .s_axil_arready     (axil_s_arready),
        .s_axil_rdata       (axil_s_rdata),
        .s_axil_rresp       (axil_s_rresp),
        .s_axil_rvalid      (axil_s_rvalid),
        .s_axil_rready      (axil_s_rready)
    );

    // =========================================================================
    // AXIL_APB_BRIDGE: axil_to_apb bridge (axil_s[AXIL_APB_BRIDGE])
    // Converts AXI-Lite ring slot 1 to APB master for the peripheral subtree.
    // =========================================================================
    axil_to_apb #(
        .ADDR_W (32),
        .DW     (32),
        .SW     (4)
    ) u_axil_apb_bridge (
        .clk            (core_clk),
        .rst_n          (core_rst_n),
        // AXI-Lite slave ← ring AXIL_APB_BRIDGE slot
        .s_axil_awaddr  (axil_s_awaddr  [AXIL_APB_BRIDGE]),
        .s_axil_awprot  (axil_s_awprot  [AXIL_APB_BRIDGE]),
        .s_axil_awvalid (axil_s_awvalid [AXIL_APB_BRIDGE]),
        .s_axil_awready (axil_s_awready [AXIL_APB_BRIDGE]),
        .s_axil_wdata   (axil_s_wdata   [AXIL_APB_BRIDGE]),
        .s_axil_wstrb   (axil_s_wstrb   [AXIL_APB_BRIDGE]),
        .s_axil_wvalid  (axil_s_wvalid  [AXIL_APB_BRIDGE]),
        .s_axil_wready  (axil_s_wready  [AXIL_APB_BRIDGE]),
        .s_axil_bresp   (axil_s_bresp   [AXIL_APB_BRIDGE]),
        .s_axil_bvalid  (axil_s_bvalid  [AXIL_APB_BRIDGE]),
        .s_axil_bready  (axil_s_bready  [AXIL_APB_BRIDGE]),
        .s_axil_araddr  (axil_s_araddr  [AXIL_APB_BRIDGE]),
        .s_axil_arprot  (axil_s_arprot  [AXIL_APB_BRIDGE]),
        .s_axil_arvalid (axil_s_arvalid [AXIL_APB_BRIDGE]),
        .s_axil_arready (axil_s_arready [AXIL_APB_BRIDGE]),
        .s_axil_rdata   (axil_s_rdata   [AXIL_APB_BRIDGE]),
        .s_axil_rresp   (axil_s_rresp   [AXIL_APB_BRIDGE]),
        .s_axil_rvalid  (axil_s_rvalid  [AXIL_APB_BRIDGE]),
        .s_axil_rready  (axil_s_rready  [AXIL_APB_BRIDGE]),
        // APB4 master → apb_interconnect
        .psel           (apb_m_psel),
        .penable        (apb_m_penable),
        .pwrite         (apb_m_pwrite),
        .paddr          (apb_m_paddr),
        .pwdata         (apb_m_pwdata),
        .pstrb          (apb_m_pstrb),
        .prdata         (apb_m_prdata),
        .pready         (apb_m_pready),
        .pslverr        (apb_m_pslverr)
    );

    // =========================================================================
    // APB interconnect: 1 APB master → 5 APB peripheral slaves
    //   APB_UART=0 APB_SPI=1 APB_TIMER=2 APB_IRQ=3 APB_PLL=4
    // =========================================================================
    apb_interconnect #(
        .N_SLAVES  (N_APB_SLV),
        .ADDR_W    (32),
        .DW        (32),
        .SW        (4),
        .SLV_BASE  (APB_SLV_BASE),
        .SLV_LIMIT (APB_SLV_LIMIT)
    ) u_apb_ic (
        .psel_i    (apb_m_psel),
        .penable_i (apb_m_penable),
        .pwrite_i  (apb_m_pwrite),
        .paddr_i   (apb_m_paddr),
        .pwdata_i  (apb_m_pwdata),
        .pstrb_i   (apb_m_pstrb),
        .prdata_o  (apb_m_prdata),
        .pready_o  (apb_m_pready),
        .pslverr_o (apb_m_pslverr),
        .psel_o    (apb_psel),
        .penable_o (apb_penable),
        .pwrite_o  (apb_pwrite),
        .paddr_o   (apb_paddr),
        .pwdata_o  (apb_pwdata),
        .pstrb_o   (apb_pstrb),
        .prdata_i  (apb_prdata),
        .pready_i  (apb_pready),
        .pslverr_i (apb_pslverr)
    );

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
    // Phase 7 M-c: PLL clock generator + APB config slave
    // =========================================================================
    // pll_clkgen: selects STUB (default, synth-safe) or RNM (M-c cosim)
    // via PLL_IMPL parameter.  clk_i is the 100 MHz reference; core_clk is
    // the generated clock that feeds all children (see clock seam section).
    // =========================================================================
    pll_clkgen #(
        .PLL_IMPL        (PLL_IMPL)
    ) u_pll (
        .ref_clk_i   (clk_i),
        .rst_n_i     (pll_rst_n),
        .feedback_div(pll_fb_div),
        .post_div_sel(pll_post_div),
        .out_clk_o   (core_clk),
        .locked_o    (pll_locked)
    );

    // =========================================================================
    // APB_PLL (apb_psel[APB_PLL]): PLL APB config slave
    //
    // IMPORTANT — clock-domain intent:
    //   u_pll_regs and u_pll (pll_clkgen) are the SOURCE of core_clk and
    //   pll_locked.  They MUST run on the reference clock (clk_i / rst_n_i),
    //   NOT on core_clk / core_rst_n.  Placing them on core_clk would create
    //   a bootstrap deadlock: core_rst_n requires pll_locked, pll_locked
    //   requires pll_enable=1, pll_enable comes from pll_apb_regs CONTROL[0],
    //   but pll_apb_regs would be held in reset (core_rst_n=0) forever.
    //
    //   STUB mode (PLL_IMPL="STUB"):
    //     out_clk_o = ref_clk_i, so core_clk == clk_i.  No CDC issue — the
    //     apb_interconnect (running on core_clk) and u_pll_regs (running on
    //     clk_i) are in the same physical clock domain.
    //
    //   RNM mode (PLL_IMPL="RNM"):
    //     core_clk != clk_i.  The apb_interconnect runs on core_clk while
    //     u_pll_regs runs on clk_i (ref clock).  The apb_psel[APB_PLL] bus
    //     therefore crosses a CDC boundary.  A 2-FF synchroniser (or async
    //     handshake) on each valid/ready signal would be required for
    //     production-quality closure.  Deferred to Phase 7 M-d / tape-out.
    //     Do NOT remove this comment without adding the synchroniser.
    // =========================================================================
    pll_apb_regs #(
        .ADDR_W (12)
    ) u_pll_regs (
        // Run on reference clock — NOT core_clk — to avoid bootstrap deadlock.
        // See clock-domain note above.
        .clk_i       (clk_i),
        .rst_n_i     (rst_n_i),
        // APB4 slave ← apb_interconnect APB_PLL slot
        .psel        (apb_psel    [APB_PLL]),
        .penable     (apb_penable [APB_PLL]),
        .pwrite      (apb_pwrite  [APB_PLL]),
        .paddr       (apb_paddr   [APB_PLL][11:0]),
        .pwdata      (apb_pwdata  [APB_PLL]),
        .pstrb       (apb_pstrb   [APB_PLL]),
        .prdata      (apb_prdata  [APB_PLL]),
        .pready      (apb_pready  [APB_PLL]),
        .pslverr     (apb_pslverr [APB_PLL]),
        // PLL config outputs → pll_clkgen inputs
        .pll_enable_o   (pll_enable),
        .feedback_div_o (pll_fb_div),
        .post_div_sel_o (pll_post_div),
        // PLL status input ← pll_clkgen locked_o
        .pll_locked_i   (pll_locked)
    );

endmodule : soc_top
