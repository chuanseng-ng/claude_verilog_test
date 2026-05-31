// axi_pkg.sv
// Phase 5 (M1) — Shared AXI4 / AXI4-Lite parameter and encoding package.
//
// This is the minimal slice of milestone M1 required by the M3 AXI4 crossbar:
// common widths plus burst/response/size encodings.  All Phase 5 SoC fabric
// modules import this package so the bus geometry is defined in one place.
//
// Existing Phase 1-4 blocks use flat per-channel ports with NO id field and
// (today) single-beat transfers.  The crossbar's slave-facing ports are full
// AXI4 (id + len + size + burst + last); the master-facing ports take the
// lite-shaped subset.  See docs/PHASE5_SOC_INTEGRATION_PLAN.md §1.

// The constants below are a shared library package consumed by multiple Phase 5
// modules (M3 crossbar, M4 cache-upgrade, M6 SRAM controller, M8 peripherals).
// Not every constant is referenced by every module that imports this package.
// Suppress UNUSEDPARAM for the whole package so downstream modules can import
// freely without triggering spurious warnings for constants they do not use.
/* verilator lint_off UNUSEDPARAM */
package axi_pkg;

    // ── Bus geometry ─────────────────────────────────────────────────────────
    parameter int unsigned AXI_ADDR_WIDTH = 32;
    parameter int unsigned AXI_DATA_WIDTH = 32;
    parameter int unsigned AXI_STRB_WIDTH = AXI_DATA_WIDTH / 8;   // 4 byte lanes
    parameter int unsigned AXI_ID_WIDTH   = 4;                    // >= clog2(masters)
    parameter int unsigned AXI_LEN_WIDTH  = 8;                    // AxLEN (beats-1)
    parameter int unsigned AXI_SIZE_WIDTH = 3;                    // AxSIZE

    // ── Burst types (AxBURST) ────────────────────────────────────────────────
    localparam logic [1:0] AXI_BURST_FIXED = 2'b00;
    localparam logic [1:0] AXI_BURST_INCR  = 2'b01;
    localparam logic [1:0] AXI_BURST_WRAP  = 2'b10;

    // ── Transfer size (AxSIZE) — log2(bytes per beat) ────────────────────────
    localparam logic [2:0] AXI_SIZE_1B  = 3'd0;
    localparam logic [2:0] AXI_SIZE_2B  = 3'd1;
    localparam logic [2:0] AXI_SIZE_4B  = 3'd2;   // 32-bit beat (this SoC)

    // ── Response codes (xRESP) ───────────────────────────────────────────────
    localparam logic [1:0] AXI_RESP_OKAY   = 2'b00;
    localparam logic [1:0] AXI_RESP_EXOKAY = 2'b01;
    localparam logic [1:0] AXI_RESP_SLVERR = 2'b10;
    localparam logic [1:0] AXI_RESP_DECERR = 2'b11;

    // ── Convenience: cache-line burst length (16 B line / 4 B beat = 4 beats) ──
    // AxLEN is "beats - 1", so a 4-beat refill burst uses AxLEN = 3.
    localparam logic [AXI_LEN_WIDTH-1:0] AXI_LEN_LINE = 8'd3;

endpackage : axi_pkg
/* verilator lint_on  UNUSEDPARAM */
