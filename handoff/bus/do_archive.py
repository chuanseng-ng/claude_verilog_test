"""Cut the moved blocks out of the books and paste them unchanged into the source archive.

Writes: pra/base/<file> (originals), pra/old/<slug>.tex (moved blocks), pra/manifest.json.
"""
import hashlib
import json
import shutil
from pathlib import Path

REPO = Path(r"<repo>")
PRA = Path(r"<scratchpad>\bus\pra")
M = REPO / "docs/manual"
F_DS03 = M / "ds/parts/03-module-contracts.tex"
F_DS01 = M / "ds/parts/01-architecture.tex"
F_TM01 = M / "tm/parts/01-module-reference.tex"
F_CR06 = M / "cr/parts/06-source-archive.tex"


def read_lines(p):
    text = p.read_bytes().decode("utf-8")
    assert "\r" not in text, p
    return text.split("\n")  # last element is '' when the file ends with a newline


def write_lines(p, lines):
    p.write_bytes("\n".join(lines).encode("utf-8"))


def sha(lines):
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


(PRA / "base").mkdir(exist_ok=True)
(PRA / "old").mkdir(exist_ok=True)
for f in (F_DS03, F_DS01, F_TM01, F_CR06):
    shutil.copyfile(f, PRA / "base" / f.name)

ds03 = read_lines(F_DS03)
ds01 = read_lines(F_DS01)
tm01 = read_lines(F_TM01)
cr06 = read_lines(F_CR06)
manifest = {}


def section_block(lines, label):
    i = next(n for n, l in enumerate(lines) if l.startswith("\\section") and "\\label{%s}" % label in l)
    j = next(n for n in range(i, len(lines)) if lines[n].startswith("\\begin{relocated}"))
    k = next(n for n in range(j, len(lines)) if lines[n] == "\\end{relocated}")
    rm_end = k + 1 if lines[k + 1] == "" else k
    return i, j, k, rm_end


def cut_section(lines, label, slug):
    i, j, k, rm_end = section_block(lines, label)
    block = lines[j:k + 1]
    (PRA / "old" / (slug + ".tex")).write_bytes(("\n".join(block) + "\n").encode("utf-8"))
    manifest[slug] = {"sha256": sha(block), "lines": len(block), "source_label": label}
    return block, lines[:i] + lines[rm_end + 1:]


arch_ds = []
arch_tm = []

# ---- DS module sections -------------------------------------------------------
titles = {
    "ds:mod:soc-addr-map-pkg": ("ds-soc-addr-map-pkg", "soc/soc\\_addr\\_map\\_pkg.sv"),
    "ds:mod:soc-bus": ("ds-soc-bus", "soc/soc\\_bus.sv"),
    "ds:mod:soc-periph-map-pkg": ("ds-soc-periph-map-pkg", "soc/soc\\_periph\\_map\\_pkg.sv"),
}
for label, (slug, title) in titles.items():
    block, ds03 = cut_section(ds03, label, slug)
    arch_ds.append([
        "\\section{\\texttt{%s}}\\label{cr:arc:%s}" % (title, slug), "",
        "This text was in the Design Specification section \\cref{%s}. The authored section replaced it. The text is unchanged." % label,
        "", *block, "",
    ])

# ---- TM crossbar --------------------------------------------------------------
block, tm01 = cut_section(tm01, "tm:mod:axi4-crossbar", "tm-axi4-crossbar")
arch_tm.append([
    "\\section{\\texttt{soc/axi4\\_crossbar.sv}}\\label{cr:arc:tm-axi4-crossbar}", "",
    "This text was in the Technical Manual section \\cref{tm:mod:axi4-crossbar}. The authored section replaced it. The text is unchanged.",
    "", *block, "",
])

