// soc_top.sv
// Phase 5 (M8) / Phase 7 (M-c) — RV32I + GPU-Lite SoC top-level integration.
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
//   Control plane : axi4_to_axilite → axi_lite_interconnect, N_SLAVES=7
//     AXIL_GPU=0, AXIL_UART=1, AXIL_SPI=2, AXIL_TIMER=3,
//     AXIL_DMA=4, AXIL_IRQ=5, AXIL_PLL=6
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
    localparam int unsigned N_SLAVES    = SOC_N_SLAVES;    // 3
    localparam int unsigned N_AXIL_SLV  = AXIL_N_SLAVES;  // 6
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
    // Crossbar slave-facing nets (full AXI4 with ID, unpacked arrays [N_SLAVES])
    // =========================================================================
    logic [IW-1:0]   xbar_s_awid    [N_SLAVES];
    logic [AW-1:0]   xbar_s_awaddr  [N_SLAVES];
    logic [LENW-1:0] xbar_s_awlen   [N_SLAVES];
    logic [2:0]      xbar_s_awsize  [N_SLAVES];
    logic [1:0]      xbar_s_awburst [N_SLAVES];
    logic            xbar_s_awvalid [N_SLAVES];
    logic            xbar_s_awready [N_SLAVES];
    logic [DW-1:0]   xbar_s_wdata   [N_SLAVES];
    logic [SW-1:0]   xbar_s_wstrb   [N_SLAVES];
    logic            xbar_s_wlast   [N_SLAVES];
    logic            xbar_s_wvalid  [N_SLAVES];
    logic            xbar_s_wready  [N_SLAVES];
    logic [IW-1:0]   xbar_s_bid     [N_SLAVES];
    logic [1:0]      xbar_s_bresp   [N_SLAVES];
    logic            xbar_s_bvalid  [N_SLAVES];
    logic            xbar_s_bready  [N_SLAVES];
    logic [IW-1:0]   xbar_s_arid    [N_SLAVES];
    logic [AW-1:0]   xbar_s_araddr  [N_SLAVES];
    logic [LENW-1:0] xbar_s_arlen   [N_SLAVES];
    logic [2:0]      xbar_s_arsize  [N_SLAVES];
    logic [1:0]      xbar_s_arburst [N_SLAVES];
    logic            xbar_s_arvalid [N_SLAVES];
    logic            xbar_s_arready [N_SLAVES];
    logic [IW-1:0]   xbar_s_rid     [N_SLAVES];
    logic [DW-1:0]   xbar_s_rdata   [N_SLAVES];
    logic [1:0]      xbar_s_rresp   [N_SLAVES];
    logic            xbar_s_rlast   [N_SLAVES];
    logic            xbar_s_rvalid  [N_SLAVES];
    logic            xbar_s_rready  [N_SLAVES];

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
    // axi_lite_interconnect slave-facing nets [N_AXIL_SLV]
    // =========================================================================
    logic [AW-1:0] axil_s_awaddr  [N_AXIL_SLV];
    logic [2:0]    axil_s_awprot  [N_AXIL_SLV];
    logic          axil_s_awvalid [N_AXIL_SLV];
    logic          axil_s_awready [N_AXIL_SLV];
    logic [DW-1:0] axil_s_wdata   [N_AXIL_SLV];
    logic [SW-1:0] axil_s_wstrb   [N_AXIL_SLV];
    logic          axil_s_wvalid  [N_AXIL_SLV];
    logic          axil_s_wready  [N_AXIL_SLV];
    logic [1:0]    axil_s_bresp   [N_AXIL_SLV];
    logic          axil_s_bvalid  [N_AXIL_SLV];
    logic          axil_s_bready  [N_AXIL_SLV];
    logic [AW-1:0] axil_s_araddr  [N_AXIL_SLV];
    logic [2:0]    axil_s_arprot  [N_AXIL_SLV];
    logic          axil_s_arvalid [N_AXIL_SLV];
    logic          axil_s_arready [N_AXIL_SLV];
    logic [DW-1:0] axil_s_rdata   [N_AXIL_SLV];
    logic [1:0]    axil_s_rresp   [N_AXIL_SLV];
    logic          axil_s_rvalid  [N_AXIL_SLV];
    logic          axil_s_rready  [N_AXIL_SLV];

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
        // AXI4-Lite ctrl slave ← interconnect AXIL_GPU slot
        .s_axil_awaddr              (axil_s_awaddr  [AXIL_GPU][11:0]),
        .s_axil_awvalid             (axil_s_awvalid [AXIL_GPU]),
        .s_axil_awready             (axil_s_awready [AXIL_GPU]),
        .s_axil_wdata               (axil_s_wdata   [AXIL_GPU]),
        .s_axil_wstrb               (axil_s_wstrb   [AXIL_GPU]),
        .s_axil_wvalid              (axil_s_wvalid  [AXIL_GPU]),
        .s_axil_wready              (axil_s_wready  [AXIL_GPU]),
        .s_axil_bresp               (axil_s_bresp   [AXIL_GPU]),
        .s_axil_bvalid              (axil_s_bvalid  [AXIL_GPU]),
        .s_axil_bready              (axil_s_bready  [AXIL_GPU]),
        .s_axil_araddr              (axil_s_araddr  [AXIL_GPU][11:0]),
        .s_axil_arvalid             (axil_s_arvalid [AXIL_GPU]),
        .s_axil_arready             (axil_s_arready [AXIL_GPU]),
        .s_axil_rdata               (axil_s_rdata   [AXIL_GPU]),
        .s_axil_rresp               (axil_s_rresp   [AXIL_GPU]),
        .s_axil_rvalid              (axil_s_rvalid  [AXIL_GPU]),
        .s_axil_rready              (axil_s_rready  [AXIL_GPU]),
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
        // AXI4-Lite ctrl slave ← interconnect AXIL_DMA slot
        .s_axil_awaddr              (axil_s_awaddr  [AXIL_DMA][11:0]),
        .s_axil_awprot              (axil_s_awprot  [AXIL_DMA]),
        .s_axil_awvalid             (axil_s_awvalid [AXIL_DMA]),
        .s_axil_awready             (axil_s_awready [AXIL_DMA]),
        .s_axil_wdata               (axil_s_wdata   [AXIL_DMA]),
        .s_axil_wstrb               (axil_s_wstrb   [AXIL_DMA]),
        .s_axil_wvalid              (axil_s_wvalid  [AXIL_DMA]),
        .s_axil_wready              (axil_s_wready  [AXIL_DMA]),
        .s_axil_bresp               (axil_s_bresp   [AXIL_DMA]),
        .s_axil_bvalid              (axil_s_bvalid  [AXIL_DMA]),
        .s_axil_bready              (axil_s_bready  [AXIL_DMA]),
        .s_axil_araddr              (axil_s_araddr  [AXIL_DMA][11:0]),
        .s_axil_arprot              (axil_s_arprot  [AXIL_DMA]),
        .s_axil_arvalid             (axil_s_arvalid [AXIL_DMA]),
        .s_axil_arready             (axil_s_arready [AXIL_DMA]),
        .s_axil_rdata               (axil_s_rdata   [AXIL_DMA]),
        .s_axil_rresp               (axil_s_rresp   [AXIL_DMA]),
        .s_axil_rvalid              (axil_s_rvalid  [AXIL_DMA]),
        .s_axil_rready              (axil_s_rready  [AXIL_DMA]),
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
    // =========================================================================
    boot_rom #(
        .MEM_WORDS    (1024),
        .MEM_INIT_FILE(MEM_INIT_FILE)
    ) u_boot_rom (
        .clk          (core_clk),
        .rst_n        (core_rst_n),
        .s_awid       (xbar_s_awid    [SLV_ROM]),
        .s_awaddr     (xbar_s_awaddr  [SLV_ROM]),
        .s_awlen      (xbar_s_awlen   [SLV_ROM]),
        .s_awsize     (xbar_s_awsize  [SLV_ROM]),
        .s_awburst    (xbar_s_awburst [SLV_ROM]),
        .s_awvalid    (xbar_s_awvalid [SLV_ROM]),
        .s_awready    (xbar_s_awready [SLV_ROM]),
        .s_wdata      (xbar_s_wdata   [SLV_ROM]),
        .s_wstrb      (xbar_s_wstrb   [SLV_ROM]),
        .s_wlast      (xbar_s_wlast   [SLV_ROM]),
        .s_wvalid     (xbar_s_wvalid  [SLV_ROM]),
        .s_wready     (xbar_s_wready  [SLV_ROM]),
        .s_bid        (xbar_s_bid     [SLV_ROM]),
        .s_bresp      (xbar_s_bresp   [SLV_ROM]),
        .s_bvalid     (xbar_s_bvalid  [SLV_ROM]),
        .s_bready     (xbar_s_bready  [SLV_ROM]),
        .s_arid       (xbar_s_arid    [SLV_ROM]),
        .s_araddr     (xbar_s_araddr  [SLV_ROM]),
        .s_arlen      (xbar_s_arlen   [SLV_ROM]),
        .s_arsize     (xbar_s_arsize  [SLV_ROM]),
        .s_arburst    (xbar_s_arburst [SLV_ROM]),
        .s_arvalid    (xbar_s_arvalid [SLV_ROM]),
        .s_arready    (xbar_s_arready [SLV_ROM]),
        .s_rid        (xbar_s_rid     [SLV_ROM]),
        .s_rdata      (xbar_s_rdata   [SLV_ROM]),
        .s_rresp      (xbar_s_rresp   [SLV_ROM]),
        .s_rlast      (xbar_s_rlast   [SLV_ROM]),
        .s_rvalid     (xbar_s_rvalid  [SLV_ROM]),
        .s_rready     (xbar_s_rready  [SLV_ROM])
    );

    // =========================================================================
    // S1: SRAM controller (sram_controller) ← crossbar SLV_SRAM
    // =========================================================================
    sram_controller u_sram (
        .clk          (core_clk),
        .rst_n        (core_rst_n),
        .s_awid       (xbar_s_awid    [SLV_SRAM]),
        .s_awaddr     (xbar_s_awaddr  [SLV_SRAM]),
        .s_awlen      (xbar_s_awlen   [SLV_SRAM]),
        .s_awsize     (xbar_s_awsize  [SLV_SRAM]),
        .s_awburst    (xbar_s_awburst [SLV_SRAM]),
        .s_awvalid    (xbar_s_awvalid [SLV_SRAM]),
        .s_awready    (xbar_s_awready [SLV_SRAM]),
        .s_wdata      (xbar_s_wdata   [SLV_SRAM]),
        .s_wstrb      (xbar_s_wstrb   [SLV_SRAM]),
        .s_wlast      (xbar_s_wlast   [SLV_SRAM]),
        .s_wvalid     (xbar_s_wvalid  [SLV_SRAM]),
        .s_wready     (xbar_s_wready  [SLV_SRAM]),
        .s_bid        (xbar_s_bid     [SLV_SRAM]),
        .s_bresp      (xbar_s_bresp   [SLV_SRAM]),
        .s_bvalid     (xbar_s_bvalid  [SLV_SRAM]),
        .s_bready     (xbar_s_bready  [SLV_SRAM]),
        .s_arid       (xbar_s_arid    [SLV_SRAM]),
        .s_araddr     (xbar_s_araddr  [SLV_SRAM]),
        .s_arlen      (xbar_s_arlen   [SLV_SRAM]),
        .s_arsize     (xbar_s_arsize  [SLV_SRAM]),
        .s_arburst    (xbar_s_arburst [SLV_SRAM]),
        .s_arvalid    (xbar_s_arvalid [SLV_SRAM]),
        .s_arready    (xbar_s_arready [SLV_SRAM]),
        .s_rid        (xbar_s_rid     [SLV_SRAM]),
        .s_rdata      (xbar_s_rdata   [SLV_SRAM]),
        .s_rresp      (xbar_s_rresp   [SLV_SRAM]),
        .s_rlast      (xbar_s_rlast   [SLV_SRAM]),
        .s_rvalid     (xbar_s_rvalid  [SLV_SRAM]),
        .s_rready     (xbar_s_rready  [SLV_SRAM])
    );

    // =========================================================================
    // S2: axi4_to_axilite bridge ← crossbar SLV_PERIPH → interconnect master
    // =========================================================================
    axi4_to_axilite u_periph_bridge (
        .clk                        (core_clk),
        .rst_n                      (core_rst_n),
        // AXI4 slave ← crossbar SLV_PERIPH
        .s_awid                     (xbar_s_awid    [SLV_PERIPH]),
        .s_awaddr                   (xbar_s_awaddr  [SLV_PERIPH]),
        .s_awlen                    (xbar_s_awlen   [SLV_PERIPH]),
        .s_awsize                   (xbar_s_awsize  [SLV_PERIPH]),
        .s_awburst                  (xbar_s_awburst [SLV_PERIPH]),
        .s_awvalid                  (xbar_s_awvalid [SLV_PERIPH]),
        .s_awready                  (xbar_s_awready [SLV_PERIPH]),
        .s_wdata                    (xbar_s_wdata   [SLV_PERIPH]),
        .s_wstrb                    (xbar_s_wstrb   [SLV_PERIPH]),
        .s_wlast                    (xbar_s_wlast   [SLV_PERIPH]),
        .s_wvalid                   (xbar_s_wvalid  [SLV_PERIPH]),
        .s_wready                   (xbar_s_wready  [SLV_PERIPH]),
        .s_bid                      (xbar_s_bid     [SLV_PERIPH]),
        .s_bresp                    (xbar_s_bresp   [SLV_PERIPH]),
        .s_bvalid                   (xbar_s_bvalid  [SLV_PERIPH]),
        .s_bready                   (xbar_s_bready  [SLV_PERIPH]),
        .s_arid                     (xbar_s_arid    [SLV_PERIPH]),
        .s_araddr                   (xbar_s_araddr  [SLV_PERIPH]),
        .s_arlen                    (xbar_s_arlen   [SLV_PERIPH]),
        .s_arsize                   (xbar_s_arsize  [SLV_PERIPH]),
        .s_arburst                  (xbar_s_arburst [SLV_PERIPH]),
        .s_arvalid                  (xbar_s_arvalid [SLV_PERIPH]),
        .s_arready                  (xbar_s_arready [SLV_PERIPH]),
        .s_rid                      (xbar_s_rid     [SLV_PERIPH]),
        .s_rdata                    (xbar_s_rdata   [SLV_PERIPH]),
        .s_rresp                    (xbar_s_rresp   [SLV_PERIPH]),
        .s_rlast                    (xbar_s_rlast   [SLV_PERIPH]),
        .s_rvalid                   (xbar_s_rvalid  [SLV_PERIPH]),
        .s_rready                   (xbar_s_rready  [SLV_PERIPH]),
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

    // =========================================================================
    // AXI4-Lite interconnect (1 master → 6 peripheral slaves)
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
        // Slave-facing ports (to peripherals)
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
    // UART (axil_s[AXIL_UART])
    // =========================================================================
    uart_controller #(
        .ADDR_W (12)
    ) u_uart (
        .clk            (core_clk),
        .rst_n          (core_rst_n),
        .s_axil_awaddr  (axil_s_awaddr  [AXIL_UART][11:0]),
        .s_axil_awprot  (axil_s_awprot  [AXIL_UART]),
        .s_axil_awvalid (axil_s_awvalid [AXIL_UART]),
        .s_axil_awready (axil_s_awready [AXIL_UART]),
        .s_axil_wdata   (axil_s_wdata   [AXIL_UART]),
        .s_axil_wstrb   (axil_s_wstrb   [AXIL_UART]),
        .s_axil_wvalid  (axil_s_wvalid  [AXIL_UART]),
        .s_axil_wready  (axil_s_wready  [AXIL_UART]),
        .s_axil_bresp   (axil_s_bresp   [AXIL_UART]),
        .s_axil_bvalid  (axil_s_bvalid  [AXIL_UART]),
        .s_axil_bready  (axil_s_bready  [AXIL_UART]),
        .s_axil_araddr  (axil_s_araddr  [AXIL_UART][11:0]),
        .s_axil_arprot  (axil_s_arprot  [AXIL_UART]),
        .s_axil_arvalid (axil_s_arvalid [AXIL_UART]),
        .s_axil_arready (axil_s_arready [AXIL_UART]),
        .s_axil_rdata   (axil_s_rdata   [AXIL_UART]),
        .s_axil_rresp   (axil_s_rresp   [AXIL_UART]),
        .s_axil_rvalid  (axil_s_rvalid  [AXIL_UART]),
        .s_axil_rready  (axil_s_rready  [AXIL_UART]),
        .uart_tx_o      (uart_tx_o),
        .uart_rx_i      (uart_rx_i),
        .irq_o          (uart_irq)
    );

    // =========================================================================
    // SPI (axil_s[AXIL_SPI])
    // =========================================================================
    spi_controller #(
        .ADDR_W (12)
    ) u_spi (
        .clk            (core_clk),
        .rst_n          (core_rst_n),
        .s_axil_awaddr  (axil_s_awaddr  [AXIL_SPI][11:0]),
        .s_axil_awprot  (axil_s_awprot  [AXIL_SPI]),
        .s_axil_awvalid (axil_s_awvalid [AXIL_SPI]),
        .s_axil_awready (axil_s_awready [AXIL_SPI]),
        .s_axil_wdata   (axil_s_wdata   [AXIL_SPI]),
        .s_axil_wstrb   (axil_s_wstrb   [AXIL_SPI]),
        .s_axil_wvalid  (axil_s_wvalid  [AXIL_SPI]),
        .s_axil_wready  (axil_s_wready  [AXIL_SPI]),
        .s_axil_bresp   (axil_s_bresp   [AXIL_SPI]),
        .s_axil_bvalid  (axil_s_bvalid  [AXIL_SPI]),
        .s_axil_bready  (axil_s_bready  [AXIL_SPI]),
        .s_axil_araddr  (axil_s_araddr  [AXIL_SPI][11:0]),
        .s_axil_arprot  (axil_s_arprot  [AXIL_SPI]),
        .s_axil_arvalid (axil_s_arvalid [AXIL_SPI]),
        .s_axil_arready (axil_s_arready [AXIL_SPI]),
        .s_axil_rdata   (axil_s_rdata   [AXIL_SPI]),
        .s_axil_rresp   (axil_s_rresp   [AXIL_SPI]),
        .s_axil_rvalid  (axil_s_rvalid  [AXIL_SPI]),
        .s_axil_rready  (axil_s_rready  [AXIL_SPI]),
        .spi_sclk_o     (spi_sclk_o),
        .spi_mosi_o     (spi_mosi_o),
        .spi_miso_i     (spi_miso_i),
        .spi_cs_n_o     (spi_cs_n_o),
        .irq_o          (spi_irq)
    );

    // =========================================================================
    // Timer (axil_s[AXIL_TIMER])
    // =========================================================================
    timer #(
        .ADDR_W (12)
    ) u_timer (
        .clk            (core_clk),
        .rst_n          (core_rst_n),
        .s_axil_awaddr  (axil_s_awaddr  [AXIL_TIMER][11:0]),
        .s_axil_awprot  (axil_s_awprot  [AXIL_TIMER]),
        .s_axil_awvalid (axil_s_awvalid [AXIL_TIMER]),
        .s_axil_awready (axil_s_awready [AXIL_TIMER]),
        .s_axil_wdata   (axil_s_wdata   [AXIL_TIMER]),
        .s_axil_wstrb   (axil_s_wstrb   [AXIL_TIMER]),
        .s_axil_wvalid  (axil_s_wvalid  [AXIL_TIMER]),
        .s_axil_wready  (axil_s_wready  [AXIL_TIMER]),
        .s_axil_bresp   (axil_s_bresp   [AXIL_TIMER]),
        .s_axil_bvalid  (axil_s_bvalid  [AXIL_TIMER]),
        .s_axil_bready  (axil_s_bready  [AXIL_TIMER]),
        .s_axil_araddr  (axil_s_araddr  [AXIL_TIMER][11:0]),
        .s_axil_arprot  (axil_s_arprot  [AXIL_TIMER]),
        .s_axil_arvalid (axil_s_arvalid [AXIL_TIMER]),
        .s_axil_arready (axil_s_arready [AXIL_TIMER]),
        .s_axil_rdata   (axil_s_rdata   [AXIL_TIMER]),
        .s_axil_rresp   (axil_s_rresp   [AXIL_TIMER]),
        .s_axil_rvalid  (axil_s_rvalid  [AXIL_TIMER]),
        .s_axil_rready  (axil_s_rready  [AXIL_TIMER]),
        .irq_o          (timer_irq)   // → CPU timer_irq_i (MTIP) only
    );

    // =========================================================================
    // Interrupt controller (axil_s[AXIL_IRQ])
    // IRQ source bit order: [0]=UART [1]=SPI [2]=TIMER [3]=DMA [4]=GPU
    // NOTE: the TIMER slot (index 2) is tied 0 here — the timer drives the CPU
    // dedicated MTIP line (timer_irq_i) directly, so routing it through the
    // external-interrupt aggregator too would double-count one timer event as
    // both MTIP and MEIP. The slot is retained for source-numbering stability.
    // =========================================================================
    interrupt_controller #(
        .ADDR_W    (12),
        .N_SOURCES (5)
    ) u_irq_ctrl (
        .clk            (core_clk),
        .rst_n          (core_rst_n),
        .s_axil_awaddr  (axil_s_awaddr  [AXIL_IRQ][11:0]),
        .s_axil_awprot  (axil_s_awprot  [AXIL_IRQ]),
        .s_axil_awvalid (axil_s_awvalid [AXIL_IRQ]),
        .s_axil_awready (axil_s_awready [AXIL_IRQ]),
        .s_axil_wdata   (axil_s_wdata   [AXIL_IRQ]),
        .s_axil_wstrb   (axil_s_wstrb   [AXIL_IRQ]),
        .s_axil_wvalid  (axil_s_wvalid  [AXIL_IRQ]),
        .s_axil_wready  (axil_s_wready  [AXIL_IRQ]),
        .s_axil_bresp   (axil_s_bresp   [AXIL_IRQ]),
        .s_axil_bvalid  (axil_s_bvalid  [AXIL_IRQ]),
        .s_axil_bready  (axil_s_bready  [AXIL_IRQ]),
        .s_axil_araddr  (axil_s_araddr  [AXIL_IRQ][11:0]),
        .s_axil_arprot  (axil_s_arprot  [AXIL_IRQ]),
        .s_axil_arvalid (axil_s_arvalid [AXIL_IRQ]),
        .s_axil_arready (axil_s_arready [AXIL_IRQ]),
        .s_axil_rdata   (axil_s_rdata   [AXIL_IRQ]),
        .s_axil_rresp   (axil_s_rresp   [AXIL_IRQ]),
        .s_axil_rvalid  (axil_s_rvalid  [AXIL_IRQ]),
        .s_axil_rready  (axil_s_rready  [AXIL_IRQ]),
        // irq_src_i[4:0] = {GPU[4], DMA[3], TIMER[2]=0, SPI[1], UART[0]}
        // TIMER tied 0: timer interrupt is delivered as MTIP via timer_irq_i.
        .irq_src_i      ({gpu_irq_o, dma_irq, 1'b0, spi_irq, uart_irq}),
        .irq_o          (ext_irq)
    );

    // =========================================================================
    // Phase 7 M-c: PLL clock generator + AXI-Lite config slave
    // =========================================================================
    // pll_clkgen: selects STUB (default, synth-safe) or RNM (M-c cosim)
    // via PLL_IMPL parameter.  clk_i is the 100 MHz reference; core_clk is
    // the generated clock that feeds all children (see clock seam section).
    //
    // Note: pll_clkgen and pll_axil_regs themselves run on clk_i / rst_n_i
    // (not core_clk) so the clock generator is not clocked by its own output.
    // pll_axil_regs is in the control ring at AXIL_PLL slot (index 6) but
    // feeds its AXI-Lite port from the interconnect which now runs on core_clk.
    // For M-c cosim this is acceptable (ref and core clocks are synchronous in
    // the stub; the RNM's out_clk is phase-aligned to ref in the model).
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
    // AXIL_PLL (axil_s[AXIL_PLL]): PLL AXI-Lite config slave
    //
    // IMPORTANT — clock-domain intent:
    //   u_pll_regs and u_pll (pll_clkgen) are the SOURCE of core_clk and
    //   pll_locked.  They MUST run on the reference clock (clk_i / rst_n_i),
    //   NOT on core_clk / core_rst_n.  Placing them on core_clk would create
    //   a bootstrap deadlock: core_rst_n requires pll_locked, pll_locked
    //   requires pll_enable=1, pll_enable comes from pll_axil_regs CONTROL[0],
    //   but pll_axil_regs would be held in reset (core_rst_n=0) forever.
    //
    //   STUB mode (PLL_IMPL="STUB"):
    //     out_clk_o = ref_clk_i, so core_clk == clk_i.  No CDC issue — the
    //     AXI-Lite interconnect (u_axil_ic, running on core_clk) and u_pll_regs
    //     (running on clk_i) are in the same physical clock domain.
    //
    //   RNM mode (PLL_IMPL="RNM"):
    //     core_clk != clk_i.  The u_axil_ic interconnect runs on core_clk while
    //     u_pll_regs runs on clk_i (ref clock).  The axil_s_*[AXIL_PLL] bus
    //     therefore crosses a CDC boundary.  A 2-FF synchroniser (or async
    //     handshake) on each valid/ready signal would be required for
    //     production-quality closure.  This is deferred: M-c sim uses STUB
    //     where the CDC is transparent (same clock), and full RNM CDC hardening
    //     is a Phase 7 M-d or tape-out pre-requisite.  Do NOT remove this
    //     comment without adding the synchroniser.
    // =========================================================================
    pll_axil_regs #(
        .ADDR_W (12)
    ) u_pll_regs (
        // Run on reference clock — NOT core_clk — to avoid bootstrap deadlock.
        // See clock-domain note above.
        .clk_i          (clk_i),
        .rst_n_i        (rst_n_i),
        // AXI-Lite slave ← interconnect AXIL_PLL slot
        .s_axil_awaddr  (axil_s_awaddr  [AXIL_PLL][11:0]),
        .s_axil_awprot  (axil_s_awprot  [AXIL_PLL]),
        .s_axil_awvalid (axil_s_awvalid [AXIL_PLL]),
        .s_axil_awready (axil_s_awready [AXIL_PLL]),
        .s_axil_wdata   (axil_s_wdata   [AXIL_PLL]),
        .s_axil_wstrb   (axil_s_wstrb   [AXIL_PLL]),
        .s_axil_wvalid  (axil_s_wvalid  [AXIL_PLL]),
        .s_axil_wready  (axil_s_wready  [AXIL_PLL]),
        .s_axil_bresp   (axil_s_bresp   [AXIL_PLL]),
        .s_axil_bvalid  (axil_s_bvalid  [AXIL_PLL]),
        .s_axil_bready  (axil_s_bready  [AXIL_PLL]),
        .s_axil_araddr  (axil_s_araddr  [AXIL_PLL][11:0]),
        .s_axil_arprot  (axil_s_arprot  [AXIL_PLL]),
        .s_axil_arvalid (axil_s_arvalid [AXIL_PLL]),
        .s_axil_arready (axil_s_arready [AXIL_PLL]),
        .s_axil_rdata   (axil_s_rdata   [AXIL_PLL]),
        .s_axil_rresp   (axil_s_rresp   [AXIL_PLL]),
        .s_axil_rvalid  (axil_s_rvalid  [AXIL_PLL]),
        .s_axil_rready  (axil_s_rready  [AXIL_PLL]),
        // PLL config outputs → pll_clkgen inputs
        .pll_enable_o   (pll_enable),
        .feedback_div_o (pll_fb_div),
        .post_div_sel_o (pll_post_div),
        // PLL status input ← pll_clkgen locked_o
        .pll_locked_i   (pll_locked)
    );

endmodule : soc_top
