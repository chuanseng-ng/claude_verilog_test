// pll_subsystem.sv
// Pre-Phase-6 bead claude_verilog_test-1xb — PLL subsystem wrapper.
//
// Collects the three elements that were scattered across soc_top.sv into a
// single structural wrapper:
//   1. pll_clkgen      — PDK-agnostic PLL (STUB default / RNM for AMS cosim)
//   2. pll_apb_regs    — APB4 config slave (CONTROL / STATUS registers)
//   3. glue assigns    — pll_rst_n  = rst_n_i & pll_enable
//                        core_rst_n = rst_n_i & pll_locked
//
// Clock-domain rule (MUST NOT be changed):
//   This module, pll_clkgen, and pll_apb_regs all run on clk_i / rst_n_i
//   (the external reference clock).  They are the *source* of core_clk and
//   pll_locked.  Placing any of these on core_clk would create a bootstrap
//   deadlock because core_rst_n requires pll_locked, which requires
//   pll_enable=1, which comes from pll_apb_regs — which would be held in
//   reset (core_rst_n=0) forever.
//
//   STUB mode (PLL_IMPL="STUB"):
//     out_clk_o = ref_clk_i, so core_clk == clk_i.  No CDC issue.
//   RNM mode (PLL_IMPL="RNM"):
//     core_clk != clk_i.  The apb_interconnect (on core_clk) drives the APB
//     bus into pll_apb_regs (on clk_i) across a CDC boundary.  FIXED (GH #86,
//     soc_top.sv): every soc_top instance of this module (u_pll_sub,
//     u_cpu_pll_sub) has its APB4 slave port fed through an apb_cdc_bridge
//     instance (u_apb_pll_cdc / u_apb_pll2_cdc respectively) rather than
//     wired directly to the apb_interconnect slot — see soc_top.sv's
//     u_apb_pll_cdc instantiation comment for the full CDC argument and the
//     bootstrap-safety proof. Do NOT remove this comment without confirming
//     the calling soc_top still bridges this module's APB4 port.
//
// Precursor note for #4 (3-PLL: CPU / GPU / bus):
//   PLL_IMPL and STUB_LOCK_CYCLES are exposed as parameters so that three
//   independent pll_subsystem instances can be configured independently
//   (e.g. different lock-cycle counts for simulation speed).  ADDR_W is
//   similarly parameterised to allow different APB slot sizes.
//
// Ports:
//   clk_i       — reference clock input (100 MHz XO)
//   rst_n_i     — top-level active-low reset (synchronous inside sub-modules)
//   PLL_IMPL    — "STUB" (default) or "RNM" (AMS cosim only)
//   APB4 slave  — psel/penable/pwrite/paddr/pwdata/pstrb/prdata/pready/pslverr
//                 driven by soc_top from an apb_cdc_bridge DESTINATION (m_*)
//                 face, not straight off the apb_interconnect slot (GH #86)
//   core_clk    — PLL output clock; feeds all children of soc_top
//   core_rst_n  — gated reset: rst_n_i & pll_locked
//   pll_locked_o — raw PLL lock flag (exported to soc_top port)
//
// Coding rules: no logic — structural instantiation + assign only.
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

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

    // ── APB4 slave port (from an apb_cdc_bridge destination face) ───────────
    // soc_top does NOT wire this port straight to the apb_interconnect slot.
    // The interconnect runs on core_clk; this module runs on clk_i. In STUB
    // mode those are the same net, but in RNM mode core_clk != clk_i, so
    // soc_top interposes an apb_cdc_bridge (u_apb_pll_cdc for u_pll_sub,
    // u_apb_pll2_cdc for u_cpu_pll_sub) and drives this port from its m_*
    // face — GH #86. No longer deferred; see the file header.
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
    output logic pll_locked_o   // raw PLL lock flag (expose for observability)
);

    // ── Internal signals ─────────────────────────────────────────────────────
    logic pll_enable;    // CONTROL[0] from pll_apb_regs
    logic [3:0] pll_fb_div;    // CONTROL[7:4] from pll_apb_regs
    logic [1:0] pll_post_div;  // CONTROL[9:8] from pll_apb_regs
    logic pll_locked;          // raw lock flag from pll_clkgen
    logic pll_rst_n;           // gated PLL reset: de-asserts only when
                                //   rst_n_i & pll_enable both high

    // PLL reset: firmware can hold PLL in reset via CONTROL[0]=0
    assign pll_rst_n  = rst_n_i & pll_enable;

    // Children reset: held until PLL locks
    assign core_rst_n = rst_n_i & pll_locked;

    // Export raw lock flag
    assign pll_locked_o = pll_locked;

    // ── pll_clkgen: reference → core_clk ─────────────────────────────────────
    pll_clkgen #(
        .PLL_IMPL        (PLL_IMPL),
        .STUB_LOCK_CYCLES(STUB_LOCK_CYCLES)
    ) u_pll (
        .ref_clk_i   (clk_i),
        .rst_n_i     (pll_rst_n),
        .feedback_div(pll_fb_div),
        .post_div_sel(pll_post_div),
        .out_clk_o   (core_clk),
        .locked_o    (pll_locked)
    );

    // ── pll_apb_regs: APB4 config slave (runs on clk_i — NOT core_clk) ──────
    pll_apb_regs #(
        .ADDR_W (ADDR_W)
    ) u_pll_regs (
        // Reference clock domain — see clock-domain note in module header.
        .clk_i       (clk_i),
        .rst_n_i     (rst_n_i),
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

