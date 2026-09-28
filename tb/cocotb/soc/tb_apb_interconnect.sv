// tb_apb_interconnect.sv
// Phase 6 groundwork (bead claude_verilog_test-f7vs.4) — standalone cocotb test wrapper for
// apb_interconnect (rtl/soc/apb_interconnect.sv).
//
// apb_interconnect is PURELY COMBINATIONAL (no clock/reset port at all — see its own header
// and soc_bus.sv's "5. APB interconnect" comment) and has no unit suite today; it is covered
// only transitively through SoC-level suites. It is the module that decides every peripheral's
// address decode, so this wrapper exists to give it a real, direct unit suite that can also
// drive an N_SLAVES parameter sweep (see test_apb_interconnect.py) — something no SoC-level
// suite can do, since soc_top elaborates the APB sub-tree at exactly one slave count.
//
// Unpacked-array top-level ports, flattened (same rationale as tb_axi4_crossbar.sv's header):
// "The crossbar uses parameterized unpacked-array ports, which cocotb cannot index
// conveniently." apb_interconnect's per-slave ports are `logic ... [N_SLAVES]` arrays whose
// SIZE varies across the sweep, so — unlike the crossbar's fixed 3x2 prefix-named scalars —
// this wrapper flattens them into PACKED VECTORS sized by N_SLAVES instead:
//   - psel_o_flat[N_SLAVES-1:0]      : bit i = psel_o[i] (per-slave select, the only signal
//                                       that actually differs across slaves).
//   - penable_o/pwrite_o/paddr_o/pwdata_o/pstrb_o : plain scalars. apb_interconnect broadcasts
//                                       an IDENTICAL value to every slave for these signals
//                                       (see its "Per-slave output drive" always_comb block),
//                                       so there is nothing to flatten — element [0] of the
//                                       DUT's internal array is representative of all N_SLAVES.
//   - prdata_i_flat[N_SLAVES*DW-1:0], pready_i_flat[N_SLAVES-1:0], pslverr_i_flat[N_SLAVES-1:0]:
//                                       per-slave RESPONSE inputs (driven by the testbench,
//                                       standing in for N_SLAVES downstream peripherals), one
//                                       DW-bit chunk / one bit per slave index.
//
// Decode windows: SLV_BASE/SLV_LIMIT are apb_interconnect PARAMETERS (elaboration-time
// constants), so they cannot be driven from cocotb at runtime. This wrapper generates them
// internally from N_SLAVES via make_slv_base()/make_slv_limit() below — contiguous,
// non-overlapping SLV_WINDOW-byte windows starting at address 0, the same convention
// soc_periph_map_pkg.sv uses for the real integration, just computed instead of hand-listed so
// the N_SLAVES sweep needs no per-value source edit (only a Verilator `-GN_SLAVES=<n>` override
// — see the apb_interconnect Makefile target).
//
// OVERLAP_TEST (default 0): when set, deliberately extends slave 0's window to also cover
// slave 1's entire window (only meaningful when N_SLAVES>=2), for
// test_apb_interconnect.py's first-match-wins check. Left at 0 for every other build/sweep
// point so it never perturbs the "each slave's own range selects exactly that slave" property
// the rest of the suite depends on.
//
// No BFM reuse: bfm/apb4_master.py's SETUP/ACCESS protocol is built on `await RisingEdge(clock)`
// and apb_interconnect has no clock at all, so the BFM does not fit this DUT (adding a fake
// clock port purely to satisfy it would misrepresent a combinational block as a clocked one).
// The Python test drives the flat inputs directly and settles with a plain `Timer`.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET 0 errors 0 warnings.

