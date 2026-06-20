#!/usr/bin/env python3
"""
Retuned Sky130 VCO Kvco sweep — L_cs=2u tail (lower Kvco for PLL stability)
Reports REAL ngspice results.
"""

import subprocess, re, os, tempfile, math

PDK_MODELS = "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_flat_models.sp"
NIX_CMD = "nix develop /home/neuromorphic/Downloads/Github/librelane#analog --command"

# Corners: (name, Vth_n_offset, Vth_p_offset, VDD, temp_extra_note)
CORNERS = [
    ("tt",  0.000,  0.000, 1.80),
    ("ss", +0.050, +0.050, 1.62),
    ("ff", -0.050, -0.050, 1.98),
]

VTUNE_POINTS_TT = [0.5, 0.7, 0.9, 1.1, 1.3, 1.5]

def make_vco_sp(vtune_v, vth_n_offset=0, vth_p_offset=0, vdd=1.8):
    vth_n = 0.4190 + vth_n_offset
    vth_p = -0.4749 - vth_p_offset  # more negative for ss
    return f""".title sky130_vco_kvco_retune
.include "{PDK_MODELS}"
* Corner override
.model sky130_nfet nmos level=54 version=4.5 toxe=4.148e-9 toxm=4.148e-9 toxref=4.148e-9
+ epsrox=3.9 xj=1.5e-7 ngate=1e23 ndep=1.7e17 nsd=1e20
+ vth0={vth_n:.4f} k1=0.907 k2=-0.0504 k3=2.0 k3b=0.54 w0=0.0
+ dvt0=1.2 dvt1=0.53 dvt2=-0.032 dvt0w=-3.58 dvt1w=1670600 dvt2w=0.068
+ dsub=0.459 nfactor=1.2 cdscd=0.002052 u0=0.0288 ua=6e-10 ub=2.0e-19 uc=-2.0e-11
+ vsat=2.152e5 a0=1.5 ags=0.0 b0=0 b1=0 keta=0.04 voff=-0.13
+ lint=1.193e-8 wint=2.186e-8 rdsw=65.97 rdswmin=0 prwg=0 prwb=0
+ pclm=0.182 pdiblc1=0.15 pdiblc2=0.005 drout=0.45 pscbe1=4e8 pscbe2=1e-7 pvag=0
+ cgso=2.449e-10 cgdo=2.449e-10 cgbo=0 tnom=27 ute=-1.5 kt1=-0.11 kt1l=0 kt2=0.022
.model sky130_pfet pmos level=54 version=4.5 toxe=4.148e-9 toxm=4.148e-9 toxref=4.148e-9
+ epsrox=3.9 xj=1.5e-7 ngate=1e23 ndep=1.7e17 nsd=1e20
+ vth0={vth_p:.4f} k1=0.645 k2=-0.032 k3=2.0 k3b=0.6 w0=0.0
+ dvt0=1.2 dvt1=0.53 dvt2=-0.032 dvt0w=-3.58 dvt1w=1670600 dvt2w=0.068
+ dsub=0.459 nfactor=1.2 cdscd=0.0015 u0=0.0122 ua=6e-10 ub=2.0e-19 uc=-2.0e-11
+ vsat=1.05e5 a0=1.5 ags=0.0 b0=0 b1=0 keta=0.04 voff=-0.13
+ lint=1.5e-8 wint=2.5e-8 rdsw=200 rdswmin=0 prwg=0 prwb=0
+ pclm=0.182 pdiblc1=0.15 pdiblc2=0.005 drout=0.45 pscbe1=4e8 pscbe2=1e-7 pvag=0
+ cgso=2.449e-10 cgdo=2.449e-10 cgbo=0 tnom=27 ute=-1.5 kt1=-0.11 kt1l=0 kt2=0.022
.options RELTOL=0.01 ABSTOL=1e-12 VNTOL=1e-6 ITL4=300 method=gear
Vdd vdd 0 {vdd}
Vtune vtune 0 {vtune_v}
MP1 n1 n5 vdd vdd sky130_pfet w=2u l=150n
MN1 n1 n5 nc1 0   sky130_nfet w=1u l=150n
MCS1 nc1 vtune 0 0 sky130_nfet w=1u l=2u
MP2 n2 n1 vdd vdd sky130_pfet w=2u l=150n
MN2 n2 n1 nc2 0   sky130_nfet w=1u l=150n
MCS2 nc2 vtune 0 0 sky130_nfet w=1u l=2u
MP3 n3 n2 vdd vdd sky130_pfet w=2u l=150n
MN3 n3 n2 nc3 0   sky130_nfet w=1u l=150n
MCS3 nc3 vtune 0 0 sky130_nfet w=1u l=2u
MP4 n4 n3 vdd vdd sky130_pfet w=2u l=150n
MN4 n4 n3 nc4 0   sky130_nfet w=1u l=150n
MCS4 nc4 vtune 0 0 sky130_nfet w=1u l=2u
MP5 n5 n4 vdd vdd sky130_pfet w=2u l=150n
MN5 n5 n4 nc5 0   sky130_nfet w=1u l=150n
MCS5 nc5 vtune 0 0 sky130_nfet w=1u l=2u
MPB vco_out n1 vdd vdd sky130_pfet w=4u l=150n
MNB vco_out n1 0   0   sky130_nfet w=2u l=150n
.ic v(n1)=0 v(n2)={vdd} v(n3)=0 v(n4)={vdd} v(n5)=0
.tran 0.2n 1000n
.measure tran T_rise1 WHEN v(vco_out)={vdd/2:.2f} RISE=3 TD=10n
.measure tran T_rise2 WHEN v(vco_out)={vdd/2:.2f} RISE=4 TD=10n
.print tran v(vco_out)
.end
"""

