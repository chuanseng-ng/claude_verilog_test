# FSM re-encoding facts from the Yosys log of the B2 run (pnr/sky130/cpu/runs/b2_openroad/06-yosys-synthesis/yosys-synthesis.log, section 48.6/48.7):
#   Yosys FSM_RECODE re-encoded three 2-bit registers to one-hot 4-bit state vectors:
#     u_core.fwd_a_sel_r, u_core.fwd_b_sel_r, u_core.u_cache_arb.grant_q   (log lines 7626-7644)
#   mapping stated in the log (old code -> new code, bit 0 on the right):  00 -> ---1,  10 -> --1-,  01 -> -1--,  11 -> 1---
# Netlist realisation (measured on the netlist): fwd_a/fwd_b keep new bits [3],[2],[1] only (bit [0], the reset state, has no reader and was removed by opt_clean:
#   state 00 is therefore the all-zero code of the 3 remaining flops); grant_q keeps all four bits (bit [3] is the flop whose Q net is the port axi_bready_o).
# State names are shared by the reference and the implementation (matched by name).
proc fm_fsm {refdesign fsmname rflops iflops rcodes icodes} {
  set_fsm_state_vector $rflops $refdesign -name ${fsmname}
  set_fsm_encoding -name ${fsmname} $rcodes $refdesign
  set_fsm_state_vector $iflops i:/WORK/rv32i_cpu_top -name ${fsmname}_i -match ${fsmname}
  set_fsm_encoding -name ${fsmname}_i $icodes i:/WORK/rv32i_cpu_top
}
fm_fsm r:/WORK/rv32i_core_00000000 fwd_a {fwd_a_sel_r_reg[1] fwd_a_sel_r_reg[0]} {_51785_ _51784_ _51783_} {S00=2#00 S10=2#10 S01=2#01 S11=2#11} {S00=2#000 S10=2#001 S01=2#010 S11=2#100}
fm_fsm r:/WORK/rv32i_core_00000000 fwd_b {fwd_b_sel_r_reg[1] fwd_b_sel_r_reg[0]} {_49928_ _49927_ _49926_} {S00=2#00 S10=2#10 S01=2#01 S11=2#11} {S00=2#000 S10=2#001 S01=2#010 S11=2#100}
fm_fsm r:/WORK/rv32i_cache_arbiter grant {grant_q_reg[1] grant_q_reg[0]} {_54176_ _54175_ _54174_ _54173_} {S00=2#00 S10=2#10 S01=2#01 S11=2#11} {S00=2#0001 S10=2#0010 S01=2#0100 S11=2#1000}
report_fsm
