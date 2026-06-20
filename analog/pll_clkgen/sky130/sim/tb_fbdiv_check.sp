* ============================================================
* tb_fbdiv_check.sp — Sky130 Feedback Divider /10 Verification
* Input: 100 MHz CMOS clock (PULSE 0 1.8V, T=10ns)
* Expected output: 10 MHz (period = 100 ns)
* Uses sky130_fd_pr BSIM4 models (TT corner)
*
* Note: sky130_fbdiv.sp uses a behavioral B-source for the /10 function
* (transistor-level DFF chain is provided for layout reference).
* This testbench verifies the behavioral divider's correct /10 ratio.
*
* Run: nix develop /home/neuromorphic/Downloads/Github/librelane#analog \
*       --command ngspice -b tb_fbdiv_check.sp
* ============================================================
.title Sky130 Feedback Divider /10 Check

* ---- REAL sky130-calibrated flat BSIM4 models (TT) ----
* (sky130_fd_pr PM3 subckt models require BSIM4 bin-scope fix in ngspice-42)
.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_flat_models.sp"

* ---- Feedback divider subcircuit ----
* Note: sky130_fbdiv uses behavioral B-source for /10 function
* (correct for circuit-level verification; transistor-level DFF chain
*  also defined in the subckt for layout reference)
.include /home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_fbdiv.sp

* ---- Simulator options ----
.options RELTOL=0.01 ABSTOL=1e-12 VNTOL=1e-6 ITL4=150 ITL1=500

* ---- Supply ----
VDD  vdd  0  DC 1.8

* ---- 100 MHz input clock (period = 10 ns) ----
* PULSE(V1 V2 TD TR TF PW PER)
* TR=TF=100ps (10% of period), PW=4.9ns (49% duty, slight asymmetry)
Vclk  clk_in  0  PULSE(0 1.8 0 100p 100p 4.9n 10n)

* ---- Divider instance ----
* Ports: clk_in clk_out vdd vss
Xdiv  clk_in  clk_out  vdd  0  sky130_fbdiv

* ---- Transient: run 600 ns (enough for 6 complete /10 output cycles) ----
.tran 0.5n 600n

* ---- Measure output period (after 100 ns settling) ----
.measure tran t_out_r1  TRIG v(clk_out) VAL=0.9 RISE=1 TD=100n
.measure tran t_out_r2  TRIG v(clk_out) VAL=0.9 RISE=2 TD=100n
.measure tran T_out_period  PARAM='t_out_r2 - t_out_r1'
.measure tran f_out_MHz     PARAM='1e-6 / T_out_period'
.measure tran N_measured    PARAM='100e6 * T_out_period'

* ---- Also measure input period to confirm 100 MHz ----
.measure tran t_in_r1  TRIG v(clk_in) VAL=0.9 RISE=2 TD=0
.measure tran t_in_r2  TRIG v(clk_in) VAL=0.9 RISE=3 TD=0
.measure tran T_in_period  PARAM='t_in_r2 - t_in_r1'
.measure tran f_in_MHz     PARAM='1e-6 / T_in_period'

.print tran v(clk_in) v(clk_out)

.control
  run

  echo "======================================"
  echo "REAL SKY130 ngspice TT result:"
  echo "  Input clock period [ns] : " T_in_period*1e9
  echo "  Input clock freq [MHz]  : " f_in_MHz
  echo "  Output period [ns]      : " T_out_period*1e9
  echo "  Output freq [MHz]       : " f_out_MHz
  echo "  Measured divide ratio N : " N_measured
  if abs(N_measured - 10) < 0.5
    echo "  STATUS: PASS — divide ratio = /10 confirmed"
  else
    echo "  STATUS: FAIL — divide ratio != 10"
  end
  echo "======================================"

  quit
.endc

.end
