// tb_soc_top.sv
// Phase 5 (M9) — cocotb test wrapper for soc_top.
//
// soc_top has no unpacked-array ports at its boundary (those are internal),
// so no fan-in/fan-out logic is needed — this file is a thin pass-through
// that adds:
//   1. MEM_INIT_FILE parameter forwarded to the boot_rom inside soc_top
//      (boot_rom.MEM_INIT_FILE is re-exposed as a top-level parameter so
//       each cocotb test can supply its own hex image at elaboration time).
//   2. Flat scalar ports with the signal names that the cocotb BFMs expect
//      (clk_i, rst_n_i, apb_*, uart_*, spi_*, commit_*, gpu_irq_o).
//
// All signals are direct renames of soc_top ports — zero logic, exactly
// the pattern of tb_axi4_crossbar.sv.
//
// Lint target: verilator -Wall 0 errors 0 warnings.

`default_nettype none

module tb_soc_top #(
    // Forwarded to boot_rom.MEM_INIT_FILE inside soc_top.
    // Pass "" (empty string) to leave ROM all-zeros; pass a path to a
    // $readmemh-compatible hex file to pre-load firmware.
    parameter string MEM_INIT_FILE = ""
) (
    // ── Clock / reset ─────────────────────────────────────────────────────────
    input  logic        clk_i,
    input  logic        rst_n_i,

    // ── APB3 debug slave (CPU debug port) ────────────────────────────────────
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

    // ── Observability bus ─────────────────────────────────────────────────────
    output logic        commit_valid_o,
    output logic [31:0] commit_pc_o,
    output logic [31:0] commit_insn_o,
    output logic        gpu_irq_o,

    // ── PLL status (Phase 7 M-c) ─────────────────────────────────────────────
    // Exposed so soc_boot_lint passes cleanly; soc_boot / soc_periph /
    // soc_coherency / soc_cpu_gpu tests do not observe this signal directly —
    // they use commit_pc_o as the boot readiness indicator.
    output logic        pll_locked_o
);

    soc_top #(
        .MEM_INIT_FILE (MEM_INIT_FILE)
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

endmodule : tb_soc_top
