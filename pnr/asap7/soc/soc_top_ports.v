// soc_top_ports.v — Port-only stub for Yosys json_header generation.
//
// This file contains ONLY soc_top's port declarations in plain Verilog-2001
// (no SystemVerilog packages, no internal logic, no `import`).
// It is used exclusively by the Yosys json_header step to generate
// soc_top.h.json when the full Synlig-based elaboration fails to emit
// module instantiation cells (Surelog UHDM issue with this design).
//
// The FULL soc_top.sv is still used for synthesis (Yosys.Synthesis step).
// Parameters in PnR mode: MEM_INIT_FILE=int(0), PLL_IMPL=int(0).

`default_nettype none

(* top *)
module soc_top #(
    parameter integer MEM_INIT_FILE  = 0,
    parameter integer PLL_IMPL       = 0,
    parameter integer SRAM_MEM_WORDS = 1024
) (
    input  wire        clk_i,
    input  wire        rst_n_i,

    // APB3 debug slave
    input  wire [11:0] apb_paddr_i,
    input  wire        apb_psel_i,
    input  wire        apb_penable_i,
    input  wire        apb_pwrite_i,
    input  wire [31:0] apb_pwdata_i,
    output wire [31:0] apb_prdata_o,
    output wire        apb_pready_o,
    output wire        apb_pslverr_o,

    // UART
    output wire        uart_tx_o,
    input  wire        uart_rx_i,

    // SPI
    output wire        spi_sclk_o,
    output wire        spi_mosi_o,
    input  wire        spi_miso_i,
    output wire        spi_cs_n_o,

    // Observability
    output wire        commit_valid_o,
    output wire [31:0] commit_pc_o,
    output wire [31:0] commit_insn_o,
    output wire        gpu_irq_o,

    // PLL status
    output wire        pll_locked_o
);
endmodule

`default_nettype wire
