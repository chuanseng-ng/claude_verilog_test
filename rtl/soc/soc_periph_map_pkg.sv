// soc_periph_map_pkg.sv
// Phase 5 (M1/M3) — AXI-Lite control-ring + APB peripheral sub-map.
//
// APB migration PR-7 topology (GH #92: +PLL2 slot, dual-PLL clock seam):
//   AXI-Lite ring (3 slaves): GPU, DMA, APB-bridge window
//     Slave 0: GPU ctrl    0x2000_1000 .. 0x2000_1FFF
//     Slave 1: APB bridge  0x2000_2000 .. 0x2000_9FFF  (covers 7 APB perips)
//     Slave 2: DMA ctrl    0x2000_5000 .. 0x2000_5FFF
//
//   Note on overlapping window: DMA (index 2) overlaps the APB-bridge window.
//   axi_lite_interconnect's decode() iterates 0→N-1 and takes the LAST match,
//   so DMA (highest index) wins for 0x2000_5000-5FFF.  All other addresses in
//   _2000-_9FFF route to APB_BRIDGE (index 1).
//
//   APB sub-map (7 slaves, decoded by apb_interconnect):
//     APB_UART  0: 0x2000_2000 .. 0x2000_2FFF
//     APB_SPI   1: 0x2000_3000 .. 0x2000_3FFF
//     APB_TIMER 2: 0x2000_4000 .. 0x2000_4FFF
//     APB_IRQ   3: 0x2000_6000 .. 0x2000_6FFF
//     APB_PLL   4: 0x2000_7000 .. 0x2000_7FFF
//     APB_PMU   5: 0x2000_8000 .. 0x2000_8FFF
//     APB_PLL2  6: 0x2000_9000 .. 0x2000_9FFF  (GH #92 — CPU-domain PLL config)
//
//   All global MMIO addresses are UNCHANGED from the original 7-slave ring.

