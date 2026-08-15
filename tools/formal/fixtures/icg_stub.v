// icg_stub.v — blackbox declaration for ICGx1_ASAP7_75t_R.
//
// rv32i_clock_gate.sv directly instantiates this ASAP7 integrated-clock-gate
// liberty cell when USE_ICG_CELL is defined (see pnr/Makefile SOC_SV2V_DEFINES
// rationale). Neither the gold (SystemVerilog, read via Yosys read_verilog -sv)
// nor the gate (sv2v output) side carries a definition for it — it only exists
// in the ASAP7 SEQ liberty, which this repo's EQY harness deliberately does not
// load (loading real liberty would turn "does sv2v preserve this instantiation"
// into "does the ASAP7 timing model behave correctly", a different and much
// heavier question that belongs to STA/LEC-after-synthesis, not this bead).
//
// Declaring it here, identically, on both [gold] and [gate] reads makes EQY's
// equivalence proof for rv32i_clock_gate a structural/connectivity check: does
// gold's u_icg instance connect the same way gate's does? It does NOT prove
// anything about the cell's internal behaviour (there is none to prove here —
// it is a blackbox on both sides by construction).
(* blackbox *)
module ICGx1_ASAP7_75t_R (
    CLK,
    ENA,
    SE,
    GCLK
);
    input CLK;
    input ENA;
    input SE;
    output GCLK;
endmodule
