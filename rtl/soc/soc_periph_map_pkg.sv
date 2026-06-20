// soc_periph_map_pkg.sv
// Phase 5 (M1/M3) — AXI-Lite control-ring address map.
//
// The Phase 5 peripherals attach to a CPU-driven AXI4-Lite control bus
// (rtl/soc/axi_lite_interconnect.sv), NOT the data crossbar.  This reconciles
// the deferred M1 item (PHASE5_SOC_INTEGRATION_PLAN.md line 66): the original
// MEMORY_MAP.md routed peripherals through an APB3 bridge @0x2000_xxxx, but the
// GPU control port is AXI4-Lite, so the whole ring is AXI-Lite-native.  The
// APB3 interface survives only on the CPU debug slot (0x2000_0000..0FFF).
//
// Region summary (4 KB / slave, local 12-bit addressing):
//   GPU ctrl : 0x2000_1000 .. 0x2000_1FFF
//   UART     : 0x2000_2000 .. 0x2000_2FFF
//   SPI      : 0x2000_3000 .. 0x2000_3FFF
//   Timer    : 0x2000_4000 .. 0x2000_4FFF
//   DMA ctrl : 0x2000_5000 .. 0x2000_5FFF
//   IRQ ctrl : 0x2000_6000 .. 0x2000_6FFF
//
// The interconnect is parameterized with base/limit arrays so it stays reusable;
// the SoC top-level passes the constants below.  decode_axil_slave() is the
// reference model used by the top-level and the testbench.

/* verilator lint_off UNUSEDPARAM */
package soc_periph_map_pkg;
/* verilator lint_on  UNUSEDPARAM */

    import axi_pkg::*;

    // ── Control-ring slave indices ───────────────────────────────────────────
    /* verilator lint_off UNUSEDPARAM */
    localparam int unsigned AXIL_GPU   = 0;
    localparam int unsigned AXIL_UART  = 1;
    localparam int unsigned AXIL_SPI   = 2;
    localparam int unsigned AXIL_TIMER = 3;
    localparam int unsigned AXIL_DMA   = 4;
    localparam int unsigned AXIL_IRQ   = 5;
    localparam int unsigned AXIL_PLL   = 6;  // Phase 7 M-c: PLL config slave
    /* verilator lint_on  UNUSEDPARAM */
    localparam int unsigned AXIL_N_SLAVES = 7;  // was 6; +1 for PLL

    // ── Region bounds (inclusive) ────────────────────────────────────────────
    localparam logic [31:0] AXIL_GPU_BASE    = 32'h2000_1000;
    localparam logic [31:0] AXIL_GPU_LIMIT   = 32'h2000_1FFF;
    localparam logic [31:0] AXIL_UART_BASE   = 32'h2000_2000;
    localparam logic [31:0] AXIL_UART_LIMIT  = 32'h2000_2FFF;
    localparam logic [31:0] AXIL_SPI_BASE    = 32'h2000_3000;
    localparam logic [31:0] AXIL_SPI_LIMIT   = 32'h2000_3FFF;
    localparam logic [31:0] AXIL_TIMER_BASE  = 32'h2000_4000;
    localparam logic [31:0] AXIL_TIMER_LIMIT = 32'h2000_4FFF;
    localparam logic [31:0] AXIL_DMA_BASE    = 32'h2000_5000;
    localparam logic [31:0] AXIL_DMA_LIMIT   = 32'h2000_5FFF;
    localparam logic [31:0] AXIL_IRQ_BASE    = 32'h2000_6000;
    localparam logic [31:0] AXIL_IRQ_LIMIT   = 32'h2000_6FFF;
    // Phase 7 M-c: PLL clock generator config (4 KB slot)
    localparam logic [31:0] AXIL_PLL_BASE    = 32'h2000_7000;
    localparam logic [31:0] AXIL_PLL_LIMIT   = 32'h2000_7FFF;

    // Packed arrays for interconnect instantiation (index = slave number).
    // Phase 7 M-c: extended to 7 entries (index 6 = AXIL_PLL).
    localparam logic [31:0] AXIL_SLV_BASE  [AXIL_N_SLAVES] = '{
        AXIL_GPU_BASE,  AXIL_UART_BASE,  AXIL_SPI_BASE,
        AXIL_TIMER_BASE, AXIL_DMA_BASE,  AXIL_IRQ_BASE, AXIL_PLL_BASE};
    localparam logic [31:0] AXIL_SLV_LIMIT [AXIL_N_SLAVES] = '{
        AXIL_GPU_LIMIT,  AXIL_UART_LIMIT,  AXIL_SPI_LIMIT,
        AXIL_TIMER_LIMIT, AXIL_DMA_LIMIT,  AXIL_IRQ_LIMIT, AXIL_PLL_LIMIT};

    // ── Reference decode ─────────────────────────────────────────────────────
    // Returns slave index [0 .. AXIL_N_SLAVES-1], or AXIL_N_SLAVES when the
    // address matches no slave (caller must raise DECERR).
    function automatic int unsigned decode_axil_slave(input logic [31:0] addr);
        decode_axil_slave = AXIL_N_SLAVES;          // default: no match
        for (int unsigned s = 0; s < AXIL_N_SLAVES; s++) begin
            if (addr >= AXIL_SLV_BASE[s] && addr <= AXIL_SLV_LIMIT[s]) begin
                decode_axil_slave = s;
            end
        end
    endfunction

endpackage : soc_periph_map_pkg
