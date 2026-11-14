"""Every line that left a book is in the archive, except the lines that the report lists."""
from collections import Counter
from pathlib import Path

REPO = Path(r"<repo>")
PRA = Path(r"<scratchpad>\bus\pra")
M = REPO / "docs/manual"
arch = set((M / "cr/parts/06-source-archive.tex").read_bytes().decode("utf-8").split("\n"))
pairs = [("03-module-contracts.tex", M / "ds/parts/03-module-contracts.tex"),
         ("01-architecture.tex", M / "ds/parts/01-architecture.tex"),
         ("01-module-reference.tex", M / "tm/parts/01-module-reference.tex")]
tot_removed = 0
for name, new in pairs:
    base = (PRA / "base" / name).read_bytes().decode("utf-8").split("\n")
    cur = new.read_bytes().decode("utf-8").split("\n")
    removed = Counter(base) - Counter(cur)
    added = Counter(cur) - Counter(base)
    print("==", name, "removed distinct lines:", len(removed), "total:", sum(removed.values()), "added lines:", sum(added.values()))
    for line, n in removed.items():
        tot_removed += n
        if line.strip() and line not in arch:
            print("   NOT IN ARCHIVE:", line[:110])
    for line in added:
        if line.strip():
            print("   ADDED:", line[:110])
