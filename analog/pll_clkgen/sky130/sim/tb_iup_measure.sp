* ============================================================
* tb_iup_measure.sp -- PMOS charge pump IUP measurement
* sky130-fr001 fix (Phase 7 M-b2)
*
* Approach: sweep Vbias_p (pbias voltage) to find the operating
* point where i(Rbias_p) = I_PMOS (self-consistent bias point).
* Target: I = 10 uA through PMOS W=4u/L=2u at Rbias_p=71k.
*
* Self-consistent bias: pbias = VDD - I*Rbias_p
* At I=10uA: pbias = 1.8 - 10e-6*71e3 = 1.8 - 0.71 = 1.09V
* Vgs_p = 1.09 - 1.8 = -0.71V (|Vgs|=0.71V > |Vth_p|=0.475V: ON)
*
* Method: drive pbias directly from Vbias voltage source,
* sweep from 0.5V to 1.5V, plot PMOS mirror output current.
* The actual bias point is where I_mirror = (VDD-Vbias)/Rbias_p.
*
* sky130 flat BSIM4 TT: u0_p=12.2e-3 A/V2, Vth_p=-0.475V
* ============================================================
.title sky130_iup_sweep

.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_flat_models.sp"

.options RELTOL=0.01 ABSTOL=1e-12 VNTOL=1e-6 ITL4=150 ITL1=500

VDD  vdd  0  DC 1.8

* Drive pbias from voltage source (sweep)
Vbias_p  pbias  0  DC 1.09

* PMOS mirror reference: D=G=pbias, S=B=VDD
* No Rbias_p here -- we set pbias externally for the sweep
Mpref  pbias  pbias  vdd  vdd  sky130_pfet  l=2u  w=4u
* PMOS mirror output: D=psrc, G=pbias, S=B=VDD
Mpmirr  psrc  pbias  vdd  vdd  sky130_pfet  l=2u  w=4u
* PMOS switch: fully ON, S=psrc, D=iout
Vpsw  pg  0  DC 0.0
Mpsw  iout  pg  psrc  vdd  sky130_pfet  l=150n  w=8u
* Compliance
Vcpa  iout  0  DC 0.9

* Sweep pbias from 0.7V to 1.5V (Vgs from -0.3V to -1.1V)
.dc Vbias_p 0.7 1.5 0.05

.control
  dc Vbias_p 0.7 1.5 0.05
  echo "=== PMOS mirror current vs pbias voltage ==="
  echo "Column 1: v(pbias), Column 2: -i(Vcpa)*1e6 [IUP_uA]"
  echo "Column 3: Rbias_p current = (1.8-v(pbias))/71k [uA]"
  echo "Intersection = self-consistent bias point"
  echo ""
  echo "i(Vcpa) raw [A] (negative=PMOS sourcing into iout):"
  print i(Vcpa)
  echo ""
  echo "IUP from mirror output [uA] = -i(Vcpa)*1e6:"
  let iup_mirror = -i(Vcpa) * 1e6
  print iup_mirror
  echo ""
  echo "Rbias current [uA] at each pbias = (1.8 - v-sweep)/71k *1e6:"
  let I_rbias = (1.8 - v(pbias)) / 71e3 * 1e6
  print I_rbias
  echo ""
  echo "At pbias=1.09V: IUP_mirror and I_rbias should both be ~10 uA"
  quit
.endc

.end
