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
    parameter string MEM_INIT_FILE = "",

    // PLL implementation selector (Phase 7 M-c).
    //   "STUB" (default) — synthesisable digital stub; out_clk = ref_clk.
    //   "RNM"            — real-number model; use only for M-c AMS co-sim.
    parameter string PLL_IMPL = "STUB"
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
    // pll_axil_regs drives pll_enable, feedback_div, post_div_sel; PLL rst_n
    // is gated by pll_enable so firmware can keep the PLL in reset on boot.
    // =========================================================================
    logic       core_clk;       // PLL output clock — feeds all child clk ports
    logic       core_rst_n;     // gated reset: rst_n_i & pll_locked
    logic       pll_locked;     // raw PLL lock flag

    // PLL config signals driven by pll_axil_regs
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
    // Crossbar master-facing nets (no ID, unpacked arrays [N_MASTERS])
    // =========================================================================
    // Write address
    logic [AW-1:0]   xbar_m_awaddr  [N_MASTERS];
    logic [LENW-1:0] xbar_m_awlen   [N_MASTERS];
    logic [2:0]      xbar_m_awsize  [N_MASTERS];
    logic [1:0]      xbar_m_awburst [N_MASTERS];
    logic            xbar_m_awvalid [N_MASTERS];
    logic            xbar_m_awready [N_MASTERS];
    // Write data
    logic [DW-1:0]   xbar_m_wdata   [N_MASTERS];
    logic [SW-1:0]   xbar_m_wstrb   [N_MASTERS];
    logic            xbar_m_wlast   [N_MASTERS];
    logic            xbar_m_wvalid  [N_MASTERS];
    logic            xbar_m_wready  [N_MASTERS];
    // Write response
    logic [1:0]      xbar_m_bresp   [N_MASTERS];
    logic            xbar_m_bvalid  [N_MASTERS];
    logic            xbar_m_bready  [N_MASTERS];
    // Read address
    logic [AW-1:0]   xbar_m_araddr  [N_MASTERS];
    logic [LENW-1:0] xbar_m_arlen   [N_MASTERS];
    logic [2:0]      xbar_m_arsize  [N_MASTERS];
    logic [1:0]      xbar_m_arburst [N_MASTERS];
    logic            xbar_m_arvalid [N_MASTERS];
    logic            xbar_m_arready [N_MASTERS];
    // Read data
    logic [DW-1:0]   xbar_m_rdata   [N_MASTERS];
    logic [1:0]      xbar_m_rresp   [N_MASTERS];
    logic            xbar_m_rlast   [N_MASTERS];
    logic            xbar_m_rvalid  [N_MASTERS];
    logic            xbar_m_rready  [N_MASTERS];

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
    localparam int unsigned N_APB_SLV = APB_N_SLAVES; // 5

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
        .clk_i                      (core_clk),
        .rst_n_i                    (core_rst_n),
        // AXI4 master → crossbar M0
        .axi_awaddr_o               (xbar_m_awaddr  [0]),
        .axi_awlen_o                (xbar_m_awlen   [0]),
        .axi_awsize_o               (xbar_m_awsize  [0]),
        .axi_awburst_o              (xbar_m_awburst [0]),
        .axi_awvalid_o              (xbar_m_awvalid [0]),
        .axi_awready_i              (xbar_m_awready [0]),
        .axi_wdata_o                (xbar_m_wdata   [0]),
        .axi_wstrb_o                (xbar_m_wstrb   [0]),
        .axi_wlast_o                (xbar_m_wlast   [0]),
        .axi_wvalid_o               (xbar_m_wvalid  [0]),
        .axi_wready_i               (xbar_m_wready  [0]),
        .axi_bresp_i                (xbar_m_bresp   [0]),
        .axi_bvalid_i               (xbar_m_bvalid  [0]),
        .axi_bready_o               (xbar_m_bready  [0]),
        .axi_araddr_o               (xbar_m_araddr  [0]),
        .axi_arlen_o                (xbar_m_arlen   [0]),
        .axi_arsize_o               (xbar_m_arsize  [0]),
        .axi_arburst_o              (xbar_m_arburst [0]),
        .axi_arvalid_o              (xbar_m_arvalid [0]),
        .axi_arready_i              (xbar_m_arready [0]),
        .axi_rdata_i                (xbar_m_rdata   [0]),
        .axi_rresp_i                (xbar_m_rresp   [0]),
        .axi_rvalid_i               (xbar_m_rvalid  [0]),
        .axi_rlast_i                (xbar_m_rlast   [0]),
        .axi_rready_o               (xbar_m_rready  [0]),
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
        .clk                        (core_clk),
        .rst_n                      (core_rst_n),
        // AXI4-Lite ctrl slave ← soc_bus axil_gpu_* (ring slot AXIL_GPU=0)
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
        // AXI4-Lite ifetch master → gif adapter slave
        .m_axil_if_araddr           (gif_axil_araddr),
        .m_axil_if_arvalid          (gif_axil_arvalid),
        .m_axil_if_arready          (gif_axil_arready),
        .m_axil_if_rdata            (gif_axil_rdata),
        .m_axil_if_rresp            (gif_axil_rresp),
        .m_axil_if_rvalid           (gif_axil_rvalid),
        .m_axil_if_rready           (gif_axil_rready),
        // AXI4 data master → crossbar M2
        .m_axi_araddr               (xbar_m_araddr  [2]),
        .m_axi_arvalid              (xbar_m_arvalid [2]),
        .m_axi_arready              (xbar_m_arready [2]),
        .m_axi_rdata                (xbar_m_rdata   [2]),
        .m_axi_rresp                (xbar_m_rresp   [2]),
        .m_axi_rvalid               (xbar_m_rvalid  [2]),
        .m_axi_rready               (xbar_m_rready  [2]),
        .m_axi_awaddr               (xbar_m_awaddr  [2]),
        .m_axi_awvalid              (xbar_m_awvalid [2]),
        .m_axi_awready              (xbar_m_awready [2]),
        .m_axi_wdata                (xbar_m_wdata   [2]),
        .m_axi_wstrb                (xbar_m_wstrb   [2]),
        .m_axi_wvalid               (xbar_m_wvalid  [2]),
        .m_axi_wready               (xbar_m_wready  [2]),
        .m_axi_bresp                (xbar_m_bresp   [2]),
        .m_axi_bvalid               (xbar_m_bvalid  [2]),
        .m_axi_bready               (xbar_m_bready  [2]),
        // IRQ
        .gpu_irq_o                  (gpu_irq_o)
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
        // APB peripheral ports (all 5 slaves)
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
    sram_controller u_sram (
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
