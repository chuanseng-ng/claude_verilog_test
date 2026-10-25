#!/usr/bin/env python3
"""Turn the project's committed filelist into the per-tool source lists of the DQC flow.

The RTL list is NOT forked: it is read from ``rtl/filelist/<top>.f`` (generated from the
authoritative Make variables by tools/verif/gen_filelist.py).  This script only

  * resolves the repo-root-relative paths to absolute ones (SpyGlass and HAL run from a run dir),
  * appends the port-only SRAM black-box stubs of the selected arm (dqc/stubs/), and
  * emits  <out>/sources.sgf   one file per line (SpyGlass ``read_file -type sourcelist``)
           <out>/sources.f     the same plus ``-incdir`` / ``-define`` for HAL / xrun style tools
           <out>/incdirs.txt   include directories, one per line
           <out>/defines.txt   preprocessor defines, one per line

The behavioural SRAM models of ``<top>_sim_models.f`` are deliberately NOT used: see
dqc/stubs/sram_macros_bbox.sv for why the macros are black boxes.

Stdlib only (the EDA host's python is 3.8).
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DQC = os.path.dirname(HERE)
REPO = os.path.dirname(DQC)

ARMS = {
    # arm name -> (defines, stub files).  Defines match how the arm is built elsewhere:
    #   default  : the cocotb regression arm (rtl/filelist/README.md "Defines")
    #   sky130   : the Sky130 SoC harden arm (pnr/Makefile SOC_SV2V_DEFINES uses SRAM_SKY130 + __pnr__)
    "default": ([], ["sram_macros_bbox.sv", "sram_macros_gpu_bbox.sv"]),
    "sky130": (["SRAM_SKY130"], ["sram_macros_sky130_bbox.sv", "sram_macros_gpu_bbox.sv"]),
}


# --- SpyGlass front-end overlay ---------------------------------------------------------------
# SpyGlass rules SYNTH_5260 (SystemVerilog `string`) and SYNTH_5247 (`real` parameter used in a
# non-delay expression) are *SynthesisError*s whose stated consequence is that "the module in which
# this violation is reported is considered as a black box for which no SpyGlass analysis is done"
# (Built-In Rules Reference).  On this SoC that would black-box soc_top itself, pll_subsystem,
# pll_clkgen and boot_rom, so a CDC/RDC run on it would analyse nothing of the top-level wiring.
# The affected parameters are elaboration-time configuration only (a hex file name, the PLL model
# selector "STUB"/"RNM", and RNM-only real constants in a generate branch that is pruned by the
# default PLL_IMPL=="STUB"), so the DQC flow reads a LINE-COUNT-PRESERVING overlay in which
#     parameter string NAME = ...   ->   parameter NAME = ...        (untyped: a string literal is a
#                                                                    bit vector, == "STUB" still works)
#     parameter real   NAME = 1.3e9 ->   parameter NAME = 0          (RNM-only; see above)
# rtl/ is never modified; line numbers in every SpyGlass/HAL report still match rtl/.
STRING_PARAM = re.compile(r"\bparameter(\s+)string\b")
REAL_PARAM = re.compile(r"\bparameter\s+real(\s+\w+\s*=\s*)[-+0-9.eE_]+")


def overlay_text(text):
    out = STRING_PARAM.sub(lambda m: "parameter" + m.group(1) + "      ", text)
    out = REAL_PARAM.sub(lambda m: "parameter" + m.group(1) + "0", out)
    return out


def parse_f(path):
    files, incdirs = [], []
    for raw in open(path):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("+incdir+"):
            incdirs.append(line[len("+incdir+"):])
        elif line.startswith("+") or line.startswith("-"):
            raise SystemExit("unsupported filelist option in %s: %s" % (path, line))
        else:
            files.append(line)
    return files, incdirs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", default="soc_top")
    ap.add_argument("--arm", default="default", choices=sorted(ARMS))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    flist = os.path.join(REPO, "rtl", "filelist", a.top + ".f")
    if not os.path.isfile(flist):
        raise SystemExit("missing %s (python3 tools/verif/gen_filelist.py)" % flist)
    files, incdirs = parse_f(flist)
    defines, stubs = ARMS[a.arm]

    os.makedirs(a.out, exist_ok=True)
    absfiles = []
    overlaid = []
    for f in files:
        p = os.path.join(REPO, f)
        if not os.path.isfile(p):
            raise SystemExit("listed file does not exist: %s" % p)
        src = open(p).read()
        new = overlay_text(src)
        if new != src:
            assert new.count("\n") == src.count("\n"), "overlay changed line count: " + f
            q = os.path.join(a.out, "overlay", f)
            os.makedirs(os.path.dirname(q), exist_ok=True)
            with open(q, "w") as fh:
                fh.write(new)
            overlaid.append(f)
            p = q
        absfiles.append(p)
    with open(os.path.join(a.out, "overlay.txt"), "w") as fh:
        fh.write("\n".join(overlaid) + ("\n" if overlaid else ""))
    for s in stubs:
        absfiles.append(os.path.join(DQC, "stubs", s))
    absinc = [os.path.join(REPO, d) for d in incdirs]

    with open(os.path.join(a.out, "sources.sgf"), "w") as fh:
        fh.write("\n".join(absfiles) + "\n")
    with open(os.path.join(a.out, "incdirs.txt"), "w") as fh:
        fh.write("\n".join(absinc) + "\n")
    with open(os.path.join(a.out, "defines.txt"), "w") as fh:
        fh.write("\n".join(defines) + ("\n" if defines else ""))
    with open(os.path.join(a.out, "sources.f"), "w") as fh:
        for d in absinc:
            fh.write("-incdir %s\n" % d)
        for d in defines:
            fh.write("-define %s\n" % d)
        fh.write("\n".join(absfiles) + "\n")
    print("gen_sourcelist: top=%s arm=%s files=%d (incl. %d stub, %d overlaid) incdirs=%d defines=%s"
          % (a.top, a.arm, len(absfiles), len(stubs), len(overlaid), len(absinc), ",".join(defines) or "-"))


if __name__ == "__main__":
    sys.exit(main())
