// soc_addr_map_pkg.sv
// Phase 5 (M1) — SoC address-decode constants and helper.
//
// Defines the Phase 5 memory regions (per docs/design/MEMORY_MAP.md, reconciled
// to the AXI-Lite-native ring decision in PHASE5_SOC_INTEGRATION_PLAN.md M1) and
// a decode helper that maps an address to a data-fabric slave index.
//
// Region summary (data crossbar slaves):
//   Boot ROM : 0x0000_1000 .. 0x0000_1FFF   (4 KB, behavioral until M8)
//   Main SRAM: 0x0000_2000 .. 0x0FFF_FFFF   (behavioral AXI4 SRAM, M6)
//   Periph   : 0x2000_1000 .. 0x2000_9FFF   (AXI4→AXI-Lite bridge; Phase 7 M-c extended +PLL;
//              GH #92 extended again +PLL2)
//
// The crossbar itself is parameterized with SLV_BASE / SLV_LIMIT arrays so it
// stays reusable; the SoC top-level passes the constants below.  decode_slave()
// is the reference model used by the top-level and the testbench.

// SLV_ROM and SLV_SRAM are library constants referenced by the SoC top-level
// and testbenches (M4/M6/M8) but not consumed by every module that imports this
// package.  Suppress UNUSEDPARAM for the slave-index constants only.
/* verilator lint_off UNUSEDPARAM */
package soc_addr_map_pkg;
/* verilator lint_on  UNUSEDPARAM */

    import axi_pkg::*;

    // ── Data-fabric slave indices ────────────────────────────────────────────
    /* verilator lint_off UNUSEDPARAM */
    localparam int unsigned SLV_ROM    = 0;
    localparam int unsigned SLV_SRAM   = 1;
    localparam int unsigned SLV_PERIPH = 2;
    /* verilator lint_on  UNUSEDPARAM */
    localparam int unsigned SOC_N_SLAVES = 3;

    // ── Uncached MMIO window (Phase 5) ──────────────────────────────────────
    // Single source of truth: any address >= MMIO_BASE is uncached in the D-cache.
    // All peripheral bases (APB3-debug, GPU-ctrl, UART, SPI, timer, DMA, IRQ-ctrl)
    // lie at or above 0x2000_0000.  The D-cache bypass comparator uses this constant.
    // Region-bound constants are consumed by the SoC top-level and testbenches; they
    // are not referenced inside every module that imports this package.
    /* verilator lint_off UNUSEDPARAM */
    localparam logic [31:0] MMIO_BASE    = 32'h2000_0000;

    // ── Region bounds (inclusive) ────────────────────────────────────────────
    localparam logic [31:0] ROM_BASE     = 32'h0000_1000;
    localparam logic [31:0] ROM_LIMIT    = 32'h0000_1FFF;
    localparam logic [31:0] SRAM_BASE    = 32'h0000_2000;
    localparam logic [31:0] SRAM_LIMIT   = 32'h0FFF_FFFF;
    localparam logic [31:0] PERIPH_BASE  = 32'h2000_1000;
    localparam logic [31:0] PERIPH_LIMIT = 32'h2000_9FFF;  // Phase 7 M-c: extended to cover PLL slot (0x2000_7000-7FFF);
                                                            // Pre-Phase-6 #5 / GH #100: extended again to cover PMU slot (0x2000_8000-8FFF);
                                                            // GH #92: extended again to cover PLL2 slot (0x2000_9000-9FFF)
    /* verilator lint_on  UNUSEDPARAM */

    // Packed 2D arrays for crossbar instantiation (index = slave number).
    // NOTE: unpacked localparam arrays (logic [31:0] arr [N]) cause Synlig/UHDM
    // to emit $mem cells → empty-named RTLIL wires → yosys assert.
    // Use packed 2D form [N-1:0][31:0] which Synlig handles correctly.
    localparam logic [SOC_N_SLAVES-1:0][31:0] SOC_SLV_BASE  = {PERIPH_BASE,  SRAM_BASE,  ROM_BASE};
    localparam logic [SOC_N_SLAVES-1:0][31:0] SOC_SLV_LIMIT = {PERIPH_LIMIT, SRAM_LIMIT, ROM_LIMIT};

    // ── Reference decode ─────────────────────────────────────────────────────
    // Returns slave index [0 .. SOC_N_SLAVES-1], or SOC_N_SLAVES when the
    // address matches no slave (caller must raise DECERR).
    function automatic int unsigned decode_slave(input logic [31:0] addr);
        decode_slave = SOC_N_SLAVES;            // default: no match
        for (int unsigned s = 0; s < SOC_N_SLAVES; s++) begin
            if (addr >= SOC_SLV_BASE[s] && addr <= SOC_SLV_LIMIT[s]) begin
                decode_slave = s;
            end
        end
    endfunction

endpackage : soc_addr_map_pkg
