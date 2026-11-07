import pya, re
ly = pya.Layout(); ly.read(gds)
tc = ly.cell("rv32i_cpu_top")
nonstd = sorted(c.name for c in ly.each_cell() if not re.match(r"sky130_(fd_sc_hd|ef_sc_hd)__|sky130_sram", c.name))
print("non-std non-sram cells:", len(nonstd), nonstd[:40])
real = ly.cell("sky130_sram_1kbyte_1rw1r_32x256_8")
print("real SRAM bbox um:", real.dbbox(), "dbu", ly.dbu)
for inst in tc.each_inst():
    if "sram" in inst.cell.name.lower():
        t = inst.trans
        print("SRAM inst", inst.cell.name, "disp(dbu)", t.disp, "rot", t.rot, "mirr", t.is_mirror())
# top-level instance census by cell name
from collections import Counter
cnt = Counter()
for inst in tc.each_inst():
    cnt[inst.cell.name] += (inst.na*inst.nb if inst.is_regular_array() else 1)
print("top-level instance records:", sum(cnt.values()))
for n, c in cnt.most_common(40): print(f"  {c:8d} {n}")
print("via-ish top-level cells:", [(n,c) for n,c in cnt.items() if not n.startswith('sky130')])
