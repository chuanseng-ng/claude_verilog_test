// tb_pmu.sv
// GH #101 — standalone cocotb test wrapper for the behavioral PMU (rtl/soc/pmu.sv).
//
// Directly instantiates pmu with exposed APB4 slave ports that the APB4Master
// BFM drives, plus all ten per-domain sequencing outputs exposed as top-level
// outputs so tests can assert cycle-by-cycle ordering directly (no need to
// decode FSM state through the APB DOMAIN_EN register, which would perturb
// timing with extra APB transactions during a strict ordering check).
//
// This standalone approach follows the same pattern as tb_pll_apb_regs.sv:
// the BFM drives true top-level input ports, not nets driven by any RTL
// assign, so there is no multiple-driver conflict.
//
// Register map under test (pmu.sv, ADDR_W=12):
//   0x000  CTRL      [RW]  bits[1:0]=pmu_mode_req (WMASK=0x3)
//   0x004  STATUS    [RO]  [0]=cpu_domain_on [1]=gpu_domain_on [2]=busy
//   0x008  DOMAIN_EN [RO]  live per-signal bitmap (see pmu.sv header)
//
// Clock/reset naming:
//   clk   -> pclk    inside pmu (mapped via clk_i)
//   rst_n -> presetn inside pmu (mapped via rst_n_i)
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module tb_pmu #(
    parameter int unsigned ADDR_W = 12   // 4 KB slot -- matches pmu.sv
) (
    input  logic clk,
    input  logic rst_n,

    // -- APB4 slave port (BFM-facing, flat APB4 names) ----------------------
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,

    // -- CPU domain sequencing outputs (PD_CPU) ------------------------------
    output logic cpu_clk_en_o,
    output logic cpu_iso_en_o,
    output logic cpu_rst_n_o,
    output logic cpu_ret_save_o,
    output logic cpu_ret_restore_o,

    // -- GPU domain sequencing outputs (PD_GPU) ------------------------------
    output logic gpu_clk_en_o,
    output logic gpu_iso_en_o,
    output logic gpu_rst_n_o,
    output logic gpu_ret_save_o,
    output logic gpu_ret_restore_o
);

    pmu #(
        .ADDR_W(ADDR_W)
    ) u_dut (
        .clk_i  (clk),
        .rst_n_i(rst_n),

        // APB4 slave
        .psel   (psel),
        .penable(penable),
        .pwrite (pwrite),
        .paddr  (paddr),
        .pwdata (pwdata),
        .pstrb  (pstrb),
        .prdata (prdata),
        .pready (pready),
        .pslverr(pslverr),

        // CPU domain
        .cpu_clk_en_o     (cpu_clk_en_o),
        .cpu_iso_en_o     (cpu_iso_en_o),
        .cpu_rst_n_o      (cpu_rst_n_o),
        .cpu_ret_save_o   (cpu_ret_save_o),
        .cpu_ret_restore_o(cpu_ret_restore_o),

        // GPU domain
        .gpu_clk_en_o     (gpu_clk_en_o),
        .gpu_iso_en_o     (gpu_iso_en_o),
        .gpu_rst_n_o      (gpu_rst_n_o),
        .gpu_ret_save_o   (gpu_ret_save_o),
        .gpu_ret_restore_o(gpu_ret_restore_o)
    );

endmodule : tb_pmu

`default_nettype wire
