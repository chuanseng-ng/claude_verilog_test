#!/usr/bin/env python3
"""mk_innovus_do.py <scripts/lec_genus_direct.do> <outdir>  -- B4d: Conformal do-files for the post-route Innovus netlist.
Derived from the B4b direct do-file (which itself is Genus' write_do_lec file with the changes listed in mk_do.py / mk_direct.py), so library
reads, hdl options, flatten options, naming rules and the RTL file list/defines are the ones Genus wrote.
  lec_innovus_rtl.do    (a) golden = RTL (same 28 SV files + defines incl. SRAM_SKY130), revised = $env(IMPL) Innovus netlist
                            [I1] verdict markers renamed B4D_RTL_*   (mapping file $env(MAPFILE) is optional: if the variable is empty no
                                 mapping file is used and pairing is by name / function)
  lec_innovus_genus.do  (b) golden = Genus final netlist $env(GOLDEN_NL), revised = $env(IMPL) Innovus netlist, netlist-to-netlist
                            [I2] RTL read, RTL-only naming rules (set_naming_*, set_undriven_signal -golden), uniquify and the mapping file are
                                 dropped; the golden netlist is read like the revised one.  Flatten options (seq_constant/-seq_merge) kept.
"""
import sys, re
src, outdir = sys.argv[1:3]
t = open(src).read()
def sub(s, old, new, n=1):
    assert s.count(old) == n, (old, s.count(old))
    return s.replace(old, new)

# ---- (a) RTL vs Innovus -------------------------------------------------------------------------------------------------
a = t.replace("B4B_DIRECT_", "B4D_RTL_")
a = sub(a, "# [D2] pure name mapping, composed RTL->final by Genus' analyze_extended_mapping in leg 1\nset_analyze_option -mapping_file $env(MAPFILE)",
        "# [I1] optional pure name mapping (Genus-composed RTL->Genus-netlist pairs; Innovus kept the Genus flop names). Empty MAPFILE = no file.\n"
        "if {$env(MAPFILE) ne \"\"} { set_analyze_option -mapping_file $env(MAPFILE) }")
a = sub(a, "set_mapping_method -search_in_mapping_file\n",
        "if {$env(MAPFILE) ne \"\"} { set_mapping_method -search_in_mapping_file }\n")
a = sub(a, "check_mapping_setup -mapping_file_quality -summary\n",
        "if {$env(MAPFILE) ne \"\"} { check_mapping_setup -mapping_file_quality -summary }\n")
a = sub(a, "# [D1] revised = the FINAL netlist (or a negative-control mutant of it)", "# [I1] revised = the Innovus post-route logical netlist (or a negative-control mutant of it)")
open(outdir + "/lec_innovus_rtl.do", "w").write(a)

# ---- (b) Genus netlist vs Innovus ---------------------------------------------------------------------------------------
b = t.replace("B4B_DIRECT_", "B4D_GENUS_")
i0 = b.index("set_undriven_signal 0 -golden")
i1 = b.index("# Align LEC's treatment")
b = b[:i0] + "# [I2] golden is a netlist: RTL naming rules and set_undriven_signal -golden are not applied\n" + b[i1:]
r0 = b.index("read_design -enumconstraint")
r1 = b.index("# [I1]") if "# [I1]" in b else b.index("# [D1]")
b = b[:r0] + ("# [I2] golden = Genus final netlist (netlist-to-netlist)\n"
              "read_design -verilog95   -golden -lastmod -noelab $env(GOLDEN_NL)\n"
              "elaborate_design -golden -root {rv32i_cpu_top}\n\n") + b[r1:]
b = sub(b, "uniquify -all -nolib -golden\n", "")
b = sub(b, "# [D2] pure name mapping, composed RTL->final by Genus' analyze_extended_mapping in leg 1\nset_analyze_option -mapping_file $env(MAPFILE)\n", "")
b = sub(b, "set_mapping_method -search_in_mapping_file\n", "")
b = sub(b, "check_mapping_setup -mapping_file_quality -summary\n", "")
b = sub(b, "    set_mapping_method -mapping_file_nopipo\n", "    # [I2] no mapping file: PIs/POs are paired by name anyway\n")
b = sub(b, "# [D1] revised = the FINAL netlist (or a negative-control mutant of it)", "# [I2] revised = the Innovus post-route logical netlist (or a negative-control mutant of it)")
open(outdir + "/lec_innovus_genus.do", "w").write(b)
print("wrote do-files in", outdir)
