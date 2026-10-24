// rv32i_cpu_top_stub.sv
// Blackbox stub for the rv32i_cpu_top hard macro at SoC-top synthesis.
// Yosys treats (* blackbox *) modules as externally-defined cells; the port
// interface is preserved for netlist connectivity but no logic is synthesised.
// The real implementation is in pnr/asap7/soc/macro/rv32i_cpu_top.nl.v.gz
// (gate-level netlist from the CPU block-level signoff run).
//
// AXI bus widths: AXI_LEN_WIDTH=8, AXI_SIZE_WIDTH=3 (from axi_pkg.sv).

`timescale 1ns/1ps

(* blackbox *)
module rv32i_cpu_top #(
    parameter logic [31:0] RESET_PC = 32'h0000_0000
) (
    // Clock and reset
    input  logic        clk_i,
    input  logic        rst_n_i,

    // AXI4 Master — write address channel
    output logic [31:0] axi_awaddr_o,
    output logic [7:0]  axi_awlen_o,
    output logic [2:0]  axi_awsize_o,
    output logic [1:0]  axi_awburst_o,
    output logic        axi_awvalid_o,
    input  logic        axi_awready_i,

    // AXI4 Master — write data channel
    output logic [31:0] axi_wdata_o,
    output logic [3:0]  axi_wstrb_o,
    output logic        axi_wlast_o,
    output logic        axi_wvalid_o,
    input  logic        axi_wready_i,

    // AXI4 Master — write response channel
    input  logic [1:0]  axi_bresp_i,
    input  logic        axi_bvalid_i,
    output logic        axi_bready_o,

    // AXI4 Master — read address channel
    output logic [31:0] axi_araddr_o,
    output logic [7:0]  axi_arlen_o,
    output logic [2:0]  axi_arsize_o,
    output logic [1:0]  axi_arburst_o,
    output logic        axi_arvalid_o,
    input  logic        axi_arready_i,

    // AXI4 Master — read data channel
    input  logic [31:0] axi_rdata_i,
    input  logic [1:0]  axi_rresp_i,
    input  logic        axi_rvalid_i,
    input  logic        axi_rlast_i,
    output logic        axi_rready_o,

    // APB3 Slave (debug)
    input  logic [11:0] apb_paddr_i,
    input  logic        apb_psel_i,
    input  logic        apb_penable_i,
    input  logic        apb_pwrite_i,
    input  logic [31:0] apb_pwdata_i,
    output logic [31:0] apb_prdata_o,
    output logic        apb_pready_o,
    output logic        apb_pslverr_o,

    // Commit / observability
    output logic        commit_valid_o,
    output logic [31:0] commit_pc_o,
    output logic [31:0] commit_insn_o,
    output logic        trap_taken_o,
    output logic [3:0]  trap_cause_o,

    // Debug outputs
    output logic [31:0] debug_rs1_data_o,
    output logic [31:0] debug_rs2_data_o,
    output logic        debug_branch_taken_o,
    output logic        debug_take_branch_jump_o,
    output logic        debug_pc_src_o,
    output logic [3:0]  debug_state_o,
    output logic        debug_ebreak_o,

    // Interrupt inputs
    input  logic        ext_irq_i,
    input  logic        timer_irq_i,

    // DFT test boundary (bead j41m.4, DFT_ARCHITECTURE.md 14.10). These four ports exist in
    // the RTL and in this stub so the SoC netlist elaborates, but the COMMITTED ASAP7 macro
    // views (pnr/asap7/soc/macro/rv32i_cpu_top.{lef,lib,nl}) are the pre-DFT ones and do not
    // have the pins. An ASAP7 SoC P&R against them fails at the macro pin match until bead
    // j41m.13 regenerates the views (blocked on ma7/lxv/2kn, like every ASAP7 SoC re-run).
    input  logic        scan_mode_i,
    input  logic        scan_en_i,
    input  logic [1:0]  scan_in_i,
    output logic [1:0]  scan_out_o,

    // MBIST boundary (bead c54a, DFT_ARCHITECTURE.md 16.7): 96 pins, same status as the four DFT ports
    // above: present in the RTL and in this stub so the SoC netlist elaborates, absent from the committed
    // ASAP7 macro views and from pnr/asap7/cpu/pin_order.cfg (not changed: the ASAP7 CPU macro re-harden is
    // shelved, blocked on ma7/lxv/2kn; j41m.13 regenerates the views and must add these pins, which carry
    // no live logic on the ASAP7 arm: the caches have no collars there and drive 0 as MBIST read data).
    input  logic        mbist_run_i,
    input  logic [25:0] mbist_cfg_i,
    output logic [68:0] mbist_status_o
);
endmodule
