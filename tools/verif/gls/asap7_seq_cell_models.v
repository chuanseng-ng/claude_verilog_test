// Hand-written behavioural models for the ASAP7 sequential (SEQ library)
// standard cells actually instantiated by the vector_alu_hls baseline
// netlists (GH #119 beads egt/gcd/b0t). Enumerated via:
//   grep -oE '^  [A-Za-z0-9_]*(DFF|LATCH|SDFF)[A-Za-z0-9_]*_ASAP7_75t_R' \
//     <nl.v> | sort -u
// against both /nobackup/asap7_valu_hls_runs/RUN_2026-09-15_14-05-40 (HLS-
// SYNLIG) and /nobackup/pnr_ab_valu_hls/runs/RUN_2026-09-15_16-34-19
// (HLS-SV2V): only two distinct types are used, DFFHQNx1_ASAP7_75t_R and
// DFFASRHQNx1_ASAP7_75t_R.
//
// Why this file exists: `read_liberty -ignore_miss_func` (the approach used
// for the comb arm's combinational cells, see gen_vector_alu_vectors.py /
// make_eval_ys.py) produces a functionally-correct but yosys-SAT-opaque
// representation for these two FF cells -- `sat -seq` fails at SAT-database
// import time ("Failed to import cell ... type $_DFF_PN0_") regardless of
// vector count or memory (bead b0t notes, 2026-09-15). Reading these plain
// `always @(posedge/negedge)` models INSTEAD of the SEQ liberty for just
// these two cells lets yosys's own `proc`+`flatten` infer native
// $dff/$adffsr cells, which `sat -seq` (and `sim`) DO support. Read the
// combinational (AO/OA/INVBUF/SIMPLE) libraries via `read_liberty
// -ignore_miss_func` as before -- only the SEQ library is replaced.
//
// Semantics below are transcribed directly from
// asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib's `ff (IQN,IQNN) { ... }` groups
// (cells DFFHQNx1_ASAP7_75t_R at line 2700, DFFASRHQNx1_ASAP7_75t_R at line
// 158; pin QN function is "IQN", i.e. QN is the *non-inverted* copy of the
// internal state variable IQN, and next_state is "!D" -- so on every rising
// CLK edge, QN <= ~D. This is deliberate: the netlist wires D from
// upstream inverting logic, so this pair is exactly a "DFF with inverted-D
// convention" cell, not a bug. asap7 ships no gate-level Verilog sim
// models at all (ASAP7 is a predictive PDK) -- there is no vendor model
// these could disagree with.

// DFFHQNx1_ASAP7_75t_R: plain D-FF, QN-only output, no async control.
//   ff (IQN,IQNN) { clocked_on: "CLK"; next_state: "!D"; }
module DFFHQNx1_ASAP7_75t_R (input CLK, input D, output reg QN);
  always @(posedge CLK) QN <= ~D;
endmodule

// DFFASRHQNx1_ASAP7_75t_R: D-FF, QN-only output, async active-low
// set (RESETN, confusingly named -- see below) and clear (SETN).
//   ff (IQN,IQNN) {
//     clocked_on: "CLK"; next_state: "!D";
//     clear: "!SETN"; preset: "!RESETN";
//     clear_preset_var1: L; clear_preset_var2: L;
//   }
// i.e. !SETN==1 (SETN low) forces the internal state IQN (-> QN) to 0
// ("clear"), !RESETN==1 (RESETN low) forces it to 1 ("preset"), and if
// both are simultaneously asserted the result is defined as L (0) by
// clear_preset_var1 -- matched below by checking the clear condition
// (!SETN) first. The naming is inverted from what "RESETN"/"SETN" suggest
// at the pin level; this is transcribed exactly from the liberty function
// tables, not inferred from the names. rtl/gpu callers wire this cell's
// SETN to the block's own active-low rst_n (see the netlist: `.SETN(rst_n)`
// on every instance sampled), consistent with the design's documented
// "async active-low reset" convention (hls/gpu/vector_alu/shim/
// vector_alu_hls.sv's port comment).
module DFFASRHQNx1_ASAP7_75t_R (input CLK, input D, input RESETN, input SETN,
                                  output reg QN);
  always @(posedge CLK or negedge RESETN or negedge SETN) begin
    if (!SETN)
      QN <= 1'b0;
    else if (!RESETN)
      QN <= 1'b1;
    else
      QN <= ~D;
  end
endmodule
