// tb_soc_pll.sv
// Phase 7 (M-c) — cocotb test wrapper for SoC PLL verification.
//
// Instantiates soc_top with PLL_IMPL="STUB" (default) so the testbench runs
// under pure Verilator without real-number model support.
//
// Adds pll_locked_o to the port list (soc_top.pll_locked_o, new in M-c) so
// cocotb can observe lock acquisition directly.  All other ports mirror
// tb_soc_top.sv exactly (same signal names, same direction, same width).
//
// Clock seam (STUB mode):
//   clk_i drives ref_clk inside soc_top.
//   core_clk = ref_clk (stub passthrough, no multiply).
//   pll_locked asserts after STUB_LOCK_CYCLES=16 ref_clk edges.
//   core_rst_n = rst_n_i & pll_locked, so children come out of reset after
//   the lock counter fires — roughly 16+1 = 17 ref_clk cycles after reset
//   de-asserts.
//
// Lint target: verilator -Wall 0 errors 0 warnings.

`default_nettype none

module tb_soc_pll #(
    // Forwarded to boot_rom.MEM_INIT_FILE inside soc_top.
    parameter string MEM_INIT_FILE = "",

    // PLL implementation selector — keep "STUB" for Verilator CI.
    // Override to "RNM" for AMS co-simulation (requires real-type support).
    parameter string PLL_IMPL = "STUB"
) (
    // ── Clock / reset ─────────────────────────────────────────────────────────
    // clk_i is the external reference clock (100 MHz in production; any
    // frequency in simulation — testbench sets the period).
    input  logic        clk_i,
    input  logic        rst_n_i,

    // ── APB3 debug slave (pass-through to CPU) ───────────────────────────────
    input  logic [11:0] apb_paddr_i,
    input  logic        apb_psel_i,
    input  logic        apb_penable_i,
    input  logic        apb_pwrite_i,
    input  logic [31:0] apb_pwdata_i,
    output logic [31:0] apb_prdata_o,
    output logic        apb_pready_o,
    output logic        apb_pslverr_o,

    // ── UART ─────────────────────────────────────────────────────────────────
    output logic        uart_tx_o,
    input  logic        uart_rx_i,

    // ── SPI ──────────────────────────────────────────────────────────────────
    output logic        spi_sclk_o,
    output logic        spi_mosi_o,
    input  logic        spi_miso_i,
    output logic        spi_cs_n_o,

    // ── Observability ─────────────────────────────────────────────────────────
    output logic        commit_valid_o,
    output logic [31:0] commit_pc_o,
    output logic [31:0] commit_insn_o,
    output logic        gpu_irq_o,

    // ── PLL status (Phase 7 M-c) ─────────────────────────────────────────────
    output logic        pll_locked_o    // 1 when stub lock counter fires
);

    soc_top #(
        .MEM_INIT_FILE (MEM_INIT_FILE),
        .PLL_IMPL      (PLL_IMPL)
    ) u_soc (
        .clk_i          (clk_i),
        .rst_n_i        (rst_n_i),

        .apb_paddr_i    (apb_paddr_i),
        .apb_psel_i     (apb_psel_i),
        .apb_penable_i  (apb_penable_i),
        .apb_pwrite_i   (apb_pwrite_i),
        .apb_pwdata_i   (apb_pwdata_i),
        .apb_prdata_o   (apb_prdata_o),
        .apb_pready_o   (apb_pready_o),
        .apb_pslverr_o  (apb_pslverr_o),

        .uart_tx_o      (uart_tx_o),
        .uart_rx_i      (uart_rx_i),

        .spi_sclk_o     (spi_sclk_o),
        .spi_mosi_o     (spi_mosi_o),
        .spi_miso_i     (spi_miso_i),
        .spi_cs_n_o     (spi_cs_n_o),

        .commit_valid_o (commit_valid_o),
        .commit_pc_o    (commit_pc_o),
        .commit_insn_o  (commit_insn_o),
        .gpu_irq_o      (gpu_irq_o),

        .pll_locked_o   (pll_locked_o)
    );

endmodule : tb_soc_pll

`default_nettype wire
