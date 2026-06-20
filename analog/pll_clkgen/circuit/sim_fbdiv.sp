* ============================================================
* Feedback Divider /13 — Self-contained CMOS /13 counter test
* Uses TSPC D-FFs + combinational reset
* Clocked at 1.3 GHz (nominal VCO freq)
* Verifies divout period = 13 * T_clk
* ============================================================
FeedbackDiv /13 Check

.model nfinfet_rvt nmos level=14 version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9 wint=0 lint=0
+ vth0=0.276 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032 dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 minv=0.0 voffl=0 dvtp0=1e-10 dvtp1=0.1
+ w0=2.5e-6 k3b=0 ngate=0
+ vsat=1.7e5 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18 nsd=2.0e20 phin=0
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.060 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0 clc=0 cle=0.6 delta=0.01
+ rdsw=150 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0 pdiblc2=0 pdiblcb=0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7 pvag=0 mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0 cf=0 xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0 xl=-4e-9

.model pfinfet_rvt pmos level=14 version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9 wint=0 lint=0
+ vth0=-0.284 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032 dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 minv=0.0 voffl=0 dvtp0=1e-10 dvtp1=0.1
+ w0=2.5e-6 k3b=0 ngate=0
+ vsat=1.1e5 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18 nsd=2.0e20 phin=0
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.025 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0 clc=0 cle=0.6 delta=0.01
+ rdsw=200 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0 pdiblc2=0 pdiblcb=0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7 pvag=0 mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0 cf=0 xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0 xl=-4e-9

* ---- Supply ----
.param vdd_val=0.7
VDD vdd 0 DC 'vdd_val'

* ---- 1.3 GHz clock (period=769.2 ps) ----
* Rise/fall 30 ps for CMOS edges at 0.7 V
Vclk clkin 0 PULSE 0 'vdd_val' 0 30p 30p 354.6p 769.2p

* ============================================================
* TSPC DFF (inline)
* Topology: 3-stage TSPC (Yuan-Svensson)
* Stage1: PMOS precharge (clk=0) + NMOS eval (clk=1)
* Stage2: dual-precharge node
* Stage3: static inverter output pair
*
* For T-FF: connect D=QB
*
* FF0 (bit 0, toggle every cycle): D=q0b
* ============================================================

* ---- FF0 (bit 0) ----
MP_p1_0  nd1_0  clkin  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n1_0  nd1_0  q0b    nd2_0  0  nfinfet_rvt  w=14n  l=7n
MN_n2_0  nd2_0  clkin  0      0  nfinfet_rvt  w=14n  l=7n
MP_p2a_0 nd3_0  clkin  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_p2b_0 nd3_0  nd1_0  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n3_0  nd3_0  clkin  0    0    nfinfet_rvt  w=14n  l=7n
MP_p3_0  q0     nd3_0  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n4_0  q0     nd3_0  0    0    nfinfet_rvt  w=14n  l=7n
MP_p4_0  q0b    q0     vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n5_0  q0b    q0     0    0    nfinfet_rvt  w=14n  l=7n

* ---- FF1 (bit 1, T=AND(q0b, nrst_b) wait... use ripple T-mode) ----
* Simple ripple: FF1 clocked by q0 falling (T-FF on q0 output)
* Use clkin for all FFs (synchronous), T input drives D via qb feedback
* T1 = q0 (toggle when q0=1)
* AND2 for T1: a=q0, b=nrst_b -> t1_in = q0 AND nrst_b
*   NAND: MN series stack + MP parallel
MP_nd1a_1  nand_t1  q0     vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_nd1b_1  nand_t1  nrst_b vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_nd1a_1  nand_t1  q0  nd_and1  0  nfinfet_rvt  w=14n  l=7n
MN_nd1b_1  nd_and1  nrst_b  0   0  nfinfet_rvt  w=14n  l=7n
*   INV: t1_in = inv(nand_t1)
MP_inv1a_1  t1_in  nand_t1  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_inv1b_1  t1_in  nand_t1  0    0    nfinfet_rvt  w=14n  l=7n

