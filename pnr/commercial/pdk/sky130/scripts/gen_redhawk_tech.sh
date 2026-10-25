#!/bin/bash
# gen_redhawk_tech.sh -- RedHawk technology file for the authored Sky130 stack.
# Uses Ansys' own converter (RedHawk scripts/adsTechConverter.pl: ITF -> Apache tech) so the file is in the
# format this RedHawk build reads, plus an EM table taken from the tech-LEF (DC avg mA/um, mA/via).
# No licence needed (perl).  Inputs: build/tech/itf/sky130A_<corner>.itf (scripts/gen_stack.py).
set -eu
here=$(cd "$(dirname "$0")" && pwd); b=$here/../build; out=$b/redhawk; mkdir -p "$out"
RH=${RH_HOME:-/home/EDA/ansys/RedHawk_Linux64e8_V2025R2.2}
cat > "$out/layer_map.txt" <<'M'
# <layer_in_itf>  <layer_in_lef>   (tech LEF names; ITF via1 == LEF "via")
li1   li1
met1  met1
met2  met2
met3  met3
met4  met4
met5  met5
mcon  mcon
via1  via
via2  via2
via3  via3
via4  via4
M
# EM limits [TLEF sky130_fd_sc_hd__nom.tlef DCCURRENTDENSITY AVERAGE]: metals mA/um, cuts mA/via, at Tj=90C.
# EM_Adjust (second column) is the RedHawk width/temperature adjust factor: Sky130 publishes none -> 1.0 [ABSENT].
# li1 has no EM limit in the tech LEF -> omitted (ABSENT).
cat > "$out/em_table.txt" <<'M'
# <metal_in_lef> <EM> <EM_Adjust>   metal EM: mA/um ; via EM: mA/via   (all [TLEF] DC average at Tj=90C)
met1  2.8   1.0
met2  2.8   1.0
met3  6.8   1.0
met4  6.8   1.0
met5  10.17 1.0
mcon  0.36  1.0
via   0.29  1.0
via2  0.48  1.0
via3  0.48  1.0
via4  2.49  1.0
M
# adsTechConverter.pl uses `defined %hash` (removed in perl >= 5.22; host has 5.26) -> patched COPY in build/
# (reason: converter aborts at line 522 otherwise; original install file is not modified).
sed 's/defined *%dielectric/%dielectric/' "$RH/scripts/adsTechConverter.pl" > "$out/adsTechConverter.patched.pl"
for c in nom min max; do
  # the converter matches CONDUCTOR/DIELECTRIC/VIA anywhere in a line (even inside comments) -> feed it a comment-free ITF
  grep -v '^ *\$' "$b/tech/itf/sky130A_$c.itf" > "$out/sky130A_$c.nocomment.itf"
  (cd "$out" && perl "$out/adsTechConverter.patched.pl" -s "$out/sky130A_$c.nocomment.itf" -m "$out/layer_map.txt" -e "$out/em_table.txt" -o "$out/sky130A_$c.tech") > "$b/logs/adsTechConverter_$c.log" 2>&1 || { echo "converter failed ($c)"; tail -20 "$b/logs/adsTechConverter_$c.log"; exit 1; }
  # RedHawk 2025R2 rejects EM_Adjust inside via{} blocks (TEC-011, part 2a): drop it there, keep it in metal{} blocks
  python3 -I - "$out/sky130A_$c.tech" <<'PY'
import re, sys
p = sys.argv[1]; t = open(p).read()
t = re.sub(r"(via\s+\S+\s*\n\{(?:(?!\n\}).)*?)\n\s*EM_Adjust\s+\S+", r"\1", t, flags=re.S)
open(p, "w").write(t)
PY
  echo "wrote $out/sky130A_$c.tech"
done