# ---- MEMORY_MAP spans ---------------------------------------------------------
s1 = ds01.index("Complete address space allocation for RV32I SoC")
e1 = ds01.index("See Global Memory Map above.")
assert ds01[e1 + 1] == "" and ds01[e1 + 2].startswith("\\subsection{Detailed Register Maps}")
span1 = ds01[s1:e1 + 1]
s2 = next(n for n, l in enumerate(ds01) if l.startswith("\\subsection{Reset and Trap Vectors}"))
ih = next(n for n, l in enumerate(ds01) if l.startswith("\\subsubsection{Interrupt Hierarchy (Phase 5)}"))
assert ds01[ih - 1] == "" and ds01[ih - 2] == "\\end{itemize}"
e2 = ih - 2
span2 = ds01[s2:e2 + 1]
s3 = next(n for n, l in enumerate(ds01) if l.startswith("\\subsection{Testing Recommendations}"))
e3 = next(n for n in range(s3, len(ds01)) if ds01[n] == "\\end{relocated}") - 1
assert ds01[e3] == "\\end{itemize}"
span3 = ds01[s3:e3 + 1]
assert s1 < e1 < s2 < e2 < s3 < e3
for slug, sp in (("ds-memory-map-1", span1), ("ds-memory-map-2", span2), ("ds-memory-map-3", span3)):
    (PRA / "old" / (slug + ".tex")).write_bytes(("\n".join(sp) + "\n").encode("utf-8"))
    manifest[slug] = {"sha256": sha(sp), "lines": len(sp)}
# remove from the end first so the indices stay valid
ds01 = ds01[:s3] + ds01[e3 + 1:]
ds01 = ds01[:s2] + ds01[ih:]
ds01 = ds01[:s1] + ds01[e1 + 2:]
old_intro = "This chapter gives the address space. It lists the register map of each block."
n_intro = ds01.index(old_intro)
ds01[n_intro] = "The address map of the SoC and the rules for it are in \\cref{ds:ch:mod-bus-fabric:memory-map}. This chapter lists the register map of each block."

arch_ds.append([
    "\\section{\\texttt{docs/design/MEMORY\\_MAP.md}}\\label{cr:arc:ds-memory-map}", "",
    "This text was in the Design Specification chapter \\cref{ds:ch:memory-map}. The authored section \\cref{ds:ch:mod-bus-fabric:memory-map} replaced it. The register maps of the blocks stay in the chapter \\cref{ds:ch:memory-map}. The text is unchanged. The labels inside the text are the labels of the old document. The text has three parts, and each part is in its own block.",
    "", "\\begin{relocated}{docs/design/MEMORY_MAP.md}", *span1, "\\end{relocated}",
    "", "\\begin{relocated}{docs/design/MEMORY_MAP.md}", *span2, "\\end{relocated}",
    "", "\\begin{relocated}{docs/design/MEMORY_MAP.md}", *span3, "\\end{relocated}",
    "",
])

# ---- inputs and pointer sentences -------------------------------------------
i_pow = ds03.index("\\input{parts/chapters/power}")
ds03.insert(i_pow + 1, "")
ds03.insert(i_pow + 2, "\\input{parts/chapters/bus}")
n = next(k for k, l in enumerate(ds03) if l.startswith("This chapter states the contract of each module in this area. The area holds the crossbar"))
ds03[n] = ds03[n].replace(
    "The PMU is in \\cref{ds:ch:mod-power-management}.",
    "The PMU is in \\cref{ds:ch:mod-power-management}. The memory map, the crossbar and the contract on masters and slaves are in \\cref{ds:ch:mod-bus-fabric}.")
assert "ds:ch:mod-bus-fabric" in ds03[n]

i_pow = tm01.index("\\input{parts/chapters/power}")
tm01.insert(i_pow + 1, "")
tm01.insert(i_pow + 2, "\\input{parts/chapters/bus}")
n = next(k for k, l in enumerate(tm01) if l.startswith("This chapter describes how each module in this area works. The area holds the crossbar"))
tm01[n] = tm01[n].replace(
    "The PMU is in \\cref{tm:ch:mod-power-management}.",
    "The PMU is in \\cref{tm:ch:mod-power-management}. The fabric topology and the crossbar are in \\cref{tm:ch:mod-bus-fabric}.")
assert "tm:ch:mod-bus-fabric" in tm01[n]

# ---- archive insertion ----------------------------------------------------------
i_tm = cr06.index("\\chapter{Archived Technical Manual text}\\label{cr:ch:source-archive-tm}")
flat = [l for part in arch_ds for l in part]
cr06 = cr06[:i_tm] + flat + cr06[i_tm:]
i_um = next(k for k, l in enumerate(cr06) if l.startswith("\\chapter{Archived User Manual text}"))
flat = [l for part in arch_tm for l in part]
cr06 = cr06[:i_um] + flat + cr06[i_um:]

write_lines(F_DS03, ds03)
write_lines(F_DS01, ds01)
write_lines(F_TM01, tm01)
write_lines(F_CR06, cr06)
(PRA / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2))
