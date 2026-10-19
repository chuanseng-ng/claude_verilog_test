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
//                          [3]=cpu_iso_ack_timeout (sticky, bead 3ogd)
//   0x008  DOMAIN_EN [RO]  live per-signal bitmap (see pmu.sv header)
//
// CPU isolation-acknowledge model (bead 3ogd).  In soc_top the PMU's cpu_iso_ack_i is the CPU-domain
// clamp (pmu_cpu_iso_en_sync) synchronised back to core_clk.  Here a small behavioural model stands in
// for that round trip, controlled from the test through three plain inputs:
//   ack_lat_i    0 (default): ack = cpu_iso_en_o combinationally -- the ack is "already there", so
//                every pre-3ogd ordering test sees the unchanged one-action-per-cycle walk.
//                N >= 1: ack follows cpu_iso_en_o N clk cycles late, in BOTH directions.
//   ack_stuck_i  1: ack holds its current value (a dead CPU clock domain), whatever cpu_iso_en_o does.
//   ack_force_i  1: ack_force_val_i is driven as the ack regardless of the model (a stale/early ack).
//
// Clock/reset naming:
//   clk   -> pclk    inside pmu (mapped via clk_i)
//   rst_n -> presetn inside pmu (mapped via rst_n_i)
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module tb_pmu #(
    parameter int unsigned ADDR_W = 12,         // 4 KB slot -- matches pmu.sv
    // Small enough to make the timeout path cheap to test; larger than the longest ack_lat_i the
    // tests use.  soc_top uses pmu.sv's own default (255).
    parameter int unsigned ISO_ACK_TIMEOUT = 16
) (
    input  logic clk,
    input  logic rst_n,

    // -- CPU isolation-ack model controls (see header) ----------------------
    input  logic [7:0] ack_lat_i,
    input  logic       ack_stuck_i,
    input  logic       ack_force_i,
    input  logic       ack_force_val_i,
    output logic       cpu_iso_ack_o,       // the ack the PMU actually sees (observability)

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

    // -- CPU isolation-ack model --------------------------------------------
    logic       ack_q;
    logic [7:0] ack_cnt_q;
    logic       ack_model;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            ack_q     <= 1'b0;
            ack_cnt_q <= 8'd0;
        end else if (ack_stuck_i) begin
            ack_cnt_q <= 8'd0;
        end else if (ack_lat_i == 8'd0) begin
            ack_q     <= cpu_iso_en_o;   // keep the held value current while the model is a pass-through
            ack_cnt_q <= 8'd0;
        end else if (cpu_iso_en_o != ack_q) begin
            if (ack_cnt_q >= ack_lat_i - 8'd1) begin
                ack_q     <= cpu_iso_en_o;
                ack_cnt_q <= 8'd0;
            end else begin
                ack_cnt_q <= ack_cnt_q + 8'd1;
            end
        end else begin
            ack_cnt_q <= 8'd0;
        end
    end

    // Latency 0 is a pass-through; a stuck model holds the registered value (which, with
    // ack_lat_i == 0, is whatever it was when ack_stuck_i was raised).
    assign ack_model     = ack_stuck_i ? ack_q : ((ack_lat_i == 8'd0) ? cpu_iso_en_o : ack_q);
    assign cpu_iso_ack_o = ack_force_i ? ack_force_val_i : ack_model;

    pmu #(
        .ADDR_W         (ADDR_W),
        .ISO_ACK_TIMEOUT(ISO_ACK_TIMEOUT)
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
        .cpu_iso_ack_i    (cpu_iso_ack_o),

        // GPU domain
        .gpu_clk_en_o     (gpu_clk_en_o),
        .gpu_iso_en_o     (gpu_iso_en_o),
        .gpu_rst_n_o      (gpu_rst_n_o),
        .gpu_ret_save_o   (gpu_ret_save_o),
        .gpu_ret_restore_o(gpu_ret_restore_o)
    );

endmodule : tb_pmu

`default_nettype wire
