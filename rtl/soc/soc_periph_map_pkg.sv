// soc_periph_map_pkg.sv
// Phase 5 (M1/M3) — AXI-Lite control-ring + APB peripheral sub-map.
//
// Phase 6 (bead claude_verilog_test-f7vs.2): the full 14-slave APB sub-tree is
// pre-allocated in this one commit, per docs/PHASE6_IP_EXPANSION_PLAN.md §4.
// Slots 11-13 (I2C/CRYPTO/NPU) are BASE/LIMIT constants only —
// reserved-but-unbuilt, not yet in APB_N_SLAVES or the APB_SLV_BASE/LIMIT
// arrays. Slots 8-10 (PWM, WDT, TRNG) are live. Each reserved slot is promoted to a
// real slave (index constant + array entry + module instance) one at a time as
// its peripheral lands (6a-4 .. 6c).
//
// APB migration PR-7 topology (GH #92: +PLL2 slot, dual-PLL clock seam):
//   AXI-Lite ring (3 slaves): GPU, DMA, APB-bridge window
//     Slave 0: GPU ctrl    0x2000_1000 .. 0x2000_1FFF
//     Slave 1: APB bridge  0x2000_2000 .. 0x2001_0FFF  (covers the full 14-slot APB window)
//     Slave 2: DMA ctrl    0x2000_5000 .. 0x2000_5FFF
//
//   Note on overlapping window: DMA (index 2) overlaps the APB-bridge window.
//   axi_lite_interconnect's decode() iterates 0→N-1 and takes the LAST match,
//   so DMA (highest index) wins for 0x2000_5000-5FFF.  All other addresses in
//   _2000-_0FFF route to APB_BRIDGE (index 1).
//
//   APB sub-map, final 14-slot allocation (decoded by apb_interconnect; only the
//   first 11 are live slaves today — APB_N_SLAVES stays 11 until the next slot lands):
//     APB_UART    0: 0x2000_2000 .. 0x2000_2FFF                        (Phase 5)
//     APB_SPI     1: 0x2000_3000 .. 0x2000_3FFF                        (Phase 5)
//     APB_TIMER   2: 0x2000_4000 .. 0x2000_4FFF                        (Phase 5)
//     APB_IRQ     3: 0x2000_6000 .. 0x2000_6FFF                        (Phase 5)
//     APB_PLL     4: 0x2000_7000 .. 0x2000_7FFF                        (Phase 7 M-c)
//     APB_PMU     5: 0x2000_8000 .. 0x2000_8FFF                        (GH #100)
//     APB_PLL2    6: 0x2000_9000 .. 0x2000_9FFF  (CPU-domain PLL config, GH #92)
//     APB_GPIO    7: 0x2000_A000 .. 0x2000_AFFF                        (6a, bead ckc)
//     APB_PWM     8: 0x2000_B000 .. 0x2000_BFFF                        (6a-2, bead f7vs.6)
//     APB_WDT     9: 0x2000_C000 .. 0x2000_CFFF                        (6a-3, bead f7vs.7)
//     APB_TRNG   10: 0x2000_D000 .. 0x2000_DFFF                        (6a-4, bead f7vs.8)
//     I2C        11: 0x2000_E000 .. 0x2000_EFFF  reserved              (6a-5)
//     CRYPTO     12: 0x2000_F000 .. 0x2000_FFFF  reserved              (6b)
//     NPU        13: 0x2001_0000 .. 0x2001_0FFF  reserved              (6c)
//
//   The window deliberately crosses out of 0x2000_xxxx into 0x2001_0FFF at the
//   14th slave (NPU). Verified inert: paddr is 32 bits end to end — both
//   axil_to_apb and apb_interconnect are instantiated with .ADDR_W(32)
//   (rtl/soc/soc_bus.sv:608,652) — and each peripheral consumes only
//   paddr[11:0], so the upper-byte rollover carries no decode meaning.
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
    // APB bridge window — covers all APB peripheral slots (8 × 4 KB).
    // DMA (index 2, checked last) takes priority for 0x2000_5000-5FFF.
    // Pre-Phase-6 #5 / GH #100: extended 0x2000_7FFF -> 0x2000_8FFF for PMU.
    // GH #92: extended 0x2000_8FFF -> 0x2000_9FFF for the second (CPU-domain) PLL.
    // Phase 6a / bead claude_verilog_test-ckc: extended 0x2000_9FFF -> 0x2000_AFFF for GPIO.
    // Phase 6 / bead claude_verilog_test-f7vs.2: extended 0x2000_AFFF -> 0x2001_0FFF, the
    // final value — pre-allocates the full 14-slot APB window (PWM/WDT/TRNG/I2C/CRYPTO/NPU)
    // in one commit per docs/PHASE6_IP_EXPANSION_PLAN.md §4.
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
    localparam int unsigned APB_PMU   = 5;  // Pre-Phase-6 #5 / GH #100
    localparam int unsigned APB_PLL2  = 6;  // GH #92 — CPU-domain PLL config
    localparam int unsigned APB_GPIO  = 7;  // Phase 6a — bead claude_verilog_test-ckc
    localparam int unsigned APB_PWM   = 8;  // Phase 6a-2 — bead claude_verilog_test-f7vs.6
    localparam int unsigned APB_WDT   = 9;  // Phase 6a-3 — bead claude_verilog_test-f7vs.7
    localparam int unsigned APB_TRNG  = 10; // Phase 6a-4 — bead claude_verilog_test-f7vs.8
    /* verilator lint_on  UNUSEDPARAM */
    localparam int unsigned APB_N_SLAVES = 11;

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
    // GPIO — Phase 6a (bead claude_verilog_test-ckc).
    localparam logic [31:0] APB_GPIO_BASE   = 32'h2000_A000;
    localparam logic [31:0] APB_GPIO_LIMIT  = 32'h2000_AFFF;
    // PWM — Phase 6a-2 (bead claude_verilog_test-f7vs.6).
    localparam logic [31:0] APB_PWM_BASE    = 32'h2000_B000;
    localparam logic [31:0] APB_PWM_LIMIT   = 32'h2000_BFFF;
    // WDT — Phase 6a-3 (bead claude_verilog_test-f7vs.7).
    localparam logic [31:0] APB_WDT_BASE    = 32'h2000_C000;
    localparam logic [31:0] APB_WDT_LIMIT   = 32'h2000_CFFF;
    // TRNG — Phase 6a-4 (bead claude_verilog_test-f7vs.8).
    localparam logic [31:0] APB_TRNG_BASE   = 32'h2000_D000;
    localparam logic [31:0] APB_TRNG_LIMIT  = 32'h2000_DFFF;

    // Reserved-but-unbuilt slots 11-13 — pre-allocated by bead claude_verilog_test-f7vs.2
    // (docs/PHASE6_IP_EXPANSION_PLAN.md §4). Not yet in APB_N_SLAVES or the
    // APB_SLV_BASE/LIMIT arrays below; each is wired in one at a time as its
    // peripheral lands. Unused until then, so guarded against UNUSEDPARAM.
    // PWM (was slot 8), WDT (was slot 9) and TRNG (was slot 10) promoted to live slaves by
    // beads claude_verilog_test-f7vs.6 / f7vs.7 / f7vs.8 — their BASE/LIMIT constants moved above,
    // out of this reserved block.
    /* verilator lint_off UNUSEDPARAM */
    localparam logic [31:0] APB_I2C_BASE    = 32'h2000_E000;  // 6a-5
    localparam logic [31:0] APB_I2C_LIMIT   = 32'h2000_EFFF;
    localparam logic [31:0] APB_CRYPTO_BASE = 32'h2000_F000;  // 6b
    localparam logic [31:0] APB_CRYPTO_LIMIT = 32'h2000_FFFF;
    localparam logic [31:0] APB_NPU_BASE    = 32'h2001_0000;  // 6c
    localparam logic [31:0] APB_NPU_LIMIT   = 32'h2001_0FFF;
    /* verilator lint_on  UNUSEDPARAM */

    // Packed arrays for apb_interconnect instantiation.
    localparam logic [31:0] APB_SLV_BASE  [APB_N_SLAVES] = '{
        APB_UART_BASE,  APB_SPI_BASE,  APB_TIMER_BASE,
        APB_IRQ_BASE,   APB_PLL_BASE,  APB_PMU_BASE,  APB_PLL2_BASE, APB_GPIO_BASE, APB_PWM_BASE,
        APB_WDT_BASE, APB_TRNG_BASE};
    localparam logic [31:0] APB_SLV_LIMIT [APB_N_SLAVES] = '{
        APB_UART_LIMIT, APB_SPI_LIMIT, APB_TIMER_LIMIT,
        APB_IRQ_LIMIT,  APB_PLL_LIMIT, APB_PMU_LIMIT, APB_PLL2_LIMIT, APB_GPIO_LIMIT, APB_PWM_LIMIT,
        APB_WDT_LIMIT, APB_TRNG_LIMIT};

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
