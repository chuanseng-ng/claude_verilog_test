"""Archive proofs: hash identity, absence from the books, line runs, negative controls."""
import hashlib
import json
import re
from pathlib import Path

REPO = Path(r"<repo>")
PRA = Path(r"<scratchpad>\bus\pra")
M = REPO / "docs/manual"
manifest = json.loads((PRA / "manifest.json").read_text(encoding="utf-8"))


def rd(p):
    return Path(p).read_bytes().decode("utf-8")


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


archive = rd(M / "cr/parts/06-source-archive.tex")
new_books = {
    "ds03": rd(M / "ds/parts/03-module-contracts.tex"),
    "ds01": rd(M / "ds/parts/01-architecture.tex"),
    "tm01": rd(M / "tm/parts/01-module-reference.tex"),
}
all_new = "\n".join(new_books.values())


def archived_blocks(slug):
    """Return the list of block texts that the archive holds for a slug."""
    label = "cr:arc:" + slug if slug != "ds-memory-map" else "cr:arc:ds-memory-map"
    i = archive.index("\\label{%s}" % label)
    j = archive.index("\n\\section", i) if "\n\\section" in archive[i:] else len(archive)
    nxt = [archive.find(s, i) for s in ("\n\\section", "\n\\chapter")]
    nxt = [n for n in nxt if n > 0]
    sec = archive[i:min(nxt)]
    blocks = []
    pos = 0
    while True:
        b = sec.find("\\begin{relocated}", pos)
        if b < 0:
            break
        # a block body starts after the begin line and ends before the end line
        bl_end = sec.index("\n", b)
        e = sec.index("\n\\end{relocated}", bl_end)
        blocks.append((sec[b:bl_end], sec[bl_end + 1:e]))
        pos = e + 1
    return blocks


def runs(text):
    out, cur = [], []
    for line in text.split("\n"):
        if line.strip() == "":
            if cur:
                out.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        out.append(cur)
    return out


def contiguous_count(hay_lines, run):
    n = len(run)
    return sum(1 for k in range(len(hay_lines) - n + 1) if hay_lines[k:k + n] == run)


def line_run_check(old_text, arch_text):
    hay = arch_text.split("\n")
    missing = []
    total = 0
    for r in runs(old_text):
        total += 1
        if contiguous_count(hay, r) < 1:
            missing.append(r[0][:60])
    return total, missing


results = []
ok_all = True
singles = ["ds-soc-addr-map-pkg", "ds-soc-bus", "ds-soc-periph-map-pkg", "tm-axi4-crossbar"]
for slug in singles:
    blocks = archived_blocks(slug)
    assert len(blocks) == 1, (slug, len(blocks))
    head, body = blocks[0]
    block_full = head + "\n" + body + "\n\\end{relocated}"
    old = rd(PRA / "old" / (slug + ".tex"))
    h_old, h_arc = sha(old), sha(block_full + "\n")
    ident = (h_old == h_arc == manifest[slug]["sha256"])
    absent = old.rstrip("\n") not in all_new
    tot, miss = line_run_check(old, archive)
    ok = ident and absent and not miss
    ok_all &= ok
    results.append((slug, ident, absent, tot, len(miss)))

# memory map: three blocks, in order
blocks = archived_blocks("ds-memory-map")
assert len(blocks) == 3, len(blocks)
for n, (head, body) in enumerate(blocks, 1):
    slug = "ds-memory-map-%d" % n
    old = rd(PRA / "old" / (slug + ".tex"))
    h_arc = sha(body + "\n")
    ident = (sha(old) == h_arc == manifest[slug]["sha256"])
    absent = old.rstrip("\n") not in all_new
    tot, miss = line_run_check(old, archive)
    ok_all &= ident and absent and not miss
    results.append((slug, ident, absent, tot, len(miss)))

print("slug, hash-identical, absent-from-books, line-runs, runs-missing")
for r in results:
    print(r)
print("ALL OK" if ok_all else "FAILED")

# negative controls
# 1. hash: change one character inside the archived text of one block
slug = "ds-soc-bus"
old = rd(PRA / "old" / (slug + ".tex"))
bad_arch = archive.replace("single source of truth", "single source of trutH", 1)
assert bad_arch != archive
head, body = archived_blocks(slug)[0]
body_bad = body.replace("single source of truth", "single source of trutH", 1)
print("negative control 1 (hash after one-character change):",
      "detected" if sha(head + "\n" + body_bad + "\n\\end{relocated}\n") != manifest[slug]["sha256"] else "NOT DETECTED")
# 2. line run: the same change must make a run missing
tot, miss = line_run_check(old, bad_arch)
print("negative control 2 (line runs after one-character change): missing runs =", len(miss),
      "detected" if miss else "NOT DETECTED")
# 3. a one-character change in the old text must be caught by the absence test (text still in books)
print("negative control 3 (a block that is still in a book is found):",
      "detected" if (rd(PRA / "base" / "03-module-contracts.tex").count(old.rstrip("\n")) == 1) else "NOT DETECTED")