`default_nettype none

module tb_apb_interconnect #(
    parameter int unsigned N_SLAVES   = 8,       // mirrors apb_interconnect's N_SLAVES
    parameter int unsigned ADDR_W     = 32,      // mirrors apb_interconnect's ADDR_W
    parameter int unsigned DW         = 32,      // mirrors apb_interconnect's DW
    parameter int unsigned SW         = 4,       // mirrors apb_interconnect's SW
    parameter int unsigned SLV_WINDOW = 32'h1000,// wrapper-only: bytes per generated slave window
    parameter bit          OVERLAP_TEST = 1'b0   // wrapper-only: see header
) (
    // ── APB master input (from axil_to_apb bridge, BFM-facing) ───────────────
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [DW-1:0]     pwdata,
    input  logic [SW-1:0]     pstrb,

    // ── APB master response output (back to bridge) ──────────────────────────
    output logic [DW-1:0]     prdata,
    output logic              pready,
    output logic              pslverr,

    // ── APB slave outputs, flattened (see header) ─────────────────────────────
    output logic [N_SLAVES-1:0] psel_o_flat,
    output logic                penable_o,
    output logic                pwrite_o,
    output logic [ADDR_W-1:0]   paddr_o,
    output logic [DW-1:0]       pwdata_o,
    output logic [SW-1:0]       pstrb_o,

    // ── APB slave responses, flattened (see header; testbench-driven) ─────────
    input  logic [N_SLAVES*DW-1:0] prdata_i_flat,
    input  logic [N_SLAVES-1:0]    pready_i_flat,
    input  logic [N_SLAVES-1:0]    pslverr_i_flat
);

    // ── Generated per-slave decode windows ──────────────────────────────────
    typedef logic [ADDR_W-1:0] slv_addr_arr_t [N_SLAVES];

    function automatic slv_addr_arr_t make_slv_base();
        for (int unsigned i = 0; i < N_SLAVES; i++) begin
            make_slv_base[i] = ADDR_W'(i * SLV_WINDOW);
        end
    endfunction

    function automatic slv_addr_arr_t make_slv_limit();
        for (int unsigned i = 0; i < N_SLAVES; i++) begin
            make_slv_limit[i] = ADDR_W'(i * SLV_WINDOW + (SLV_WINDOW - 1));
        end
        if (OVERLAP_TEST && N_SLAVES >= 2) begin
            // Deliberately overlap slave 0 into slave 1's window -- see header.
            make_slv_limit[0] = ADDR_W'(2 * SLV_WINDOW - 1);
        end
    endfunction

    localparam slv_addr_arr_t SLV_BASE_LP  = make_slv_base();
    localparam slv_addr_arr_t SLV_LIMIT_LP = make_slv_limit();

    // ── DUT-facing unpacked arrays (unflattened) ────────────────────────────
    logic              psel_o_arr    [N_SLAVES];
    logic              penable_o_arr [N_SLAVES];
    logic              pwrite_o_arr  [N_SLAVES];
    logic [ADDR_W-1:0] paddr_o_arr   [N_SLAVES];
    logic [DW-1:0]     pwdata_o_arr  [N_SLAVES];
    logic [SW-1:0]     pstrb_o_arr   [N_SLAVES];

    logic [DW-1:0]     prdata_i_arr  [N_SLAVES];
    logic              pready_i_arr  [N_SLAVES];
    logic              pslverr_i_arr [N_SLAVES];

    genvar gi;
    generate
        for (gi = 0; gi < N_SLAVES; gi = gi + 1) begin : g_flatten
            assign psel_o_flat[gi]   = psel_o_arr[gi];
            assign prdata_i_arr[gi]  = prdata_i_flat[gi*DW +: DW];
            assign pready_i_arr[gi]  = pready_i_flat[gi];
            assign pslverr_i_arr[gi] = pslverr_i_flat[gi];
        end
    endgenerate

    // Broadcast signals: identical across every slave index by DUT construction
    // (see header) -- element [0] is representative.
    assign penable_o = penable_o_arr[0];
    assign pwrite_o  = pwrite_o_arr[0];
    assign paddr_o   = paddr_o_arr[0];
    assign pwdata_o  = pwdata_o_arr[0];
    assign pstrb_o   = pstrb_o_arr[0];

    apb_interconnect #(
        .N_SLAVES  (N_SLAVES),
        .ADDR_W    (ADDR_W),
        .DW        (DW),
        .SW        (SW),
        .SLV_BASE  (SLV_BASE_LP),
        .SLV_LIMIT (SLV_LIMIT_LP)
    ) u_dut (
        .psel_i     (psel),
        .penable_i  (penable),
        .pwrite_i   (pwrite),
        .paddr_i    (paddr),
        .pwdata_i   (pwdata),
        .pstrb_i    (pstrb),

        .prdata_o   (prdata),
        .pready_o   (pready),
        .pslverr_o  (pslverr),

        .psel_o     (psel_o_arr),
        .penable_o  (penable_o_arr),
        .pwrite_o   (pwrite_o_arr),
        .paddr_o    (paddr_o_arr),
        .pwdata_o   (pwdata_o_arr),
        .pstrb_o    (pstrb_o_arr),

        .prdata_i   (prdata_i_arr),
        .pready_i   (pready_i_arr),
        .pslverr_i  (pslverr_i_arr)
    );

endmodule : tb_apb_interconnect

`default_nettype wire
