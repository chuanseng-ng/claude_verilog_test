// pll_subsystem - structural wrapper for the PLL clock generator, its APB4 registers and the reset glue.
//
// Function: The module holds pll_clkgen, pll_apb_regs and two reset assigns:
//   pll_rst_n = rst_n_i & pll_enable and core_rst_n = rst_n_i & pll_locked.
//   core_clk is the PLL output clock. ref_clk_o is clk_i, or scan_clk_i in scan mode.
//   In scan mode dft_clk_mux replaces the reference with scan_clk_i.
//   pll_rst_n, core_rst_n and the register-file reset take scan_rst_ni through dft_rst_mux.
//   With a non-STUB PLL, core_clk is also scan_clk_i in scan mode.
// Parameters: PLL_IMPL ("STUB" by default, "RNM" for AMS co-simulation), STUB_LOCK_CYCLES and ADDR_W.
// Clocks and resets: the whole module runs on clk_i and rst_n_i, the external reference.
// Caller rules:
//   - The module must not run on core_clk. That creates a bootstrap deadlock.
//   - Always feed the APB4 slave port from the m face of an apb_cdc_bridge. In RNM mode core_clk differs from clk_i.
//   - Do not wire the APB4 port straight to apb_interconnect.
// Doc: ds:mod:pll-subsystem, tm:mod:pll-subsystem, cr:mod:pll-subsystem