* FF1 TSPC: D = q1b (T-FF mode, T=t1_in)
* Mux D: if t1_in=1 -> D=q1b; if t1_in=0 -> D=q1 (hold)
* Simplified: direct T-FF via D=XOR(q1,t1_in)=? Use TSPC properly:
* The TSPC DFF with D=q1b acts as T-FF only when reset not needed
* For /13 counter, use synchronous reset: clear all on count=12=1100b
* Bit arrangement: q0=LSB toggles every clk; q1 on q0; q2 on q0&q1; q3 on q0&q1&q2
* With synchronous clear: when all 4 FFs hit count 12 (1100), nrst_b=0

MP_p1_1  nd1_1  clkin  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n1_1  nd1_1  q1b    nd2_1  0  nfinfet_rvt  w=14n  l=7n
MN_n2_1  nd2_1  clkin  0      0  nfinfet_rvt  w=14n  l=7n
MP_p2a_1 nd3_1  clkin  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_p2b_1 nd3_1  nd1_1  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n3_1  nd3_1  clkin  0    0    nfinfet_rvt  w=14n  l=7n
MP_p3_1  q1     nd3_1  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n4_1  q1     nd3_1  0    0    nfinfet_rvt  w=14n  l=7n
MP_p4_1  q1b    q1     vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n5_1  q1b    q1     0    0    nfinfet_rvt  w=14n  l=7n

* AND for t2: q1 AND q0 AND nrst_b (simplified: q1 AND t1_in)
MP_nd2a  nand_t2  q1     vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_nd2b  nand_t2  t1_in  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_nd2a  nand_t2  q1  nd_and2  0  nfinfet_rvt  w=14n  l=7n
MN_nd2b  nd_and2  t1_in  0    0  nfinfet_rvt  w=14n  l=7n
MP_inv2a  t2_in  nand_t2  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_inv2b  t2_in  nand_t2  0    0    nfinfet_rvt  w=14n  l=7n

* ---- FF2 (bit 2) ----
MP_p1_2  nd1_2  clkin  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n1_2  nd1_2  q2b    nd2_2  0  nfinfet_rvt  w=14n  l=7n
MN_n2_2  nd2_2  clkin  0      0  nfinfet_rvt  w=14n  l=7n
MP_p2a_2 nd3_2  clkin  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_p2b_2 nd3_2  nd1_2  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n3_2  nd3_2  clkin  0    0    nfinfet_rvt  w=14n  l=7n
MP_p3_2  q2     nd3_2  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n4_2  q2     nd3_2  0    0    nfinfet_rvt  w=14n  l=7n
MP_p4_2  q2b    q2     vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n5_2  q2b    q2     0    0    nfinfet_rvt  w=14n  l=7n

* AND for t3: q2 AND t2_in
MP_nd3a  nand_t3  q2     vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_nd3b  nand_t3  t2_in  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_nd3a  nand_t3  q2  nd_and3  0  nfinfet_rvt  w=14n  l=7n
MN_nd3b  nd_and3  t2_in  0    0  nfinfet_rvt  w=14n  l=7n
MP_inv3a  t3_in  nand_t3  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_inv3b  t3_in  nand_t3  0    0    nfinfet_rvt  w=14n  l=7n

* ---- FF3 (bit 3) ----
MP_p1_3  nd1_3  clkin  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n1_3  nd1_3  q3b    nd2_3  0  nfinfet_rvt  w=14n  l=7n
MN_n2_3  nd2_3  clkin  0      0  nfinfet_rvt  w=14n  l=7n
MP_p2a_3 nd3_3  clkin  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_p2b_3 nd3_3  nd1_3  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n3_3  nd3_3  clkin  0    0    nfinfet_rvt  w=14n  l=7n
MP_p3_3  q3     nd3_3  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n4_3  q3     nd3_3  0    0    nfinfet_rvt  w=14n  l=7n
MP_p4_3  q3b    q3     vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n5_3  q3b    q3     0    0    nfinfet_rvt  w=14n  l=7n

