// soc_top - top level of the RV32I CPU and GPU-lite SoC.
//
// Function: The module wires the CPU, GPU, DMA, crossbar, peripherals, PMU and two PLL subsystems.
//   It adds no logic beyond wiring, clock gates, isolation clamps and reset combining.
//   The AXI4 crossbar has four masters (CPU, GPU ifetch, GPU data, DMA) and three slaves (boot ROM, SRAM, peripherals).
//   The peripheral slave leads through axi4_to_axilite and axi_lite_interconnect to an APB tree of 14 slaves.
//   The debug plane is an APB3 slave at the top-level ports. It crosses into the CPU domain through u_apb_dbg_cdc.
// Main parameters: MEM_INIT_FILE, SRAM_MEM_WORDS, PLL_IMPL ("STUB" by default), SCAN_CHAINS and MBIST_CPU.
// Clocks and resets: clk_i and rst_n_i are the system reference. core_clk comes from u_pll_sub.
//   core_rst_n is rst_n_i & pll_locked. cpu_clk_i and cpu_rst_n_i feed u_cpu_pll_sub.
//   The CPU runs on cpu_gated_clk. tck_i is a third, asynchronous clock for the JTAG TAP.
//   For a single-clock build, tie cpu_clk_i to clk_i and cpu_rst_n_i to rst_n_i.
// Caller rules:
//   - u_cpu_axi_cdc is the one intentional CDC boundary between the CPU domain and core_clk.
//   - Every other signal between cpu_core_clk and core_clk goes through cdc_sync, cdc_reset_sync or apb_cdc_bridge.
//   - u_pll_sub and u_cpu_pll_sub must stay on their own reference clock. Do not move them onto core_clk.
//   - The s_rst_n_i of u_cpu_axi_cdc must be cpu_core_rst_n, not cpu_domain_rst_n.
//   - The crossbar and the PMU power-down have no drain step. A cold reset of the crossbar or slave side in the middle of
//     a burst, or PMU clock-gating during a CPU burst, can wedge a crossbar slave engine.
//   - Drive the apb_* debug ports synchronously to core_clk (the same net as clk_i in STUB mode).
//   - While the WDT reset is asserted, the CPU clock must run.
//   - Real power switches and retention cells are out of scope.
//   - irq_src_i bit 0 to 11 are uart, spi, timer, dma, gpu, gpio, pwm, wdt, trng, i2c, crypto, npu.
//     The timer slot is tied 0 because the timer IRQ goes straight to the CPU.
// Full contract: ds:mod:soc-top
// Doc: ds:mod:soc-top, tm:mod:soc-top, cr:mod:soc-top

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
    parameter string PLL_IMPL = "STUB",

    // Number of scan chain pairs at the SoC boundary. The top CPU_SCAN_CHAINS indices go straight to u_cpu.
    parameter int unsigned SCAN_CHAINS = 8,
    // MBIST_CPU=1: the CPU hard macro holds its own MBIST controller and cache collars.
    // MBIST_CPU=0: no CPU-domain MBIST. The mbist_* ports are tied inactive.
    parameter bit MBIST_CPU = 1'b1
) (
    // clk_i is the system reference clock. The SoC runs on core_clk from the PLL.
    input  logic clk_i,
    input  logic rst_n_i,

    // cpu_clk_i and cpu_rst_n_i are the CPU-domain reference. u_cpu_pll_sub uses them.
    // For a single-clock build, tie cpu_clk_i to clk_i and cpu_rst_n_i to rst_n_i.
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

    // ── GPIO ─────────────────────────────────────────────────────────────────
    output logic [31:0] gpio_out_o,
    output logic [31:0] gpio_oe_o,
    input  logic [31:0] gpio_in_i,

    // PWM pins.
    output logic [3:0]  pwm_o,

    // Watchdog bite request. It is level-held.
    output logic        wdt_rst_req_o,

    // I2C pins.
    // Open-drain triplet, same convention as GPIO: there is no tristate anywhere
    // in this RTL tree, so `_o` is hard-tied 0 and `_oe_o` is the real control
    // (drive-low = oe 1; release = oe 0 and the external pull-up makes it high).
    // The real open-drain buffer + pull-up is a pad-ring integration concern: an EXTERNAL
    // PULL-UP on each line is REQUIRED, `_o` is dead (see i2c_controller.sv's PAD-RING CONTRACT).
    output logic        i2c_scl_o,
    output logic        i2c_scl_oe_o,
    input  logic        i2c_scl_i,
    output logic        i2c_sda_o,
    output logic        i2c_sda_oe_o,
    input  logic        i2c_sda_i,

    // ── Observability (subset; M7 perf counters added later) ─────────────────
    output logic        commit_valid_o,
    output logic [31:0] commit_pc_o,
    output logic [31:0] commit_insn_o,
    output logic        gpu_irq_o,

    // PLL status.
    output logic        pll_locked_o,       // 1 when system/fabric PLL has acquired lock
    output logic        cpu_pll_locked_o,   // 1 when CPU-domain PLL has acquired lock

    // DFT test access.
    // Direct (parallel) scan access; the JTAG TAP of Stage 1b (j41m.3, ports
    // below) is OR-ed on top by dft_ctrl. Inactive values
    // (functional mode, bit-identical to the pre-DFT design): scan_mode_i=0,
    // scan_en_i=0, scan_rst_ni=1, scan_clk_i=0 (any level; never selected).
    // See Doc: tm:ch:dft-architecture:14-stage-1a-implementation-record-bead-j41m2-scan-ready-fabric-rtl for the full contract.
    input  logic                    scan_mode_i,    // 1 = test mode (quasi-static)
    input  logic                    scan_en_i,      // 1 = shift, 0 = capture
    input  logic                    scan_rst_ni,    // scan reset, active low
    input  logic                    scan_clk_i,     // shared shift/capture clock, all domains
    input  logic [SCAN_CHAINS-1:0]  scan_in_i,      // placeholder until Stage 2 insertion
    output logic [SCAN_CHAINS-1:0]  scan_out_o,     // tied 0 until Stage 2 insertion

    // JTAG TAP pins.
    // Raw pins, no pad ring; TDO is never tri-stated here (no inout): the chip
    // top builds the tristate from tdo_oe_o. TCK is an asynchronous third clock
    // domain. Idle values used by every functional suite: tck_i=0, tms_i=1,
    // tdi_i=0, trst_ni=0 (TAP held in reset). trst_ni must be asserted at
    // power-up (open question Q-TRST). See Doc: tm:ch:dft-architecture:15-stage-1b-specification-and-implementation-record-bead-j41m3-jtag-tap.
    input  logic                    tck_i,          // JTAG test clock
    input  logic                    tms_i,          // JTAG test mode select
    input  logic                    tdi_i,          // JTAG test data in
    input  logic                    trst_ni,        // JTAG reset, active low
    output logic                    tdo_o,          // JTAG test data out
    output logic                    tdo_oe_o        // 1 while TAP shifts (TDO pad enable)
);

    // =========================================================================
    // Local parameters
    // =========================================================================
    localparam int unsigned N_MASTERS   = 4;

    // Scan pairs owned by the CPU hard macro (width of rv32i_cpu_top.scan_in_i/scan_out_o).
    // They are the TOP indices of the SoC scan vectors. A mismatch with the macro's port
    // width is a WIDTH error at the u_cpu instance, not a silent truncation.
    localparam int unsigned CPU_SCAN_CHAINS = 2;
    localparam int unsigned AW          = AXI_ADDR_WIDTH;
    localparam int unsigned DW          = AXI_DATA_WIDTH;
    localparam int unsigned SW          = AXI_STRB_WIDTH;
    localparam int unsigned IW          = AXI_ID_WIDTH;
    localparam int unsigned LENW        = AXI_LEN_WIDTH;

    // Synchroniser depth of the four single-bit core_clk to cpu_core_clk crossings. The default is 2.
    // Derive the reset-release ordering again before you raise it.
    localparam int unsigned SYNC_STAGES_TO_CPU = 2;
    // Depth of the cpu_core_clk to core_clk crossing in u_cpu_iso_ack_sync.
    localparam int unsigned SYNC_STAGES_FROM_CPU = 2;

    // Every scan and test consumer takes its control from these nets. They come from one dft_ctrl instance.
    // In functional mode every mux and mask passes through.
    logic dft_scan_mode;
    logic dft_scan_rst_n;
    logic dft_test_en;
    logic dft_test_clk;
    // dft_scan_en is dft_scan_en_req ANDed with scan_wipe_done_o of u_crypto.
    // The Stage 2 SE pins must take dft_scan_en, not the raw scan_en_i port.
    logic dft_scan_en_req;
    // (* keep *) stops synthesis from merging crypto_wipe_done. The Stage 2 step finds the net by name.
    (* keep *) logic crypto_wipe_done;
    logic dft_scan_en;
    assign dft_scan_en = dft_scan_en_req & crypto_wipe_done;

    // MBIST (DFT Stage 4, section 16): TAP data registers and the TCK-side crossing hooks.
    logic [28:0]  mbist_ctl;
    logic         mbist_wr;
    logic         mbist_force;
    logic         mbist_rst_tck_n;
    logic         mbist_wr_ready;
    logic [138:0] mbist_status;

    // MBIST CPU domain (c54a): soc_mbist's holding-register outputs into u_cpu's mbist_* ports, and the
    // macro's 69-bit status block back. With MBIST_CPU = 0 the three outputs of soc_mbist are tied inactive
    // and mb_cpu_status is ignored. mb_cpu_ctl_rst_n is the controller reset of the stand-alone (fabric)
    // instantiation; the macro's controller folds the CPU reset into run, so it has no consumer here.
    logic         mb_cpu_run;
    logic [25:0]  mb_cpu_cfg;
    /* verilator lint_off UNUSEDSIGNAL */
    logic         mb_cpu_ctl_rst_n;
    /* verilator lint_on  UNUSEDSIGNAL */
    logic [68:0]  mb_cpu_status;

    dft_ctrl u_dft_ctrl (
        .scan_mode_i (scan_mode_i),
        .scan_en_i   (scan_en_i),
        .scan_rst_ni (scan_rst_ni),
        .scan_clk_i  (scan_clk_i),
        .tck_i       (tck_i),
        .tms_i       (tms_i),
        .tdi_i       (tdi_i),
        .trst_ni     (trst_ni),
        .tdo_o       (tdo_o),
        .tdo_oe_o    (tdo_oe_o),
        .scan_mode_o (dft_scan_mode),
        .scan_en_o   (dft_scan_en_req),
        .scan_rst_no (dft_scan_rst_n),
        .test_en_o   (dft_test_en),
        .test_clk_o  (dft_test_clk),
        .mbist_ctl_o       (mbist_ctl),
        .mbist_wr_o        (mbist_wr),
        .mbist_force_o     (mbist_force),
        .mbist_rst_tck_n_o (mbist_rst_tck_n),
        .mbist_wr_ready_i  (mbist_wr_ready),
        .mbist_status_i    (mbist_status)
    );

    // scan_in_i has no consumer. scan_out_o is tied 0 until Stage 2 scan insertion.
    // The top CPU_SCAN_CHAINS pairs go straight to u_cpu.
