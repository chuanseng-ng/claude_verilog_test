// soc_bus.sv
// SoC Bus Fabric Wrapper — Phase 5 / APB migration PR-7 structural refactor.
//
// Wraps the five bus modules that were previously instantiated inline in soc_top:
//   1. axi4_crossbar      — AXI4 data fabric (4 masters × 3 slaves)
//   2. axi4_to_axilite    — crossbar S2 (periph) → AXI-Lite master
//   3. axi_lite_interconnect — AXI-Lite ring (3 slaves: GPU, APB_BRIDGE, DMA)
//   4. axil_to_apb        — AXI-Lite ring slot 1 → APB master
//   5. apb_interconnect   — APB master → 5 APB peripheral slaves
//
// This is a PURE STRUCTURAL WRAPPER.  No logic is added or removed.
// Every signal that crossed the soc_top/bus boundary is an explicit port here.
//
// Port groups (matching soc_top's wire naming):
//   clk / rst_n              — single clock domain (core_clk / core_rst_n)
//   AXI4 master-facing [N_MASTERS]   — crossbar master ports (from CPU/GPU/DMA)
//   AXI4 slave-facing  [N_SLAVES]    — crossbar slave ports (to ROM/SRAM/periph)
//   AXI-Lite [AXIL_GPU] / [AXIL_DMA] — ring slaves that remain AXI-Lite direct
//   APB [N_APB_SLV]                  — per-peripheral APB ports
//
// Address-map packages (soc_addr_map_pkg, soc_periph_map_pkg) are used directly
// for all parameters — soc_bus is the single source of truth for fabric sizing.
//
// Lint: verilator -Wall 0 errors 0 warnings (same baseline as pre-refactor).

