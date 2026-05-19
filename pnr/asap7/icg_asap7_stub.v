// icg_asap7_stub.v
// Blackbox stub for ICGx1_ASAP7_75t_R (ASAP7 RVT integrated clock gate).
// Used by the Yosys json_header and synthesis steps so the cell is a known
// blackbox before the liberty is loaded.  During synthesis, read_liberty -lib
// replaces this stub with the actual liberty cell (same pattern as the SRAM
// stub).  Verilator never sees this file — it is in VERILOG_FILES only.
//
// Pin map (from asap7sc7p5t_SEQ_RVT_FF_nldm_220123.lib):
//   CLK  — source clock
//   ENA  — active-high enable, sampled on falling CLK edge
//   SE   — scan enable (tie 0 in non-DFT use)
//   GCLK — gated clock output

`timescale 1ns/1ps

(* blackbox *)
module ICGx1_ASAP7_75t_R (
    input  wire CLK,
    input  wire ENA,
    input  wire SE,
    output wire GCLK
);
endmodule