`ifndef __pnr__
    initial begin
        if (SCAN_CHAINS <= CPU_SCAN_CHAINS)
            $fatal(1, "soc_top: SCAN_CHAINS must exceed the CPU macro's %0d scan pairs", CPU_SCAN_CHAINS);
    end
`endif
    localparam int unsigned FABRIC_SCAN_CHAINS = SCAN_CHAINS - CPU_SCAN_CHAINS;

    logic [CPU_SCAN_CHAINS-1:0] cpu_scan_in_w;
    logic [CPU_SCAN_CHAINS-1:0] cpu_scan_out_w;
    assign cpu_scan_in_w = scan_in_i[SCAN_CHAINS-1 -: CPU_SCAN_CHAINS];

    /* verilator lint_off UNUSEDSIGNAL */
    logic [FABRIC_SCAN_CHAINS-1:0] dft_scan_in_unused;
    assign dft_scan_in_unused = scan_in_i[FABRIC_SCAN_CHAINS-1:0];
    /* verilator lint_on  UNUSEDSIGNAL */
    assign scan_out_o[FABRIC_SCAN_CHAINS-1:0] = '0;  // DFT_PLACEHOLDER: replaced by Stage 2 insertion
    assign scan_out_o[SCAN_CHAINS-1 -: CPU_SCAN_CHAINS] = cpu_scan_out_w;

    // u_pll_sub runs on clk_i and rst_n_i. core_clk and core_rst_n come from it.
    logic core_clk;     // PLL output clock — feeds all child clk ports
    logic core_rst_n;   // gated reset: rst_n_i & pll_locked (from pll_subsystem)
    logic pll_locked;   // raw PLL lock flag — export to top-level port
    // j41m.2: the reference clock each pll_subsystem actually runs on (clk_i /
    // cpu_clk_i, or the test clock in scan mode). The APB CDC bridges' destination
    // faces share that reference and must use it, not the raw port.
    logic pll_ref_clk;
    logic cpu_pll_ref_clk;

    // Second PLL subsystem. cpu_clk_i feeds it.
    // cpu_core_clk and cpu_core_rst_n feed u_cpu_cg and the CPU-domain reset tree.
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
    localparam int unsigned N_APB_SLV = APB_N_SLAVES; // 14

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
    // PMU sequencing nets.
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
    // CPU-domain synchronisers for the PMU control signals.
    // u_cpu_clk_dis_sync must use cpu_core_clk, never cpu_gated_clk. The gated clock would wait on its own enable.
    // pmu_cpu_clk_dis_sync is the synchronised inverse of pmu_cpu_clk_en. The reset value 0 of cdc_sync means the clock runs.
    // The u_cpu_cg enable is ~pmu_cpu_clk_dis_sync ANDed with pmu_cpu_rst_n_cpu_sync.
    // cpu_gated_clk cannot tick while the PMU reset is asserted in cpu_core_clk, whatever the skew of the two synchronisers.
    // =========================================================================
    logic pmu_cpu_clk_dis_sync;
    cdc_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_CPU)
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
    // pmu_cpu_iso_en_sync is not inverted. Its reset value 0 means not isolated, like the PMU reset default.
    logic pmu_cpu_iso_en_sync;
    cdc_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_CPU)
    ) u_cpu_iso_en_sync (
        .clk_i   (cpu_core_clk),
        .rst_n_i (cpu_core_rst_n),
        .d_i     (pmu_cpu_iso_en),
        .q_o     (pmu_cpu_iso_en_sync)
    );

    // Isolation-ack handshake.
    // u_cpu_iso_ack_sync returns pmu_cpu_iso_en_sync to core_clk as pmu_cpu_iso_ack. The PMU waits for it in DOM_PD_ISO and DOM_PU_ISO.
    // The source flop uses cpu_core_clk, never cpu_gated_clk. If cpu_core_rst_n is low, ISO_ACK_TIMEOUT bounds the wait.
    logic pmu_cpu_iso_ack;
    cdc_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_FROM_CPU)
    ) u_cpu_iso_ack_sync (
        .clk_i   (core_clk),
        .rst_n_i (core_rst_n),
        .d_i     (pmu_cpu_iso_en_sync),
        .q_o     (pmu_cpu_iso_ack)
    );

    // pmu_cpu_rst_n: synchronised into the cpu_core_clk domain with
    // cdc_reset_sync (async-assert / sync-deassert) — this is exactly the
    // "per-domain PMU reset" reuse. See ds:mod:cdc-reset-sync.
    // The source reset of this cdc_reset_sync is pmu_cpu_rst_n, not cpu_core_rst_n. cpu_core_rst_n already belongs to cpu_core_clk.
    logic pmu_cpu_rst_n_cpu_sync;
    cdc_reset_sync #(
        .STAGES (2)
    ) u_cpu_pmu_rst_sync (
        .clk_i       (cpu_core_clk),
        .rst_n_i     (pmu_cpu_rst_n),
        .scanmode_i  (dft_scan_mode),
        .scan_rst_ni (dft_scan_rst_n),
        .rst_n_o     (pmu_cpu_rst_n_cpu_sync)
    );

    // =========================================================================
    // WDT bite to CPU-domain reset.
    // When WDT_CTRL.RST_EN is 1, a bite resets the CPU domain only. It does not pass through pmu.sv.
    // wdt_cpu_rst_req_q is a registered AND of bite and RST_EN. wdt_rst_req_o is not gated by RST_EN.
    // The CPU clock must run while this reset is asserted. cpu_gated_clk_en has no WDT term.
    // =========================================================================
    logic wdt_rst_en_w;      // driven by u_wdt.rst_en_o (real port, not a shadow)
    logic wdt_cpu_rst_req_q;
    always_ff @(posedge core_clk) begin
        if (!core_rst_n) wdt_cpu_rst_req_q <= 1'b0;
        else             wdt_cpu_rst_req_q <= wdt_rst_req_o & wdt_rst_en_w;
    end

    logic wdt_cpu_rst_n_cpu_sync;
    cdc_reset_sync #(
        .STAGES (2)
    ) u_cpu_wdt_rst_sync (
        .clk_i       (cpu_core_clk),
        .rst_n_i     (~wdt_cpu_rst_req_q),
        .scanmode_i  (dft_scan_mode),
        .scan_rst_ni (dft_scan_rst_n),
        .rst_n_o     (wdt_cpu_rst_n_cpu_sync)
    );

    // =========================================================================
    // IRQ signals
    // =========================================================================
    // ext_irq and timer_irq are declared here so that every use follows its declaration.
    logic uart_irq;
    logic spi_irq;
    logic timer_irq;
    logic dma_irq;
    logic gpio_irq;
    // gpu_irq_o is exposed at top-level port; driven by gpu_top

    // IRQ bits 6 to 11 come from the peripheral instances below.
    logic pwm_irq;
    logic wdt_irq;
    logic trng_irq;
    logic i2c_irq;
    logic crypto_irq;
    logic npu_irq;

    // The pins pwm_o, wdt_rst_req_o and i2c_* come from the peripheral instances below.

    logic ext_irq;    // interrupt_controller output → CPU ext_irq_i

    // ext_irq / timer_irq: level-held sources (see interrupt_controller.sv /
    // timer.sv — irq_o is `|masked` / `irq_en & irq_pending_q`, both sticky
    // until explicitly cleared, never a single-cycle pulse), so a plain 2-FF
    // level synchroniser cannot miss the assertion. See ds:mod:soc-top.
    logic ext_irq_cpu_sync, timer_irq_cpu_sync;
    cdc_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_CPU)
    ) u_ext_irq_sync (
        .clk_i   (cpu_core_clk),
        .rst_n_i (cpu_core_rst_n),
        .d_i     (ext_irq),
        .q_o     (ext_irq_cpu_sync)
    );
    cdc_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_CPU)
    ) u_timer_irq_sync (
        .clk_i   (cpu_core_clk),
        .rst_n_i (cpu_core_rst_n),
        .d_i     (timer_irq),
        .q_o     (timer_irq_cpu_sync)
    );

    // =========================================================================
    // Reset trees. cpu_domain_rst_n is cpu_core_rst_n ANDed with pmu_cpu_rst_n_cpu_sync and wdt_cpu_rst_n_cpu_sync.
    // gpu_domain_rst_n is core_rst_n & pmu_gpu_rst_n. No reset synchroniser is added, because the GPU stays on core_clk.
    // cpu_domain_rst_n resets u_cpu and the m face of u_apb_dbg_cdc.
    // u_cpu_axi_cdc uses cpu_core_rst_n as s_rst_n_i, not cpu_domain_rst_n.
    // =========================================================================
    logic cpu_domain_rst_n, gpu_domain_rst_n;
    assign cpu_domain_rst_n = cpu_core_rst_n & pmu_cpu_rst_n_cpu_sync & wdt_cpu_rst_n_cpu_sync;

    // DFT: cpu_domain_rst_n needs no override of its own -- in scan mode all
    // three terms equal dft_scan_rst_n (cpu_core_rst_n through pll_subsystem's u_core_rm,
    // the two syncs through cdc_reset_sync's output mux), so their AND does too.
    // gpu_domain_rst_n is the exception: pmu_gpu_rst_n is a PMU flop output with no
    // synchroniser in front of it, so it would toggle while the chains shift.
    logic gpu_domain_rst_n_func;
    assign gpu_domain_rst_n_func = core_rst_n & pmu_gpu_rst_n;
    dft_rst_mux u_gpu_domain_rm (
        .func_rst_n_i (gpu_domain_rst_n_func),
        .scan_rst_ni  (dft_scan_rst_n),
        .scan_mode_i  (dft_scan_mode),
        .rst_n_o      (gpu_domain_rst_n)
    );

    // ISO_CPU and ISO_GPU clamp the master-side request and accept handshakes and the domain outputs.
    // Payload bits are not clamped. The valid signal qualifies them. Slave-side responses of u_gpu and the CPU debug port are not clamped.
    // The ISO_CPU clamp is at the s face of u_cpu_axi_cdc, qualified by pmu_cpu_iso_en_sync. ISO_GPU stays on core_clk.
    logic cpu_axi_awvalid_raw, cpu_axi_wvalid_raw, cpu_axi_arvalid_raw;
    logic cpu_axi_bready_raw, cpu_axi_rready_raw;
    logic cpu_commit_valid_raw;

    logic gpu_axi_awvalid_raw, gpu_axi_wvalid_raw, gpu_axi_arvalid_raw;
    logic gpu_axi_bready_raw, gpu_axi_rready_raw;
    logic gpu_gif_arvalid_raw, gpu_gif_rready_raw;
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
    // APB3 debug-port CDC bridge u_apb_dbg_cdc.
    // The s face of u_apb_dbg_cdc uses core_clk and core_rst_n. The m face uses cpu_gated_clk and cpu_domain_rst_n.
    // apb_cdc_bridge is APB4. The CPU debug slave is APB3. s_pstrb_i is tied to all ones. m_pstrb_o goes to an unused net.
    // =========================================================================
    logic        dbg_bridge_m_psel, dbg_bridge_m_penable, dbg_bridge_m_pwrite;
    logic [11:0] dbg_bridge_m_paddr;
    logic [31:0] dbg_bridge_m_pwdata, dbg_bridge_m_prdata;
    logic        dbg_bridge_m_pready, dbg_bridge_m_pslverr;
    logic [3:0]  dbg_bridge_m_pstrb_unused;

    apb_cdc_bridge #(
        .ADDR_W (12)
    ) u_apb_dbg_cdc (
        .scanmode_i  (dft_scan_mode),
        .scan_rst_ni (dft_scan_rst_n),

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
    // CPU-domain face of the CPU to crossbar M0 AXI4 CDC bridge.
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
        // APB3 debug slave. It takes the m face of u_apb_dbg_cdc, in the CPU domain.
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
        // Interrupt inputs. They are synchronised into the CPU domain. Both sources are level-held.
        .ext_irq_i                  (ext_irq_cpu_sync),
        .timer_irq_i                (timer_irq_cpu_sync),
        // DFT (j41m.4). clk_i above is already the test clock in scan mode (dft_clk_mux
        // ahead of u_cpu_cg), cpu_domain_rst_n already equals dft_scan_rst_n in scan mode,
        // so the macro needs only mode/enable/data. dft_scan_en is the TAP-or-pin scan
        // enable from dft_ctrl, NOT the raw scan_en_i port.
        .scan_mode_i                (dft_scan_mode),
        .scan_en_i                  (dft_scan_en),
        .scan_in_i                  (cpu_scan_in_w),
        .scan_out_o                 (cpu_scan_out_w),
        // MBIST (c54a, section 16.7): CPU-domain holding register in, 69-bit status block out. Quasi-static
        // levels crossing from cpu_core_clk into the gated clk_i of the same source and frequency.
        .mbist_run_i                (mb_cpu_run),
        .mbist_cfg_i                (mb_cpu_cfg),
        .mbist_status_o             (mb_cpu_status)
    );

    // ISO_CPU functional-isolation clamp (`-location parent`, clamp_value 0):
    // forces the CPU->fabric handshake + commit observability to 0 while
    // pmu_cpu_iso_en_sync is asserted. See clamp-scope note above u_cpu.
    assign cpu_bridge_s_awvalid = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_awvalid_raw;
    assign cpu_bridge_s_wvalid  = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_wvalid_raw;
    assign cpu_bridge_s_arvalid = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_arvalid_raw;
    assign cpu_bridge_s_bready  = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_bready_raw;
    assign cpu_bridge_s_rready  = pmu_cpu_iso_en_sync ? 1'b0 : cpu_axi_rready_raw;
    assign commit_valid_o       = pmu_cpu_iso_en_sync ? 1'b0 : cpu_commit_valid_raw;

    // =========================================================================
    // u_cpu_axi_cdc is the one CDC boundary between cpu_gated_clk and core_clk. Its reset is a hard flush.
    // s_rst_n_i is cpu_core_rst_n. Do not change it to cpu_domain_rst_n.
    // The bridge keeps its state in a PMU power cycle, because a flush would lose a response that u_cpu waits for.
    // u_cpu state in CPU_OFF is not guaranteed: its clock stops and its reset is synchronous. Doc: ds:req:pmu-181
    // Known gap: a mid-burst CPU transaction at clock gating can still wedge a crossbar slave engine. No drain step exists.
    // s_clk_i ticks throughout the cpu_core_rst_n low window, so the reset-width rule of async_axi_fifo holds.
    // =========================================================================
    async_axi_fifo u_cpu_axi_cdc (
        .scanmode_i  (dft_scan_mode),
        .scan_rst_ni (dft_scan_rst_n),

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
        .m_axil_if_rready           (gpu_gif_rready_raw),
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
    // forces the GPU->fabric handshake (incl. m_axil_if_rready) + IRQ to 0 while pmu_gpu_iso_en is
    // asserted. See clamp-scope note above u_gpu.
    assign xbar_m_awvalid [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_awvalid_raw;
    assign xbar_m_wvalid  [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_wvalid_raw;
    assign xbar_m_arvalid [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_arvalid_raw;
    assign xbar_m_bready  [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_bready_raw;
    assign xbar_m_rready  [2] = pmu_gpu_iso_en ? 1'b0 : gpu_axi_rready_raw;
    assign gif_axil_arvalid   = pmu_gpu_iso_en ? 1'b0 : gpu_gif_arvalid_raw;
    // gif_axil_rready is clamped by pmu_gpu_iso_en like the other ready and valid outputs.
    assign gif_axil_rready    = pmu_gpu_iso_en ? 1'b0 : gpu_gif_rready_raw;
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
    // MBIST. The core-domain controller tests the two SoC-level SRAM macros, u_sram and the NPU weight memory.
    // Only the TAP starts it. No bus slave decodes to it.
    // =========================================================================
    logic         mb_bist_en;
    logic         mb_ce;
    logic         mb_we;
    logic [3:0]   mb_wmask;
    logic [9:0]   mb_addr;
    logic [31:0]  mb_din;
    logic [31:0]  mb_sram_dout0;
    logic [31:0]  mb_sram_dout1;
    logic [31:0]  mb_npu_dout0;

    soc_mbist #(
        .CPU_PRESENT (MBIST_CPU),
        .N_MEM       (2),
        .AW          (10),
        .P1_MASK     (2'b01)
    ) u_mbist (
        .tck_i            (tck_i),
        .rst_tck_n_i      (mbist_rst_tck_n),
        .mbist_ctl_i      (mbist_ctl),
        .mbist_wr_i       (mbist_wr),
        .mbist_wr_ready_o (mbist_wr_ready),
        .mbist_status_o   (mbist_status),
        .trst_ni          (trst_ni),
        .scan_mode_i      (dft_scan_mode),
        .scan_rst_ni      (dft_scan_rst_n),
        .core_clk_i       (core_clk),
        .core_rst_n_i     (core_rst_n),
        .bist_en_o        (mb_bist_en),
        .b_ce_o           (mb_ce),
        .b_we_o           (mb_we),
        .b_wmask_o        (mb_wmask),
        .b_addr_o         (mb_addr),
        .b_din_o          (mb_din),
        .dout0_i          ({mb_npu_dout0, mb_sram_dout0}),
        .dout1_i          ({32'd0, mb_sram_dout1}),
        .cpu_clk_i        (cpu_core_clk),
        .cpu_rst_n_i      (cpu_core_rst_n),
        .cpu_run_o        (mb_cpu_run),
        .cpu_cfg_o        (mb_cpu_cfg),
        .cpu_ctl_rst_n_o  (mb_cpu_ctl_rst_n),
        .cpu_status_i     (mb_cpu_status)
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
        .s_rready     (bus_mem_rready),
        .mb_en_i      (mb_bist_en),
        .mb_ce_i      (mb_ce),
        .mb_we_i      (mb_we),
        .mb_wmask_i   (mb_wmask),
        .mb_addr_i    (mb_addr),
        .mb_din_i     (mb_din),
        .mb_dout0_o   (mb_sram_dout0),
        .mb_dout1_o   (mb_sram_dout1)
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
    // GPIO — APB slave (apb_psel[APB_GPIO])
    // =========================================================================
    gpio_controller #(
        .ADDR_W (12),
        .N_PINS (32)
    ) u_gpio (
        .clk        (core_clk),
        .rst_n      (core_rst_n),
        .psel       (apb_psel    [APB_GPIO]),
        .penable    (apb_penable [APB_GPIO]),
        .pwrite     (apb_pwrite  [APB_GPIO]),
        .paddr      (apb_paddr   [APB_GPIO][11:0]),
        .pwdata     (apb_pwdata  [APB_GPIO]),
        .pstrb      (apb_pstrb   [APB_GPIO]),
        .prdata     (apb_prdata  [APB_GPIO]),
        .pready     (apb_pready  [APB_GPIO]),
        .pslverr    (apb_pslverr [APB_GPIO]),
        .gpio_out_o (gpio_out_o),
        .gpio_oe_o  (gpio_oe_o),
        .gpio_in_i  (gpio_in_i),
        .irq_o      (gpio_irq)
    );

    // =========================================================================
    // PWM APB slave (apb_psel[APB_PWM]).
    // =========================================================================
    pwm_controller #(
        .ADDR_W (12),
        .N_CH   (4)
    ) u_pwm (
        .clk     (core_clk),
        .rst_n   (core_rst_n),
        .psel    (apb_psel    [APB_PWM]),
        .penable (apb_penable [APB_PWM]),
        .pwrite  (apb_pwrite  [APB_PWM]),
        .paddr   (apb_paddr   [APB_PWM][11:0]),
        .pwdata  (apb_pwdata  [APB_PWM]),
        .pstrb   (apb_pstrb   [APB_PWM]),
        .prdata  (apb_prdata  [APB_PWM]),
        .pready  (apb_pready  [APB_PWM]),
        .pslverr (apb_pslverr [APB_PWM]),
        .pwm_o   (pwm_o),
        .irq_o   (pwm_irq)
    );

    // =========================================================================
    // WDT APB slave (apb_psel[APB_WDT]).
    // core_clk domain. irq_o -> interrupt_controller bit 7; wdt_rst_req_o is the
    // top-level bite pin AND (via RST_EN) the CPU-domain reset source, see
    // u_cpu_wdt_rst_sync above.
    // =========================================================================
    watchdog_timer #(
        .ADDR_W (12)
    ) u_wdt (
        .clk           (core_clk),
        .rst_n         (core_rst_n),
        .psel          (apb_psel    [APB_WDT]),
        .penable       (apb_penable [APB_WDT]),
        .pwrite        (apb_pwrite  [APB_WDT]),
        .paddr         (apb_paddr   [APB_WDT][11:0]),
        .pwdata        (apb_pwdata  [APB_WDT]),
        .pstrb         (apb_pstrb   [APB_WDT]),
        .prdata        (apb_prdata  [APB_WDT]),
        .pready        (apb_pready  [APB_WDT]),
        .pslverr       (apb_pslverr [APB_WDT]),
        .irq_o         (wdt_irq),
        .wdt_rst_req_o (wdt_rst_req_o),
        .rst_en_o      (wdt_rst_en_w)
    );

    // =========================================================================
    // TRNG APB slave (apb_psel[APB_TRNG]).
    // core_clk domain, no top-level pins: the entropy source is an `ifdef-swapped
    // sub-module (trng_lfsr_entropy by default, trng_ro_sky130 under TRNG_RO_SKY130),
    // not a port. irq_o -> interrupt_controller bit 8. The default build is a
    // deterministic LFSR and advertises that via TRNG_STATUS[3] (INSECURE) = 1.
    // =========================================================================
    trng #(
        .ADDR_W (12)
    ) u_trng (
        .clk     (core_clk),
        .rst_n   (core_rst_n),
        .psel    (apb_psel    [APB_TRNG]),
        .penable (apb_penable [APB_TRNG]),
        .pwrite  (apb_pwrite  [APB_TRNG]),
        .paddr   (apb_paddr   [APB_TRNG][11:0]),
        .pwdata  (apb_pwdata  [APB_TRNG]),
        .pstrb   (apb_pstrb   [APB_TRNG]),
        .prdata  (apb_prdata  [APB_TRNG]),
        .pready  (apb_pready  [APB_TRNG]),
        .pslverr (apb_pslverr [APB_TRNG]),
        .irq_o   (trng_irq)
    );

    // =========================================================================
    // I2C APB slave (apb_psel[APB_I2C]).
    // core_clk domain. Open-drain triplets, NO tristate (same convention as GPIO): `_oe_o` is
    // the real control (1 = drive low, 0 = release), `_o` is hard-tied 0 inside the module and
    // dead, `_i` is the asynchronous sensed pad level (synchronised inside u_i2c). External
    // pull-ups are REQUIRED; the wired-AND bus lives off-chip / in the testbench. irq_o ->
    // interrupt_controller bit 9 (level-held).
    // =========================================================================
    i2c_controller #(
        .ADDR_W (12)
    ) u_i2c (
        .clk          (core_clk),
        .rst_n        (core_rst_n),
        .psel         (apb_psel    [APB_I2C]),
        .penable      (apb_penable [APB_I2C]),
        .pwrite       (apb_pwrite  [APB_I2C]),
        .paddr        (apb_paddr   [APB_I2C][11:0]),
        .pwdata       (apb_pwdata  [APB_I2C]),
        .pstrb        (apb_pstrb   [APB_I2C]),
        .prdata       (apb_prdata  [APB_I2C]),
        .pready       (apb_pready  [APB_I2C]),
        .pslverr      (apb_pslverr [APB_I2C]),
        .i2c_scl_o    (i2c_scl_o),
        .i2c_scl_oe_o (i2c_scl_oe_o),
        .i2c_scl_i    (i2c_scl_i),
        .i2c_sda_o    (i2c_sda_o),
        .i2c_sda_oe_o (i2c_sda_oe_o),
        .i2c_sda_i    (i2c_sda_i),
        .irq_o        (i2c_irq)
    );

    // =========================================================================
    // CRYPTO - AES-128 / SHA-256 accelerator, APB slave (apb_psel[APB_CRYPTO]).
    // core_clk domain only. It has no asynchronous inputs and no top-level pins. irq_o goes to interrupt_controller bit 10.
    // This block is not production cryptography. See the crypto_accel.sv header NON-GOALS.
    // =========================================================================
    crypto_accel #(
        .ADDR_W (12)
    ) u_crypto (
        .clk     (core_clk),
        .rst_n   (core_rst_n),
        // DFT (j41m.2): forces the key_q / rk_q read nets to 0 in scan mode.
        .scan_mode_i (dft_scan_mode),
        // j41m.17: wipe applied -> scan enable may rise (see dft_scan_en above).
        .scan_wipe_done_o (crypto_wipe_done),
        .psel    (apb_psel    [APB_CRYPTO]),
        .penable (apb_penable [APB_CRYPTO]),
        .pwrite  (apb_pwrite  [APB_CRYPTO]),
        .paddr   (apb_paddr   [APB_CRYPTO][11:0]),
        .pwdata  (apb_pwdata  [APB_CRYPTO]),
        .pstrb   (apb_pstrb   [APB_CRYPTO]),
        .prdata  (apb_prdata  [APB_CRYPTO]),
        .pready  (apb_pready  [APB_CRYPTO]),
        .pslverr (apb_pslverr [APB_CRYPTO]),
        .irq_o   (crypto_irq)
    );

    // =========================================================================
    // NPU - INT8 4x4 weight-stationary MAC array, APB slave (apb_psel[APB_NPU]).
    // core_clk domain, single clock, NO asynchronous
    // inputs and NO top-level pins (register-only), so no cdc_sync and no SDC false-path apply.
    // npu_mac_array / npu_weight_mem are instantiated inside npu_top; the weight store is one
    // 4 KB SRAM macro. Default EN_NPU = 1. irq_o -> interrupt_controller bit 11 (level-held).
    // =========================================================================
    npu_top #(
        .ADDR_W (12)
    ) u_npu (
        .clk     (core_clk),
        .rst_n   (core_rst_n),
        .psel    (apb_psel    [APB_NPU]),
        .penable (apb_penable [APB_NPU]),
        .pwrite  (apb_pwrite  [APB_NPU]),
        .paddr   (apb_paddr   [APB_NPU][11:0]),
        .pwdata  (apb_pwdata  [APB_NPU]),
        .pstrb   (apb_pstrb   [APB_NPU]),
        .prdata  (apb_prdata  [APB_NPU]),
        .pready  (apb_pready  [APB_NPU]),
        .pslverr (apb_pslverr [APB_NPU]),
        .irq_o   (npu_irq),
        .mb_en_i    (mb_bist_en),
        .mb_ce_i    (mb_ce),
        .mb_we_i    (mb_we),
        .mb_wmask_i (mb_wmask),
        .mb_addr_i  (mb_addr),
        .mb_din_i   (mb_din),
        .mb_dout0_o (mb_npu_dout0)
    );

    // =========================================================================
    // Interrupt controller — APB slave (apb_psel[APB_IRQ])
    // irq_src_i[11:0] = {NPU[11], CRYPTO[10], I2C[9], TRNG[8], WDT[7], PWM[6],
    //                     GPIO[5], GPU[4], DMA[3], TIMER[2]=0, SPI[1], UART[0]}
    // TIMER slot tied 0: timer IRQ goes directly to CPU MTIP; routing it here
    // too would double-count the event.
    // =========================================================================
    interrupt_controller #(
        .ADDR_W    (12),
        .N_SOURCES (12)
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
        .irq_src_i  ({npu_irq, crypto_irq, i2c_irq, trng_irq, wdt_irq, pwm_irq,
                      gpio_irq, gpu_irq_o, dma_irq, 1'b0, spi_irq, uart_irq}),
        .irq_o      (ext_irq)
    );

    // =========================================================================
    // APB4 CDC bridge for the APB_PLL slot (u_apb_pll_cdc).
    // The s face uses core_clk and core_rst_n. The m face uses clk_i and rst_n_i, the raw reference of u_pll_sub.
    // The bridge is instantiated for every PLL_IMPL. In STUB mode it only adds latency.
    // The bridge cannot deadlock the PLL. pll_enable resets to 1 and bit 0 cannot be cleared.
    // =========================================================================
    logic        pll_m_psel, pll_m_penable, pll_m_pwrite;
    logic [11:0] pll_m_paddr;
    logic [31:0] pll_m_pwdata, pll_m_prdata;
    logic [3:0]  pll_m_pstrb;
    logic        pll_m_pready, pll_m_pslverr;

    apb_cdc_bridge #(
        .ADDR_W (12)
    ) u_apb_pll_cdc (
        .scanmode_i  (dft_scan_mode),
        .scan_rst_ni (dft_scan_rst_n),

        .s_clk_i     (core_clk),
        .s_rst_n_i   (core_rst_n),
        .s_psel_i    (apb_psel    [APB_PLL]),
        .s_penable_i (apb_penable [APB_PLL]),
        .s_pwrite_i  (apb_pwrite  [APB_PLL]),
        .s_paddr_i   (apb_paddr   [APB_PLL][11:0]),
        .s_pwdata_i  (apb_pwdata  [APB_PLL]),
        .s_pstrb_i   (apb_pstrb   [APB_PLL]),
        .s_prdata_o  (apb_prdata  [APB_PLL]),
        .s_pready_o  (apb_pready  [APB_PLL]),
        .s_pslverr_o (apb_pslverr [APB_PLL]),

        .m_clk_i     (pll_ref_clk),
        .m_rst_n_i   (rst_n_i),
        .m_psel_o    (pll_m_psel),
        .m_penable_o (pll_m_penable),
        .m_pwrite_o  (pll_m_pwrite),
        .m_paddr_o   (pll_m_paddr),
        .m_pwdata_o  (pll_m_pwdata),
        .m_pstrb_o   (pll_m_pstrb),
        .m_prdata_i  (pll_m_prdata),
        .m_pready_i  (pll_m_pready),
        .m_pslverr_i (pll_m_pslverr)
    );

    // =========================================================================
    // pll_subsystem wraps pll_clkgen and pll_apb_regs. u_pll_sub and all its logic run on clk_i and rst_n_i.
    // Running them on core_clk creates a bootstrap deadlock.
    // =========================================================================
    pll_subsystem #(
        .PLL_IMPL        (PLL_IMPL),
        .STUB_LOCK_CYCLES(16),
        .ADDR_W          (12)
    ) u_pll_sub (
        // Reference clock domain — NOT core_clk (see note above)
        .clk_i       (clk_i),
        .rst_n_i     (rst_n_i),
        // DFT test controls (j41m.2)
        .scan_mode_i (dft_scan_mode),
        .scan_rst_ni (dft_scan_rst_n),
        .scan_clk_i  (dft_test_clk),
        .ref_clk_o   (pll_ref_clk),
        // APB4 slave. It takes the m face of u_apb_pll_cdc, in the clk_i domain.
        .psel        (pll_m_psel),
        .penable     (pll_m_penable),
        .pwrite      (pll_m_pwrite),
        .paddr       (pll_m_paddr),
        .pwdata      (pll_m_pwdata),
        .pstrb       (pll_m_pstrb),
        .prdata      (pll_m_prdata),
        .pready      (pll_m_pready),
        .pslverr     (pll_m_pslverr),
        // PLL outputs → soc_top distribution
        .core_clk    (core_clk),
        .core_rst_n  (core_rst_n),
        .pll_locked_o(pll_locked)
    );

    // Export PLL lock status to top-level port
    assign pll_locked_o = pll_locked;

    // =========================================================================
    // APB4 CDC bridge for the APB_PLL2 slot (u_apb_pll2_cdc).
    // apb_cdc_bridge crosses the APB_PLL2 slot. The s face uses core_clk. The m face uses cpu_clk_i, the raw reference of u_cpu_pll_sub.
    // =========================================================================
    logic        pll2_m_psel, pll2_m_penable, pll2_m_pwrite;
    logic [11:0] pll2_m_paddr;
    logic [31:0] pll2_m_pwdata, pll2_m_prdata;
    logic [3:0]  pll2_m_pstrb;
    logic        pll2_m_pready, pll2_m_pslverr;

    apb_cdc_bridge #(
        .ADDR_W (12)
    ) u_apb_pll2_cdc (
        .scanmode_i  (dft_scan_mode),
        .scan_rst_ni (dft_scan_rst_n),

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

        .m_clk_i     (cpu_pll_ref_clk),
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
    // Second pll_subsystem, on the CPU-domain reference. Everything inside runs on cpu_clk_i and cpu_rst_n_i.
    // cpu_core_clk and cpu_core_rst_n feed u_cpu_cg and the CPU-domain reset tree. cpu_pll_locked goes to cpu_pll_locked_o.
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
        // DFT test controls (j41m.2)
        .scan_mode_i (dft_scan_mode),
        .scan_rst_ni (dft_scan_rst_n),
        .scan_clk_i  (dft_test_clk),
        .ref_clk_o   (cpu_pll_ref_clk),
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
        // PLL outputs. They feed u_cpu_cg and the CPU-domain reset tree.
        .core_clk    (cpu_core_clk),
        .core_rst_n  (cpu_core_rst_n),
        .pll_locked_o(cpu_pll_locked)
    );

    // Export CPU-domain PLL lock status to top-level port
    assign cpu_pll_locked_o = cpu_pll_locked;

    // =========================================================================
    // PMU. It runs on core_clk and core_rst_n. It must never be clock-gated or held in a domain reset.
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
        .cpu_iso_ack_i       (pmu_cpu_iso_ack),
        // GPU domain sequencing (PD_GPU)
        .gpu_clk_en_o        (pmu_gpu_clk_en),
        .gpu_iso_en_o        (pmu_gpu_iso_en),
        .gpu_rst_n_o         (pmu_gpu_rst_n),
        .gpu_ret_save_o      (pmu_gpu_ret_save),
        .gpu_ret_restore_o   (pmu_gpu_ret_restore)
    );

    // u_cpu_cg and u_gpu_cg are clock gates that the PMU clk_en enables. At the reset default they are transparent.
    // u_cpu_cg runs on cpu_core_clk. Its enable is ~pmu_cpu_clk_dis_sync ANDed with pmu_cpu_rst_n_cpu_sync.
    // u_gpu_cg stays on core_clk with pmu_gpu_clk_en.
    // cpu_gated_clk_en is a same-clock AND of two flops, so the ICG enable is glitch-free.
    logic cpu_gated_clk_en;
    assign cpu_gated_clk_en = ~pmu_cpu_clk_dis_sync & pmu_cpu_rst_n_cpu_sync;

    // dft_test_en forces both gates open in test mode. With MBIST_CPU=1 the CPU MBIST run also forces u_cpu_cg open.
    // cpu_gated_clk is a CTS root. u_gpu_cg stays behavioural.
    // The CPU MBIST force is held through cpu_mbist_busy until the controller has cleared.
    logic cpu_mbist_busy;
    logic cpu_cg_en;
    assign cpu_mbist_busy = MBIST_CPU ? (mb_cpu_status[0] | mb_cpu_status[1]) : 1'b0;
    assign cpu_cg_en = cpu_gated_clk_en | (MBIST_CPU ? mbist_force : 1'b0) | cpu_mbist_busy;
    rv32i_clock_gate #(.HARD_ROOT(1'b1)) u_cpu_cg (.en(cpu_cg_en), .test_en(dft_test_en), .clk(cpu_core_clk), .gclk(cpu_gated_clk));
    rv32i_clock_gate u_gpu_cg (.en(pmu_gpu_clk_en),   .test_en(dft_test_en), .clk(core_clk),     .gclk(gpu_gated_clk));

endmodule : soc_top