module pll_subsystem #(
    // PLL implementation selector — "STUB" (default, synth-safe) or "RNM" (cosim)
    parameter string       PLL_IMPL        = "STUB",
    // Number of ref_clk_i rising edges before locked_o asserts in STUB mode.
    // Expose so multi-instance designs (#4) can stagger lock times.
    parameter int unsigned STUB_LOCK_CYCLES = 16,
    // APB4 address width (4 KB slot default — one APB slave position)
    parameter int unsigned ADDR_W          = 12
) (
    // ── Reference clock / reset (this module runs on clk_i) ─────────────────
    input  logic clk_i,
    input  logic rst_n_i,

    // ── DFT test controls (j41m.2). Must be connected at every instantiation
    //    (no SV port defaults): scan_mode_i=1'b0, scan_rst_ni=1'b1, scan_clk_i=1'b0
    //    where there is no scan-aware parent. ──────────────────────────────────
    input  logic scan_mode_i,
    input  logic scan_rst_ni,
    input  logic scan_clk_i,

    // ── APB4 slave port (from an apb_cdc_bridge destination face) ───────────
    // soc_top does NOT wire this port straight to the apb_interconnect slot.
    // The interconnect runs on core_clk; this module runs on clk_i. In STUB
    // mode those are the same net, but in RNM mode core_clk != clk_i, so
    // soc_top interposes an apb_cdc_bridge (u_apb_pll_cdc for u_pll_sub,
    // u_apb_pll2_cdc for u_cpu_pll_sub) and drives this port from its m face.
    // See ds:mod:pll-subsystem.
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,

    // ── Outputs to soc_top ───────────────────────────────────────────────────
    output logic core_clk,      // PLL output clock; feeds all children
    output logic core_rst_n,    // rst_n_i & pll_locked; holds children in reset
    output logic pll_locked_o,  // raw PLL lock flag (expose for observability)
    // The reference clock this module actually runs on: clk_i, or scan_clk_i in
    // scan mode (j41m.2). Anything the parent clocks from the same reference (the
    // APB CDC bridge's destination face) must use THIS, not the raw port, or its
    // flops stay on the functional clock during test.
    output logic ref_clk_o
);

    // ── Internal signals ─────────────────────────────────────────────────────
    logic pll_enable;    // CONTROL[0] from pll_apb_regs
    logic [3:0] pll_fb_div;    // CONTROL[7:4] from pll_apb_regs
    logic [1:0] pll_post_div;  // CONTROL[9:8] from pll_apb_regs
    logic pll_locked;          // raw lock flag from pll_clkgen
    logic pll_rst_n;           // gated PLL reset: de-asserts only when
                                //   rst_n_i & pll_enable both high

    // ── DFT: test-clock and scan-reset bypass (see ds:mod:pll-subsystem) ───────
    logic ref_clk_w;        // clk_i, or scan_clk_i in scan mode
    logic rst_n_regs;       // rst_n_i, or scan_rst_ni in scan mode
    logic pll_rst_n_func;   // functional pll_rst_n before the scan override
    logic core_rst_n_func;  // functional core_rst_n before the scan override
    logic pll_clk_w;        // pll_clkgen output, before the optional output mux

    dft_clk_mux u_ref_cm (
        .func_clk_i (clk_i),
        .scan_clk_i (scan_clk_i),
        .sel_i      (scan_mode_i),
        .clk_o      (ref_clk_w)
    );

    assign ref_clk_o = ref_clk_w;

    dft_rst_mux u_regs_rm (
        .func_rst_n_i (rst_n_i),
        .scan_rst_ni  (scan_rst_ni),
        .scan_mode_i  (scan_mode_i),
        .rst_n_o      (rst_n_regs)
    );

    // PLL reset: firmware can hold PLL in reset via CONTROL[0]=0
    assign pll_rst_n_func  = rst_n_i & pll_enable;

    // Children reset: held until PLL locks
    assign core_rst_n_func = rst_n_i & pll_locked;

    dft_rst_mux u_pll_rm (
        .func_rst_n_i (pll_rst_n_func),
        .scan_rst_ni  (scan_rst_ni),
        .scan_mode_i  (scan_mode_i),
        .rst_n_o      (pll_rst_n)
    );

    dft_rst_mux u_core_rm (
        .func_rst_n_i (core_rst_n_func),
        .scan_rst_ni  (scan_rst_ni),
        .scan_mode_i  (scan_mode_i),
        .rst_n_o      (core_rst_n)
    );

    // Export raw lock flag
    assign pll_locked_o = pll_locked;

    // ── pll_clkgen: reference → core_clk ─────────────────────────────────────
    pll_clkgen #(
        .PLL_IMPL        (PLL_IMPL),
        .STUB_LOCK_CYCLES(STUB_LOCK_CYCLES)
    ) u_pll (
        .ref_clk_i   (ref_clk_w),
        .rst_n_i     (pll_rst_n),
        .feedback_div(pll_fb_div),
        .post_div_sel(pll_post_div),
        .out_clk_o   (pll_clk_w),
        .locked_o    (pll_locked)
    );

    // core_clk in scan mode. The stub is a pure passthrough of its reference
    // (pll_clkgen_stub: `assign out_clk_o = ref_clk_i`), so pll_clk_w already IS the
    // test clock in scan mode and a second mux would only add a stage to the clock
    // path. Any real or modelled PLL has an output that is NOT its reference, so its
    // output gets its own mux. If the stub ever stops being a passthrough this
    // generate must change with it (test_soc_dft_scan.py would fail).
    if (PLL_IMPL == "STUB") begin : g_core_clk_stub
        assign core_clk = pll_clk_w;
    end else begin : g_core_clk_pll
        dft_clk_mux u_core_cm (
            .func_clk_i (pll_clk_w),
            .scan_clk_i (scan_clk_i),
            .sel_i      (scan_mode_i),
            .clk_o      (core_clk)
        );
    end

    // ── pll_apb_regs: APB4 config slave (runs on clk_i — NOT core_clk) ──────
    pll_apb_regs #(
        .ADDR_W (ADDR_W)
    ) u_pll_regs (
        // Reference clock domain. See ds:mod:pll-subsystem.
        .clk_i       (ref_clk_w),
        .rst_n_i     (rst_n_regs),
        // APB4 slave
        .psel        (psel),
        .penable     (penable),
        .pwrite      (pwrite),
        .paddr       (paddr),
        .pwdata      (pwdata),
        .pstrb       (pstrb),
        .prdata      (prdata),
        .pready      (pready),
        .pslverr     (pslverr),
        // PLL config outputs → pll_clkgen
        .pll_enable_o   (pll_enable),
        .feedback_div_o (pll_fb_div),
        .post_div_sel_o (pll_post_div),
        // PLL status ← pll_clkgen
        .pll_locked_i   (pll_locked)
    );

endmodule : pll_subsystem