/* verilator lint_off UNUSEDPARAM */
package soc_periph_map_pkg;
/* verilator lint_on  UNUSEDPARAM */

    import axi_pkg::*;

    // =========================================================================
    // AXI-Lite ring — 3 slaves (PR-7 topology)
    // =========================================================================
    /* verilator lint_off UNUSEDPARAM */
    localparam int unsigned AXIL_GPU        = 0;
    localparam int unsigned AXIL_APB_BRIDGE = 1;
    localparam int unsigned AXIL_DMA        = 2;
    /* verilator lint_on  UNUSEDPARAM */
    localparam int unsigned AXIL_N_SLAVES   = 3;

    // ── AXI-Lite region bounds ───────────────────────────────────────────────
    localparam logic [31:0] AXIL_GPU_BASE    = 32'h2000_1000;
    localparam logic [31:0] AXIL_GPU_LIMIT   = 32'h2000_1FFF;
    // APB bridge window — covers all APB peripheral slots (7 × 4 KB).
    // DMA (index 2, checked last) takes priority for 0x2000_5000-5FFF.
    // Pre-Phase-6 #5 / GH #100: extended 0x2000_7FFF -> 0x2000_8FFF for PMU.
    // GH #92: extended 0x2000_8FFF -> 0x2000_9FFF for the second (CPU-domain) PLL.
    localparam logic [31:0] AXIL_APB_BASE    = 32'h2000_2000;
    localparam logic [31:0] AXIL_APB_LIMIT   = 32'h2000_9FFF;
    localparam logic [31:0] AXIL_DMA_BASE    = 32'h2000_5000;
    localparam logic [31:0] AXIL_DMA_LIMIT   = 32'h2000_5FFF;

    // Packed 2D arrays for axi_lite_interconnect instantiation (index = slave number).
    // Packed [N-1:0][31:0] form (not unpacked) — matches axi_lite_interconnect's
    // packed SLV_BASE/SLV_LIMIT ports and avoids the Synlig/UHDM $mem lowering of
    // unpacked array parameters (empty-named RTLIL wire assert).
    // Concatenation order: MSB = highest index, so index 0 (GPU) is rightmost.
    // Ring slaves: 0 = GPU, 1 = APB bridge, 2 = DMA.
    localparam logic [AXIL_N_SLAVES-1:0][31:0] AXIL_SLV_BASE  =
        {AXIL_DMA_BASE,  AXIL_APB_BASE,  AXIL_GPU_BASE};
    localparam logic [AXIL_N_SLAVES-1:0][31:0] AXIL_SLV_LIMIT =
        {AXIL_DMA_LIMIT, AXIL_APB_LIMIT, AXIL_GPU_LIMIT};

    // =========================================================================
    // APB peripheral sub-map — 5 slaves behind the axil_to_apb bridge
    // =========================================================================
    /* verilator lint_off UNUSEDPARAM */
    localparam int unsigned APB_UART  = 0;
    localparam int unsigned APB_SPI   = 1;
    localparam int unsigned APB_TIMER = 2;
    localparam int unsigned APB_IRQ   = 3;
    localparam int unsigned APB_PLL   = 4;
    localparam int unsigned APB_PMU   = 5;  // Pre-Phase-6 #5 / GH #100
    localparam int unsigned APB_PLL2  = 6;  // GH #92 — CPU-domain PLL config
    /* verilator lint_on  UNUSEDPARAM */
    localparam int unsigned APB_N_SLAVES = 7;

    // ── APB region bounds (preserving original global MMIO addresses) ─────────
    localparam logic [31:0] APB_UART_BASE   = 32'h2000_2000;
    localparam logic [31:0] APB_UART_LIMIT  = 32'h2000_2FFF;
    localparam logic [31:0] APB_SPI_BASE    = 32'h2000_3000;
    localparam logic [31:0] APB_SPI_LIMIT   = 32'h2000_3FFF;
    localparam logic [31:0] APB_TIMER_BASE  = 32'h2000_4000;
    localparam logic [31:0] APB_TIMER_LIMIT = 32'h2000_4FFF;
    localparam logic [31:0] APB_IRQ_BASE    = 32'h2000_6000;
    localparam logic [31:0] APB_IRQ_LIMIT   = 32'h2000_6FFF;
    localparam logic [31:0] APB_PLL_BASE    = 32'h2000_7000;
    localparam logic [31:0] APB_PLL_LIMIT   = 32'h2000_7FFF;
    // PMU — Pre-Phase-6 #5 / GH #100 (behavioral power-mode sequencer, GH #99).
    localparam logic [31:0] APB_PMU_BASE    = 32'h2000_8000;
    localparam logic [31:0] APB_PMU_LIMIT   = 32'h2000_8FFF;
    // PLL2 — GH #92 (second pll_subsystem instance, CPU-domain reference clock).
    localparam logic [31:0] APB_PLL2_BASE   = 32'h2000_9000;
    localparam logic [31:0] APB_PLL2_LIMIT  = 32'h2000_9FFF;

    // Packed arrays for apb_interconnect instantiation.
    localparam logic [31:0] APB_SLV_BASE  [APB_N_SLAVES] = '{
        APB_UART_BASE,  APB_SPI_BASE,  APB_TIMER_BASE,
        APB_IRQ_BASE,   APB_PLL_BASE,  APB_PMU_BASE,  APB_PLL2_BASE};
    localparam logic [31:0] APB_SLV_LIMIT [APB_N_SLAVES] = '{
        APB_UART_LIMIT, APB_SPI_LIMIT, APB_TIMER_LIMIT,
        APB_IRQ_LIMIT,  APB_PLL_LIMIT, APB_PMU_LIMIT, APB_PLL2_LIMIT};

    // =========================================================================
    // Legacy address constants — kept for testbench / firmware compatibility.
    // These are the original global MMIO addresses; routing now goes via APB.
    // =========================================================================
    /* verilator lint_off UNUSEDPARAM */
    localparam logic [31:0] AXIL_UART_BASE   = 32'h2000_2000;
    localparam logic [31:0] AXIL_UART_LIMIT  = 32'h2000_2FFF;
    localparam logic [31:0] AXIL_SPI_BASE    = 32'h2000_3000;
    localparam logic [31:0] AXIL_SPI_LIMIT   = 32'h2000_3FFF;
    localparam logic [31:0] AXIL_TIMER_BASE  = 32'h2000_4000;
    localparam logic [31:0] AXIL_TIMER_LIMIT = 32'h2000_4FFF;
    localparam logic [31:0] AXIL_IRQ_BASE    = 32'h2000_6000;
    localparam logic [31:0] AXIL_IRQ_LIMIT   = 32'h2000_6FFF;
    localparam logic [31:0] AXIL_PLL_BASE    = 32'h2000_7000;
    localparam logic [31:0] AXIL_PLL_LIMIT   = 32'h2000_7FFF;
    /* verilator lint_on  UNUSEDPARAM */

    // ── Reference decode (AXI-Lite ring) ─────────────────────────────────────
    // Returns slave index [0 .. AXIL_N_SLAVES-1], or AXIL_N_SLAVES when the
    // address matches no slave (caller must raise DECERR).
    function automatic int unsigned decode_axil_slave(input logic [31:0] addr);
        // Last-match (mirrors axi_lite_interconnect behaviour):
        // highest-index slave that covers addr wins.
        decode_axil_slave = AXIL_N_SLAVES;
        for (int unsigned s = 0; s < AXIL_N_SLAVES; s++) begin
            if (addr >= AXIL_SLV_BASE[s] && addr <= AXIL_SLV_LIMIT[s]) begin
                decode_axil_slave = s;
            end
        end
    endfunction

endpackage : soc_periph_map_pkg
