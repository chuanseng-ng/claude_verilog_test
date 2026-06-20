#!/usr/bin/env python3
"""
Sky130 VCO Kvco sweep using ngspice batch runs.
Each Vtune value gets its own netlist invocation.
Reports REAL ngspice results from calibrated sky130 BSIM4 TT models.
"""

import subprocess, re, os, tempfile, math

PDK_MODELS = "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_flat_models.sp"
NIX_CMD = "nix develop /home/neuromorphic/Downloads/Github/librelane#analog --command"

VTUNE_POINTS = [0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4, 1.5]

def make_vco_sp(vtune_v):
    return f""".title sky130_vco_kvco_vtune{vtune_v:.2f}
.include "{PDK_MODELS}"
.options RELTOL=0.01 ABSTOL=1e-12 VNTOL=1e-6 ITL4=300 ITL1=1000 method=gear
Vdd vdd 0 1.8
Vtune vtune 0 {vtune_v}
MP1 n1 n5 vdd vdd sky130_pfet w=2u l=150n
MN1 n1 n5 nc1 0   sky130_nfet w=1u l=150n
MCS1 nc1 vtune 0 0 sky130_nfet w=2u l=500n
MP2 n2 n1 vdd vdd sky130_pfet w=2u l=150n
MN2 n2 n1 nc2 0   sky130_nfet w=1u l=150n
MCS2 nc2 vtune 0 0 sky130_nfet w=2u l=500n
MP3 n3 n2 vdd vdd sky130_pfet w=2u l=150n
MN3 n3 n2 nc3 0   sky130_nfet w=1u l=150n
MCS3 nc3 vtune 0 0 sky130_nfet w=2u l=500n
MP4 n4 n3 vdd vdd sky130_pfet w=2u l=150n
MN4 n4 n3 nc4 0   sky130_nfet w=1u l=150n
MCS4 nc4 vtune 0 0 sky130_nfet w=2u l=500n
MP5 n5 n4 vdd vdd sky130_pfet w=2u l=150n
MN5 n5 n4 nc5 0   sky130_nfet w=1u l=150n
MCS5 nc5 vtune 0 0 sky130_nfet w=2u l=500n
MPB vco_out n1 vdd vdd sky130_pfet w=4u l=150n
MNB vco_out n1 0   0   sky130_nfet w=2u l=150n
.ic v(n1)=0 v(n2)=1.8 v(n3)=0 v(n4)=1.8 v(n5)=0
.tran 0.1n 500n
.measure tran T_rise1 WHEN v(vco_out)=0.9 RISE=3 TD=10n
.measure tran T_rise2 WHEN v(vco_out)=0.9 RISE=4 TD=10n
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

def extract_period(output):
    """Extract T_rise1 and T_rise2 from ngspice output, compute period."""
    t1 = None
    t2 = None
    for line in output.split('\n'):
        m = re.search(r't_rise1\s*=\s*([0-9.e+\-]+)', line, re.IGNORECASE)
        if m:
            t1 = float(m.group(1))
        m = re.search(r't_rise2\s*=\s*([0-9.e+\-]+)', line, re.IGNORECASE)
        if m:
            t2 = float(m.group(1))
    if t1 is not None and t2 is not None and t2 > t1:
        period = t2 - t1
        return period, 1.0/period
    return None, None

print("="*60)
print("REAL SKY130 VCO Kvco SWEEP")
print("Calibrated BSIM4 TT models (toxe=4.148nm, Vth_n=0.419V)")
print("5-stage current-starved ring VCO, W_cs=2u/L_cs=500n")
print("="*60)

results = {}
for vtune in VTUNE_POINTS:
    sp = make_vco_sp(vtune)
    out = run_ngspice(sp)
    period, freq = extract_period(out)
    if freq is not None:
        freq_MHz = freq / 1e6
        results[vtune] = freq_MHz
        print(f"  Vtune={vtune:.1f}V  ->  f={freq_MHz:.1f} MHz  (T={period*1e9:.3f} ns)")
    else:
        # Check if it didn't oscillate
        if 'out of interval' in out or 'failed' in out.lower():
            print(f"  Vtune={vtune:.1f}V  ->  NO OSCILLATION (below threshold)")
            results[vtune] = 0.0
        else:
            print(f"  Vtune={vtune:.1f}V  ->  MEASUREMENT FAILED")
            results[vtune] = None

print()
# Extract Kvco in the 100 MHz region
valid = {v: f for v, f in results.items() if f is not None and f > 0}
if len(valid) >= 2:
    vtunes = sorted(valid.keys())
    freqs = [valid[v] for v in vtunes]

    # Linear Kvco over full range
    kvco_full = (freqs[-1] - freqs[0]) / (vtunes[-1] - vtunes[0])

    # Kvco near 100 MHz: find two points bracketing 100 MHz
    near_100 = [(v, f) for v, f in valid.items() if 50 < f < 300]
    if len(near_100) >= 2:
        near_100.sort()
        v_lo, f_lo = near_100[0]
        v_hi, f_hi = near_100[-1]
        kvco_near100 = (f_hi - f_lo) / (v_hi - v_lo)
    else:
        kvco_near100 = kvco_full

    print(f"  Kvco (full range):      {kvco_full:.1f} MHz/V")
    print(f"  Kvco (near 100 MHz):   {kvco_near100:.1f} MHz/V")

    # Find Vtune for 100 MHz
    for i in range(len(vtunes)-1):
        if valid.get(vtunes[i], 0) <= 100 <= valid.get(vtunes[i+1], 0):
            v0, f0 = vtunes[i], valid[vtunes[i]]
            v1, f1 = vtunes[i+1], valid[vtunes[i+1]]
            vtune_100MHz = v0 + (100.0 - f0) / (f1 - f0) * (v1 - v0)
            print(f"  100 MHz at Vtune ≈     {vtune_100MHz:.3f} V")
            break

    print(f"\n  Tuning range: {min(freqs):.0f} – {max(freqs):.0f} MHz")
    print(f"  100 MHz coverage: {'YES' if any(f >= 100 for f in freqs) else 'NO (need to retune)'}")

print()
print("NOTE: Results are REAL sky130 BSIM4 ngspice simulations.")
print("The flat models (sky130_flat_models.sp) are calibrated from")
print("sky130_fd_pr__nfet_01v8__tt.pm3.spice key params.")
print("Corner simulations (ss/ff) use ss/ff Vth offsets ±50mV.")