`default_nettype none

module soc_bus
    import axi_pkg::*;
    import soc_addr_map_pkg::*;
    import soc_periph_map_pkg::*;
#(
    // Number of AXI4 masters (M0=CPU, M1=GPU-ifetch, M2=GPU-data, M3=DMA).
    // Must match soc_top's N_MASTERS localparam.
    parameter int unsigned N_MASTERS = 4
) (
    input  logic clk,
    input  logic rst_n,

    // =========================================================================
    // AXI4 master-facing ports [N_MASTERS=4]: crossbar master side
    //   M0=CPU, M1=GPU-ifetch, M2=GPU-data, M3=DMA
    // =========================================================================
    // Write address
    input  logic [AXI_ADDR_WIDTH-1:0]  m_awaddr  [N_MASTERS],
    input  logic [AXI_LEN_WIDTH-1:0]   m_awlen   [N_MASTERS],
    input  logic [2:0]                 m_awsize  [N_MASTERS],
    input  logic [1:0]                 m_awburst [N_MASTERS],
    input  logic                       m_awvalid [N_MASTERS],
    output logic                       m_awready [N_MASTERS],
    // Write data
    input  logic [AXI_DATA_WIDTH-1:0]  m_wdata   [N_MASTERS],
    input  logic [AXI_STRB_WIDTH-1:0]  m_wstrb   [N_MASTERS],
    input  logic                       m_wlast   [N_MASTERS],
    input  logic                       m_wvalid  [N_MASTERS],
    output logic                       m_wready  [N_MASTERS],
    // Write response
    output logic [1:0]                 m_bresp   [N_MASTERS],
    output logic                       m_bvalid  [N_MASTERS],
    input  logic                       m_bready  [N_MASTERS],
    // Read address
    input  logic [AXI_ADDR_WIDTH-1:0]  m_araddr  [N_MASTERS],
    input  logic [AXI_LEN_WIDTH-1:0]   m_arlen   [N_MASTERS],
    input  logic [2:0]                 m_arsize  [N_MASTERS],
    input  logic [1:0]                 m_arburst [N_MASTERS],
    input  logic                       m_arvalid [N_MASTERS],
    output logic                       m_arready [N_MASTERS],
    // Read data
    output logic [AXI_DATA_WIDTH-1:0]  m_rdata   [N_MASTERS],
    output logic [1:0]                 m_rresp   [N_MASTERS],
    output logic                       m_rlast   [N_MASTERS],
    output logic                       m_rvalid  [N_MASTERS],
    input  logic                       m_rready  [N_MASTERS],

    // =========================================================================
    // AXI4 slave-facing ports — S0 (ROM) and S1 (SRAM) only.
    // S2 (SLV_PERIPH) is consumed internally by the axi4_to_axilite bridge
    // and is therefore not exposed as a port.
    // Naming: rom_* for SLV_ROM, mem_* for SLV_SRAM.
    // =========================================================================
    // --- ROM (S0 = SLV_ROM) ---
    output logic [AXI_ID_WIDTH-1:0]   rom_awid,
    output logic [AXI_ADDR_WIDTH-1:0] rom_awaddr,
    output logic [AXI_LEN_WIDTH-1:0]  rom_awlen,
    output logic [2:0]                rom_awsize,
    output logic [1:0]                rom_awburst,
    output logic                      rom_awvalid,
    input  logic                      rom_awready,
    output logic [AXI_DATA_WIDTH-1:0] rom_wdata,
    output logic [AXI_STRB_WIDTH-1:0] rom_wstrb,
    output logic                      rom_wlast,
    output logic                      rom_wvalid,
    input  logic                      rom_wready,
    input  logic [AXI_ID_WIDTH-1:0]   rom_bid,
    input  logic [1:0]                rom_bresp,
    input  logic                      rom_bvalid,
    output logic                      rom_bready,
    output logic [AXI_ID_WIDTH-1:0]   rom_arid,
    output logic [AXI_ADDR_WIDTH-1:0] rom_araddr,
    output logic [AXI_LEN_WIDTH-1:0]  rom_arlen,
    output logic [2:0]                rom_arsize,
    output logic [1:0]                rom_arburst,
    output logic                      rom_arvalid,
    input  logic                      rom_arready,
    input  logic [AXI_ID_WIDTH-1:0]   rom_rid,
    input  logic [AXI_DATA_WIDTH-1:0] rom_rdata,
    input  logic [1:0]                rom_rresp,
    input  logic                      rom_rlast,
    input  logic                      rom_rvalid,
    output logic                      rom_rready,
    // --- SRAM (S1 = SLV_SRAM) ---
    output logic [AXI_ID_WIDTH-1:0]   mem_awid,
    output logic [AXI_ADDR_WIDTH-1:0] mem_awaddr,
    output logic [AXI_LEN_WIDTH-1:0]  mem_awlen,
    output logic [2:0]                mem_awsize,
    output logic [1:0]                mem_awburst,
    output logic                      mem_awvalid,
    input  logic                      mem_awready,
    output logic [AXI_DATA_WIDTH-1:0] mem_wdata,
    output logic [AXI_STRB_WIDTH-1:0] mem_wstrb,
    output logic                      mem_wlast,
    output logic                      mem_wvalid,
    input  logic                      mem_wready,
    input  logic [AXI_ID_WIDTH-1:0]   mem_bid,
    input  logic [1:0]                mem_bresp,
    input  logic                      mem_bvalid,
    output logic                      mem_bready,
    output logic [AXI_ID_WIDTH-1:0]   mem_arid,
    output logic [AXI_ADDR_WIDTH-1:0] mem_araddr,
    output logic [AXI_LEN_WIDTH-1:0]  mem_arlen,
    output logic [2:0]                mem_arsize,
    output logic [1:0]                mem_arburst,
    output logic                      mem_arvalid,
    input  logic                      mem_arready,
    input  logic [AXI_ID_WIDTH-1:0]   mem_rid,
    input  logic [AXI_DATA_WIDTH-1:0] mem_rdata,
    input  logic [1:0]                mem_rresp,
    input  logic                      mem_rlast,
    input  logic                      mem_rvalid,
    output logic                      mem_rready,

    // =========================================================================
    // AXI-Lite slave ports for GPU ctrl (AXIL_GPU=0) — AXI-Lite direct ring slave
    // =========================================================================
    output logic [AXI_ADDR_WIDTH-1:0] axil_gpu_awaddr,
    output logic [2:0]                axil_gpu_awprot,
    output logic                      axil_gpu_awvalid,
    input  logic                      axil_gpu_awready,
    output logic [AXI_DATA_WIDTH-1:0] axil_gpu_wdata,
    output logic [AXI_STRB_WIDTH-1:0] axil_gpu_wstrb,
    output logic                      axil_gpu_wvalid,
    input  logic                      axil_gpu_wready,
    input  logic [1:0]                axil_gpu_bresp,
    input  logic                      axil_gpu_bvalid,
    output logic                      axil_gpu_bready,
    output logic [AXI_ADDR_WIDTH-1:0] axil_gpu_araddr,
    output logic [2:0]                axil_gpu_arprot,
    output logic                      axil_gpu_arvalid,
    input  logic                      axil_gpu_arready,
    input  logic [AXI_DATA_WIDTH-1:0] axil_gpu_rdata,
    input  logic [1:0]                axil_gpu_rresp,
    input  logic                      axil_gpu_rvalid,
    output logic                      axil_gpu_rready,

    // =========================================================================
    // AXI-Lite slave ports for DMA ctrl (AXIL_DMA=2) — AXI-Lite direct ring slave
    // =========================================================================
    output logic [AXI_ADDR_WIDTH-1:0] axil_dma_awaddr,
    output logic [2:0]                axil_dma_awprot,
    output logic                      axil_dma_awvalid,
    input  logic                      axil_dma_awready,
    output logic [AXI_DATA_WIDTH-1:0] axil_dma_wdata,
    output logic [AXI_STRB_WIDTH-1:0] axil_dma_wstrb,
    output logic                      axil_dma_wvalid,
    input  logic                      axil_dma_wready,
    input  logic [1:0]                axil_dma_bresp,
    input  logic                      axil_dma_bvalid,
    output logic                      axil_dma_bready,
    output logic [AXI_ADDR_WIDTH-1:0] axil_dma_araddr,
    output logic [2:0]                axil_dma_arprot,
    output logic                      axil_dma_arvalid,
    input  logic                      axil_dma_arready,
    input  logic [AXI_DATA_WIDTH-1:0] axil_dma_rdata,
    input  logic [1:0]                axil_dma_rresp,
    input  logic                      axil_dma_rvalid,
    output logic                      axil_dma_rready,

    // =========================================================================
    // APB peripheral ports [N_APB_SLV=5]: from apb_interconnect to peripherals
    //   APB_UART=0  APB_SPI=1  APB_TIMER=2  APB_IRQ=3  APB_PLL=4
    // =========================================================================
    output logic        apb_psel    [APB_N_SLAVES],
    output logic        apb_penable [APB_N_SLAVES],
    output logic        apb_pwrite  [APB_N_SLAVES],
    output logic [31:0] apb_paddr   [APB_N_SLAVES],
    output logic [31:0] apb_pwdata  [APB_N_SLAVES],
    output logic [3:0]  apb_pstrb   [APB_N_SLAVES],
    input  logic [31:0] apb_prdata  [APB_N_SLAVES],
    input  logic        apb_pready  [APB_N_SLAVES],
    input  logic        apb_pslverr [APB_N_SLAVES]
);

    // =========================================================================
    // Local dimension constants (from imported packages; N_MASTERS is a parameter)
    // =========================================================================
    localparam int unsigned N_SLAVES   = SOC_N_SLAVES;    // 3
    localparam int unsigned N_AXIL_SLV = AXIL_N_SLAVES;   // 3
    localparam int unsigned N_APB_SLV  = APB_N_SLAVES;    // 5
    localparam int unsigned AW         = AXI_ADDR_WIDTH;
    localparam int unsigned DW         = AXI_DATA_WIDTH;
    localparam int unsigned SW         = AXI_STRB_WIDTH;
    localparam int unsigned IW         = AXI_ID_WIDTH;
    localparam int unsigned LENW       = AXI_LEN_WIDTH;

    // =========================================================================
    // Internal: full AXI4 crossbar slave-facing arrays [N_SLAVES=3]
    // S0=ROM, S1=SRAM exposed via flat rom_*/mem_* ports.
    // S2=SLV_PERIPH consumed by internal axi4_to_axilite bridge.
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
    // Connect flat ROM ports ↔ internal crossbar slave array [SLV_ROM]
    // =========================================================================
    assign rom_awid                   = xbar_s_awid    [SLV_ROM];
    assign rom_awaddr                 = xbar_s_awaddr  [SLV_ROM];
    assign rom_awlen                  = xbar_s_awlen   [SLV_ROM];
    assign rom_awsize                 = xbar_s_awsize  [SLV_ROM];
    assign rom_awburst                = xbar_s_awburst [SLV_ROM];
    assign rom_awvalid                = xbar_s_awvalid [SLV_ROM];
    assign xbar_s_awready [SLV_ROM]  = rom_awready;
    assign rom_wdata                  = xbar_s_wdata   [SLV_ROM];
    assign rom_wstrb                  = xbar_s_wstrb   [SLV_ROM];
    assign rom_wlast                  = xbar_s_wlast   [SLV_ROM];
    assign rom_wvalid                 = xbar_s_wvalid  [SLV_ROM];
    assign xbar_s_wready  [SLV_ROM]  = rom_wready;
    assign xbar_s_bid     [SLV_ROM]  = rom_bid;
    assign xbar_s_bresp   [SLV_ROM]  = rom_bresp;
    assign xbar_s_bvalid  [SLV_ROM]  = rom_bvalid;
    assign rom_bready                 = xbar_s_bready  [SLV_ROM];
    assign rom_arid                   = xbar_s_arid    [SLV_ROM];
    assign rom_araddr                 = xbar_s_araddr  [SLV_ROM];
    assign rom_arlen                  = xbar_s_arlen   [SLV_ROM];
    assign rom_arsize                 = xbar_s_arsize  [SLV_ROM];
    assign rom_arburst                = xbar_s_arburst [SLV_ROM];
    assign rom_arvalid                = xbar_s_arvalid [SLV_ROM];
    assign xbar_s_arready [SLV_ROM]  = rom_arready;
    assign xbar_s_rid     [SLV_ROM]  = rom_rid;
    assign xbar_s_rdata   [SLV_ROM]  = rom_rdata;
    assign xbar_s_rresp   [SLV_ROM]  = rom_rresp;
    assign xbar_s_rlast   [SLV_ROM]  = rom_rlast;
    assign xbar_s_rvalid  [SLV_ROM]  = rom_rvalid;
    assign rom_rready                 = xbar_s_rready  [SLV_ROM];

    // =========================================================================
    // Connect flat SRAM ports ↔ internal crossbar slave array [SLV_SRAM]
    // =========================================================================
    assign mem_awid                    = xbar_s_awid    [SLV_SRAM];
    assign mem_awaddr                  = xbar_s_awaddr  [SLV_SRAM];
    assign mem_awlen                   = xbar_s_awlen   [SLV_SRAM];
    assign mem_awsize                  = xbar_s_awsize  [SLV_SRAM];
    assign mem_awburst                 = xbar_s_awburst [SLV_SRAM];
    assign mem_awvalid                 = xbar_s_awvalid [SLV_SRAM];
    assign xbar_s_awready [SLV_SRAM]  = mem_awready;
    assign mem_wdata                   = xbar_s_wdata   [SLV_SRAM];
    assign mem_wstrb                   = xbar_s_wstrb   [SLV_SRAM];
    assign mem_wlast                   = xbar_s_wlast   [SLV_SRAM];
    assign mem_wvalid                  = xbar_s_wvalid  [SLV_SRAM];
    assign xbar_s_wready  [SLV_SRAM]  = mem_wready;
    assign xbar_s_bid     [SLV_SRAM]  = mem_bid;
    assign xbar_s_bresp   [SLV_SRAM]  = mem_bresp;
    assign xbar_s_bvalid  [SLV_SRAM]  = mem_bvalid;
    assign mem_bready                  = xbar_s_bready  [SLV_SRAM];
    assign mem_arid                    = xbar_s_arid    [SLV_SRAM];
    assign mem_araddr                  = xbar_s_araddr  [SLV_SRAM];
    assign mem_arlen                   = xbar_s_arlen   [SLV_SRAM];
    assign mem_arsize                  = xbar_s_arsize  [SLV_SRAM];
    assign mem_arburst                 = xbar_s_arburst [SLV_SRAM];
    assign mem_arvalid                 = xbar_s_arvalid [SLV_SRAM];
    assign xbar_s_arready [SLV_SRAM]  = mem_arready;
    assign xbar_s_rid     [SLV_SRAM]  = mem_rid;
    assign xbar_s_rdata   [SLV_SRAM]  = mem_rdata;
    assign xbar_s_rresp   [SLV_SRAM]  = mem_rresp;
    assign xbar_s_rlast   [SLV_SRAM]  = mem_rlast;
    assign xbar_s_rvalid  [SLV_SRAM]  = mem_rvalid;
    assign mem_rready                  = xbar_s_rready  [SLV_SRAM];

    // =========================================================================
    // Internal: axi4_to_axilite bridge output → axi_lite_interconnect master
    // =========================================================================
    logic [AW-1:0]  periph_axil_awaddr;
    logic [2:0]     periph_axil_awprot;
    logic           periph_axil_awvalid;
    logic           periph_axil_awready;
    logic [DW-1:0]  periph_axil_wdata;
    logic [SW-1:0]  periph_axil_wstrb;
    logic           periph_axil_wvalid;
    logic           periph_axil_wready;
    logic [1:0]     periph_axil_bresp;
    logic           periph_axil_bvalid;
    logic           periph_axil_bready;
    logic [AW-1:0]  periph_axil_araddr;
    logic [2:0]     periph_axil_arprot;
    logic           periph_axil_arvalid;
    logic           periph_axil_arready;
    logic [DW-1:0]  periph_axil_rdata;
    logic [1:0]     periph_axil_rresp;
    logic           periph_axil_rvalid;
    logic           periph_axil_rready;

    // =========================================================================
    // Internal: axi_lite_interconnect slave-facing arrays [N_AXIL_SLV=3]
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
    // Internal: axil_to_apb bridge single APB master output
    // =========================================================================
    logic        apb_m_psel;
    logic        apb_m_penable;
    logic        apb_m_pwrite;
    logic [31:0] apb_m_paddr;
    logic [31:0] apb_m_pwdata;
    logic [3:0]  apb_m_pstrb;
    logic [31:0] apb_m_prdata;
    logic        apb_m_pready;
    logic        apb_m_pslverr;

    // =========================================================================
    // Connect ring-slave arrays to flat module ports (GPU and DMA)
    // =========================================================================

    // AXIL_GPU ring slave → axil_gpu_* ports
    assign axil_gpu_awaddr              = axil_s_awaddr  [AXIL_GPU];
    assign axil_gpu_awprot              = axil_s_awprot  [AXIL_GPU];
    assign axil_gpu_awvalid             = axil_s_awvalid [AXIL_GPU];
    assign axil_s_awready [AXIL_GPU]   = axil_gpu_awready;
    assign axil_gpu_wdata               = axil_s_wdata   [AXIL_GPU];
    assign axil_gpu_wstrb               = axil_s_wstrb   [AXIL_GPU];
    assign axil_gpu_wvalid              = axil_s_wvalid  [AXIL_GPU];
    assign axil_s_wready  [AXIL_GPU]   = axil_gpu_wready;
    assign axil_s_bresp   [AXIL_GPU]   = axil_gpu_bresp;
    assign axil_s_bvalid  [AXIL_GPU]   = axil_gpu_bvalid;
    assign axil_gpu_bready              = axil_s_bready  [AXIL_GPU];
    assign axil_gpu_araddr              = axil_s_araddr  [AXIL_GPU];
    assign axil_gpu_arprot              = axil_s_arprot  [AXIL_GPU];
    assign axil_gpu_arvalid             = axil_s_arvalid [AXIL_GPU];
    assign axil_s_arready [AXIL_GPU]   = axil_gpu_arready;
    assign axil_s_rdata   [AXIL_GPU]   = axil_gpu_rdata;
    assign axil_s_rresp   [AXIL_GPU]   = axil_gpu_rresp;
    assign axil_s_rvalid  [AXIL_GPU]   = axil_gpu_rvalid;
    assign axil_gpu_rready              = axil_s_rready  [AXIL_GPU];

    // AXIL_DMA ring slave → axil_dma_* ports
    assign axil_dma_awaddr              = axil_s_awaddr  [AXIL_DMA];
    assign axil_dma_awprot              = axil_s_awprot  [AXIL_DMA];
    assign axil_dma_awvalid             = axil_s_awvalid [AXIL_DMA];
    assign axil_s_awready [AXIL_DMA]   = axil_dma_awready;
    assign axil_dma_wdata               = axil_s_wdata   [AXIL_DMA];
    assign axil_dma_wstrb               = axil_s_wstrb   [AXIL_DMA];
    assign axil_dma_wvalid              = axil_s_wvalid  [AXIL_DMA];
    assign axil_s_wready  [AXIL_DMA]   = axil_dma_wready;
    assign axil_s_bresp   [AXIL_DMA]   = axil_dma_bresp;
    assign axil_s_bvalid  [AXIL_DMA]   = axil_dma_bvalid;
    assign axil_dma_bready              = axil_s_bready  [AXIL_DMA];
    assign axil_dma_araddr              = axil_s_araddr  [AXIL_DMA];
    assign axil_dma_arprot              = axil_s_arprot  [AXIL_DMA];
    assign axil_dma_arvalid             = axil_s_arvalid [AXIL_DMA];
    assign axil_s_arready [AXIL_DMA]   = axil_dma_arready;
    assign axil_s_rdata   [AXIL_DMA]   = axil_dma_rdata;
    assign axil_s_rresp   [AXIL_DMA]   = axil_dma_rresp;
    assign axil_s_rvalid  [AXIL_DMA]   = axil_dma_rvalid;
    assign axil_dma_rready              = axil_s_rready  [AXIL_DMA];

    // =========================================================================
    // 1. AXI4 crossbar
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
        .clk        (clk),
        .rst_n      (rst_n),
        // Master-facing ports (from CPU/GPU/DMA)
        .m_awaddr   (m_awaddr),
        .m_awlen    (m_awlen),
        .m_awsize   (m_awsize),
        .m_awburst  (m_awburst),
        .m_awvalid  (m_awvalid),
        .m_awready  (m_awready),
        .m_wdata    (m_wdata),
        .m_wstrb    (m_wstrb),
        .m_wlast    (m_wlast),
        .m_wvalid   (m_wvalid),
        .m_wready   (m_wready),
        .m_bresp    (m_bresp),
        .m_bvalid   (m_bvalid),
        .m_bready   (m_bready),
        .m_araddr   (m_araddr),
        .m_arlen    (m_arlen),
        .m_arsize   (m_arsize),
        .m_arburst  (m_arburst),
        .m_arvalid  (m_arvalid),
        .m_arready  (m_arready),
        .m_rdata    (m_rdata),
        .m_rresp    (m_rresp),
        .m_rlast    (m_rlast),
        .m_rvalid   (m_rvalid),
        .m_rready   (m_rready),
        // Slave-facing ports (S0=ROM, S1=SRAM exposed via flat ports; S2=periph internal)
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
    // 2. axi4_to_axilite bridge (crossbar S2=SLV_PERIPH → AXI-Lite master)
    // =========================================================================
    axi4_to_axilite u_periph_bridge (
        .clk                        (clk),
        .rst_n                      (rst_n),
        // AXI4 slave ← crossbar SLV_PERIPH (internal array)
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
    // 3. AXI4-Lite interconnect (1 master → 3 ring slaves: GPU, APB_BRIDGE, DMA)
    // =========================================================================
    axi_lite_interconnect #(
        .N_SLAVES   (N_AXIL_SLV),
        .SLV_BASE   (AXIL_SLV_BASE),
        .SLV_LIMIT  (AXIL_SLV_LIMIT)
    ) u_axil_ic (
        .clk                (clk),
        .rst_n              (rst_n),
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
        // Slave-facing ports (all three ring slots: GPU, APB_BRIDGE, DMA)
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
    // 4. axil_to_apb bridge (ring AXIL_APB_BRIDGE slot → APB master)
    // =========================================================================
    axil_to_apb #(
        .ADDR_W (32),
        .DW     (32),
        .SW     (4)
    ) u_axil_apb_bridge (
        .clk            (clk),
        .rst_n          (rst_n),
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
    // 5. APB interconnect: 1 APB master → 5 APB peripheral slaves
    //   APB_UART=0  APB_SPI=1  APB_TIMER=2  APB_IRQ=3  APB_PLL=4
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
        // Per-slave APB outputs (exposed at module boundary)
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

endmodule : soc_bus
