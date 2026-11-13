// soc_periph_map_pkg - AXI-Lite control-ring and APB peripheral sub-map.
//
// Function: The package gives the base and limit of each AXI-Lite ring slave and of each APB slave.
//   The ring has three slaves: GPU control, the APB bridge window and DMA control.
//   The APB sub-tree has 14 slots, APB_UART=0 up to APB_NPU=13. apb_interconnect decodes them.
// Caller rules:
//   - The DMA window overlaps the APB bridge window. axi_lite_interconnect takes the last match, so DMA wins
//     for 0x2000_5000 to 0x2000_5FFF.
//   - The APB window crosses from 0x2000_xxxx into 0x2001_0FFF at the NPU slot. This is inert.
//     paddr is 32 bits end to end and each peripheral uses only paddr[11:0].
//   - All global MMIO addresses are unchanged from the original 7-slave ring.
// Doc: ds:mod:soc-periph-map-pkg, cr:mod:soc-periph-map-pkg

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
    // APB bridge window — covers all APB peripheral slots (8 × 4 KB).
    // DMA (index 2, checked last) takes priority for 0x2000_5000-5FFF.
    localparam logic [31:0] AXIL_APB_BASE    = 32'h2000_2000;
    localparam logic [31:0] AXIL_APB_LIMIT   = 32'h2001_0FFF;
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
    localparam int unsigned APB_PMU   = 5;  // Added before Phase 6
    localparam int unsigned APB_PLL2  = 6;  // CPU-domain PLL config
    localparam int unsigned APB_GPIO  = 7;  // Phase 6a
    localparam int unsigned APB_PWM   = 8;  // Phase 6a-2
    localparam int unsigned APB_WDT   = 9;  // Phase 6a-3
    localparam int unsigned APB_TRNG  = 10; // Phase 6a-4
    localparam int unsigned APB_I2C   = 11; // Phase 6a-5
    localparam int unsigned APB_CRYPTO = 12; // Phase 6b
    localparam int unsigned APB_NPU    = 13; // Phase 6c
    /* verilator lint_on  UNUSEDPARAM */
    localparam int unsigned APB_N_SLAVES = 14;

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
    // PMU slot.
    localparam logic [31:0] APB_PMU_BASE    = 32'h2000_8000;
    localparam logic [31:0] APB_PMU_LIMIT   = 32'h2000_8FFF;
    // PLL2 slot.
    localparam logic [31:0] APB_PLL2_BASE   = 32'h2000_9000;
    localparam logic [31:0] APB_PLL2_LIMIT  = 32'h2000_9FFF;
    // GPIO slot.
    localparam logic [31:0] APB_GPIO_BASE   = 32'h2000_A000;
    localparam logic [31:0] APB_GPIO_LIMIT  = 32'h2000_AFFF;
    // PWM slot.
    localparam logic [31:0] APB_PWM_BASE    = 32'h2000_B000;
    localparam logic [31:0] APB_PWM_LIMIT   = 32'h2000_BFFF;
    // WDT slot.
    localparam logic [31:0] APB_WDT_BASE    = 32'h2000_C000;
    localparam logic [31:0] APB_WDT_LIMIT   = 32'h2000_CFFF;
    // TRNG slot.
    localparam logic [31:0] APB_TRNG_BASE   = 32'h2000_D000;
    localparam logic [31:0] APB_TRNG_LIMIT  = 32'h2000_DFFF;
    // I2C slot.
    localparam logic [31:0] APB_I2C_BASE    = 32'h2000_E000;
    localparam logic [31:0] APB_I2C_LIMIT   = 32'h2000_EFFF;
    // CRYPTO slot.
    localparam logic [31:0] APB_CRYPTO_BASE = 32'h2000_F000;
    localparam logic [31:0] APB_CRYPTO_LIMIT = 32'h2000_FFFF;
    // NPU slot.
    localparam logic [31:0] APB_NPU_BASE    = 32'h2001_0000;
    localparam logic [31:0] APB_NPU_LIMIT   = 32'h2001_0FFF;

    // Packed arrays for apb_interconnect instantiation.
    localparam logic [31:0] APB_SLV_BASE  [APB_N_SLAVES] = '{
        APB_UART_BASE,  APB_SPI_BASE,  APB_TIMER_BASE,
        APB_IRQ_BASE,   APB_PLL_BASE,  APB_PMU_BASE,  APB_PLL2_BASE, APB_GPIO_BASE, APB_PWM_BASE,
        APB_WDT_BASE, APB_TRNG_BASE, APB_I2C_BASE, APB_CRYPTO_BASE, APB_NPU_BASE};
    localparam logic [31:0] APB_SLV_LIMIT [APB_N_SLAVES] = '{
        APB_UART_LIMIT, APB_SPI_LIMIT, APB_TIMER_LIMIT,
        APB_IRQ_LIMIT,  APB_PLL_LIMIT, APB_PMU_LIMIT, APB_PLL2_LIMIT, APB_GPIO_LIMIT, APB_PWM_LIMIT,
        APB_WDT_LIMIT, APB_TRNG_LIMIT, APB_I2C_LIMIT, APB_CRYPTO_LIMIT, APB_NPU_LIMIT};

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