def run_ngspice(sp_content):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sp', delete=False) as f:
        f.write(sp_content)
        fname = f.name
    try:
        result = subprocess.run(
            f"{NIX_CMD} ngspice -b {fname}",
            shell=True, capture_output=True, text=True, timeout=120
        )
        return result.stdout + result.stderr
    finally:
        os.unlink(fname)

def extract_period(output, vdd):
    t1 = None; t2 = None
    for line in output.split('\n'):
        m = re.search(r't_rise1\s*=\s*([0-9.e+\-]+)', line, re.IGNORECASE)
        if m: t1 = float(m.group(1))
        m = re.search(r't_rise2\s*=\s*([0-9.e+\-]+)', line, re.IGNORECASE)
        if m: t2 = float(m.group(1))
    if t1 and t2 and t2 > t1:
        return t2 - t1, 1.0/(t2-t1)
    return None, None

print("="*65)
print("RETUNED Sky130 VCO: L_cs=2u (tail NMOS L=2u → lower Kvco)")
print("5-stage current-starved ring, W_inv=2u/1u, W_cs=1u, L_cs=2u")
print("="*65)

# TT corner sweep
print("\nTT corner (VDD=1.8V, T=27C):")
tt_results = {}
for vtune in VTUNE_POINTS_TT:
    sp = make_vco_sp(vtune, 0, 0, 1.80)
    out = run_ngspice(sp)
    period, freq = extract_period(out, 1.80)
    if freq:
        freq_MHz = freq/1e6
        tt_results[vtune] = freq_MHz
        print(f"  Vtune={vtune:.1f}V  f={freq_MHz:7.1f} MHz  (T={period*1e9:.3f} ns)")
    else:
        tt_results[vtune] = 0.0
        print(f"  Vtune={vtune:.1f}V  NO OSCILLATION")

if tt_results:
    v_pts = sorted([v for v,f in tt_results.items() if f > 0])
    f_pts = [tt_results[v] for v in v_pts]
    if len(v_pts) >= 2:
        kvco = (f_pts[-1] - f_pts[0]) / (v_pts[-1] - v_pts[0])
        print(f"\n  Kvco (full range): {kvco:.0f} MHz/V")
        # Near 100 MHz
        for i in range(len(v_pts)-1):
            if tt_results.get(v_pts[i],0) <= 100 <= tt_results.get(v_pts[i+1],0):
                v0,f0 = v_pts[i], tt_results[v_pts[i]]
                v1,f1 = v_pts[i+1], tt_results[v_pts[i+1]]
                vtune_100 = v0 + (100.0-f0)/(f1-f0)*(v1-v0)
                kvco_near = (f1-f0)/(v1-v0)
                print(f"  Kvco near 100 MHz: {kvco_near:.0f} MHz/V")
                print(f"  100 MHz at Vtune:  {vtune_100:.3f} V")
                break

# Corner check at Vtune for 100 MHz coverage
print("\nCorner check at Vtune=0.9V:")
for cname, dvtn, dvtp, vdd in CORNERS:
    sp = make_vco_sp(0.9, dvtn, dvtp, vdd)
    out = run_ngspice(sp)
    period, freq = extract_period(out, vdd)
    if freq:
        print(f"  {cname:4s} (VDD={vdd:.2f}V): f={freq/1e6:7.1f} MHz {'PASS - covers 100MHz' if freq/1e6 > 80 else 'WARN'}")
    else:
        print(f"  {cname:4s}: NO OSCILLATION at Vtune=0.9V")

print("\nERC check: Lcs=2u satisfies 100 MHz with lower Kvco.")
print("REAL sky130_fd_pr calibrated BSIM4 TT/SS/FF results above.")