* ---- Reset logic: detect count=12 (1100b) -> nrst_b = 0 ----
* count=12: q3=1, q2=1, q1=0, q0=0
* -> NAND(q3, q2, q1b, q0b) -> INV -> nrst_b active low (nrst_b=0 when count=12)
* NAND4: series NMOS q3,q2,q1b,q0b; parallel PMOS
MP_rst_p1  nand4_rst  q3   vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_rst_p2  nand4_rst  q2   vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_rst_p3  nand4_rst  q1b  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_rst_p4  nand4_rst  q0b  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_rst_n1  nand4_rst  q3  nd_r1  0  nfinfet_rvt  w=14n  l=7n
MN_rst_n2  nd_r1      q2  nd_r2  0  nfinfet_rvt  w=14n  l=7n
MN_rst_n3  nd_r2      q1b nd_r3  0  nfinfet_rvt  w=14n  l=7n
MN_rst_n4  nd_r3      q0b 0      0  nfinfet_rvt  w=14n  l=7n
* INV of NAND4 -> rst_trigger (high when count=12)
MP_rst_inv  rst_trigger  nand4_rst  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_rst_inv  rst_trigger  nand4_rst  0    0    nfinfet_rvt  w=14n  l=7n
* nrst_b = inv(rst_trigger)
MP_nrst  nrst_b  rst_trigger  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_nrst  nrst_b  rst_trigger  0    0    nfinfet_rvt  w=14n  l=7n

* ---- Output toggle FF (divout): toggles on each rst_trigger ----
MP_p1_out  nd1_o  clkin  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n1_out  nd1_o  divout_b  nd2_o  0  nfinfet_rvt  w=14n  l=7n
MN_n2_out  nd2_o  clkin  0       0  nfinfet_rvt  w=14n  l=7n
MP_p2a_o  nd3_o  clkin   vdd  vdd  pfinfet_rvt  w=21n  l=7n
MP_p2b_o  nd3_o  nd1_o   vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n3_o   nd3_o  clkin   0    0    nfinfet_rvt  w=14n  l=7n
MP_p3_o   divout    nd3_o  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n4_o   divout    nd3_o  0    0    nfinfet_rvt  w=14n  l=7n
MP_p4_o   divout_b  divout  vdd  vdd  pfinfet_rvt  w=21n  l=7n
MN_n5_o   divout_b  divout  0    0    nfinfet_rvt  w=14n  l=7n

* ---- Initial conditions: all FFs reset to 0 ----
.ic V(q0)=0 V(q0b)='vdd_val'
.ic V(q1)=0 V(q1b)='vdd_val'
.ic V(q2)=0 V(q2b)='vdd_val'
.ic V(q3)=0 V(q3b)='vdd_val'
.ic V(divout)=0 V(divout_b)='vdd_val'
.ic V(nrst_b)='vdd_val'

.tran 5p 200n uic

.control
  run
  * Find period of divout: measure between rising edges
  meas tran td1 TRIG v(divout) VAL=0.35 RISE=3
  meas tran td2 TRIG v(divout) VAL=0.35 RISE=4
  if td2 > td1 and td1 > 0
    let t_period_div = td2 - td1
    let f_divout = 1.0/t_period_div
    * Expected: f_divout = 1.3e9/13 = 100 MHz
    * Measured divide ratio: f_clk / f_divout
    let f_clk = 1.0 / 769.2e-12
    let n_meas = f_clk / f_divout
    echo "============================================"
    echo "FEEDBACK DIVIDER /13 SANITY CHECK:"
    echo "  Clock freq: 1.300 GHz"
    echo "  divout period [ns]:" t_period_div*1e9
    echo "  divout freq [MHz]:" f_divout/1e6
    echo "  Measured divide ratio:" n_meas
    if abs(n_meas - 13.0) < 1.0
      echo "  PASS: divide ratio confirms /13"
    else
      echo "  FAIL: divide ratio != 13"
    end
    echo "============================================"
  else
    echo "============================================"
    echo "  WARNING: divout did not toggle in simulation window"
    echo "  Check initial conditions and counter reset logic"
    echo "============================================"
  end

  quit
.endc

.end
