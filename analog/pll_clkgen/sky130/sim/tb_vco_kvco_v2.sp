* ============================================================  
* tb_vco_kvco_v2.sp — Sky130 VCO Kvco Sweep (ngspice-42 compatible)
* 5-stage current-starved ring VCO, calibrated sky130 TT flat BSIM4
* Vtune = 0.3, 0.6, 0.9, 1.2, 1.5 V
* REAL sky130 params: toxe=4.148nm, Vth_n=0.419V, Vth_p=-0.475V
* ============================================================
.title sky130_vco_kvco_v2

.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_flat_models.sp"

.options RELTOL=0.01 ABSTOL=1e-12 VNTOL=1e-6 ITL4=200 ITL1=500 method=gear

Vdd vdd 0 1.8
Vtune vtune 0 0.9

* 5-stage current-starved ring VCO (inline flat devices)
* Stage 1: in=n5, out=n1
MP1  n1 n5 vdd vdd sky130_pfet w=2u l=150n
MN1  n1 n5 nc1 0   sky130_nfet w=1u l=150n
MCS1 nc1 vtune 0 0 sky130_nfet w=2u l=500n
* Stage 2: in=n1, out=n2
MP2  n2 n1 vdd vdd sky130_pfet w=2u l=150n
MN2  n2 n1 nc2 0   sky130_nfet w=1u l=150n
MCS2 nc2 vtune 0 0 sky130_nfet w=2u l=500n
* Stage 3: in=n2, out=n3
MP3  n3 n2 vdd vdd sky130_pfet w=2u l=150n
MN3  n3 n2 nc3 0   sky130_nfet w=1u l=150n
MCS3 nc3 vtune 0 0 sky130_nfet w=2u l=500n
* Stage 4: in=n3, out=n4
MP4  n4 n3 vdd vdd sky130_pfet w=2u l=150n
MN4  n4 n3 nc4 0   sky130_nfet w=1u l=150n
MCS4 nc4 vtune 0 0 sky130_nfet w=2u l=500n
* Stage 5: in=n4, out=n5
MP5  n5 n4 vdd vdd sky130_pfet w=2u l=150n
MN5  n5 n4 nc5 0   sky130_nfet w=1u l=150n
MCS5 nc5 vtune 0 0 sky130_nfet w=2u l=500n
* Output buffer
MPB  vco_out n1 vdd vdd sky130_pfet w=4u l=150n
MNB  vco_out n1 0   0   sky130_nfet w=2u l=150n

.ic v(n1)=0 v(n2)=1.8 v(n3)=0 v(n4)=1.8 v(n5)=0

.tran 0.2n 200n

.control

  echo "==================================================="
  echo "REAL SKY130 VCO Kvco: calibrated BSIM4 TT corner"
  echo "toxe=4.148nm Vth_n=0.419V u0_n=28.8mA/V2"
  echo "Vth_p=-0.475V u0_p=12.2mA/V2"
  echo "==================================================="

  * --- Vtune = 0.3 V ---
  alter Vtune dc = 0.3
  tran 0.2n 200n
  meas tran t1a WHEN v(vco_out) = 0.9 RISE=3
  meas tran t1b WHEN v(vco_out) = 0.9 RISE=4
  let T_03 = t1b - t1a
  let f_03 = 1.0/T_03
  echo "Vtune=0.3V: T=" T_03*1e9 "ns  f=" f_03/1e6 "MHz"

  * --- Vtune = 0.6 V ---
  alter Vtune dc = 0.6
  tran 0.2n 200n
  meas tran t2a WHEN v(vco_out) = 0.9 RISE=3
  meas tran t2b WHEN v(vco_out) = 0.9 RISE=4
  let T_06 = t2b - t2a
  let f_06 = 1.0/T_06
  echo "Vtune=0.6V: T=" T_06*1e9 "ns  f=" f_06/1e6 "MHz"

  * --- Vtune = 0.9 V ---
  alter Vtune dc = 0.9
  tran 0.2n 200n
  meas tran t3a WHEN v(vco_out) = 0.9 RISE=3
  meas tran t3b WHEN v(vco_out) = 0.9 RISE=4
  let T_09 = t3b - t3a
  let f_09 = 1.0/T_09
  echo "Vtune=0.9V: T=" T_09*1e9 "ns  f=" f_09/1e6 "MHz"

  * --- Vtune = 1.2 V ---
  alter Vtune dc = 1.2
  tran 0.2n 200n
  meas tran t4a WHEN v(vco_out) = 0.9 RISE=3
  meas tran t4b WHEN v(vco_out) = 0.9 RISE=4
  let T_12 = t4b - t4a
  let f_12 = 1.0/T_12
  echo "Vtune=1.2V: T=" T_12*1e9 "ns  f=" f_12/1e6 "MHz"

  * --- Vtune = 1.5 V ---
  alter Vtune dc = 1.5
  tran 0.2n 200n
  meas tran t5a WHEN v(vco_out) = 0.9 RISE=3
  meas tran t5b WHEN v(vco_out) = 0.9 RISE=4
  let T_15 = t5b - t5a
  let f_15 = 1.0/T_15
  echo "Vtune=1.5V: T=" T_15*1e9 "ns  f=" f_15/1e6 "MHz"

  * Kvco
  let kvco_MHz_V = (f_15 - f_03) / (1.5 - 0.3) / 1e6
  echo "==================================================="
  echo "REAL SKY130 ngspice TT RESULTS:"
  echo "  f_osc(0.3V) = " f_03/1e6 "MHz"
  echo "  f_osc(0.6V) = " f_06/1e6 "MHz"
  echo "  f_osc(0.9V) = " f_09/1e6 "MHz  <-- target: 100 MHz"
  echo "  f_osc(1.2V) = " f_12/1e6 "MHz"
  echo "  f_osc(1.5V) = " f_15/1e6 "MHz"
  echo "  Kvco (0.3-1.5V) = " kvco_MHz_V "MHz/V"
  echo "==================================================="

  quit
.endc

.end
