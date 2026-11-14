#!/usr/bin/env python3
"""Generate the memory-map tables of the books from the SoC address-map packages.

The regions come from the elaborated constants of the packages (pyslang): the index constants
of each level, and its array of bases and its array of limits. The words come from the sidecar
docs/manual/common/facts/memory_map.yaml. It holds the files, the levels and a target and a note
for each region. The tool writes docs/manual/common/generated/map/memory-map.tex (all leaf slots in
address order, with the unmapped ranges) and memory-map-<level>.tex (the slots of one level).

Both modes prove the structure of the map and stop with a message when one rule fails:
  - a region has a limit at or above its base;
  - a region starts and ends on the page grid (page_bytes in the sidecar);
  - a leaf slot of a level with leaf_bytes has exactly that size and is aligned to it;
  - two regions of one level overlap only when the sidecar declares the override, the
    overriding region has the higher index and lies inside the overridden one;
  - a declared override overlaps its target;
  - a region lies inside the window of the entry that its level hangs below;
  - each page of a window of the first level that has levels below it is claimed by
    exactly one leaf slot of those levels.
It does not check the decode logic of the RTL or the clock and reset of a slot.

Usage:
    python tools/docs/gen_memory_map.py [--check] [--root DIR]

Exit codes:
    0  success, or every output is in sync with --check
    1  an output is stale, missing or orphaned, the sidecar and the RTL disagree on a region,
       or a rule of the map does not hold
    2  the sidecar or the RTL cannot be read, or the constants of a package disagree
    3  pyslang is not installed (pip install pyslang==11.0.0)

Doc: um:guide:fact-tables
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_doc_labels import LABEL_RE  # noqa: E402
from doc_tables import longtable  # noqa: E402
from gen_fact_tables import (  # noqa: E402
    NAME_RE,
    FactError,
    Slang,
    code,
    describe,
    load_slang,
    parse_int,
)

REPO = Path(__file__).resolve().parents[2]
SIDECAR = Path("docs/manual/common/facts/memory_map.yaml")
OUT_DIR = Path("docs/manual/common/generated/map")
LEVEL_RE = re.compile(r"^[a-z][a-z0-9-]*$")
UNITS = (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10))
ALL_COLS = ("p{28mm}", "p{20mm}", "p{30mm}", "p{30mm}", "p{31mm}")
LEVEL_COLS = ("p{9mm}", "p{33mm}", "p{27mm}", "p{17mm}", "p{25mm}", "p{28mm}")


@dataclass
class Const:
    """One constant of a package as elaborated."""

    type_text: str
    width: int
    value: str
    unpacked: bool


@dataclass
class Slot:
    """One region of a level."""

    level: str
    key: str
    constant: str
    index: int
    base: int
    limit: int
    target: str = ""
    note: str = ""

    @property
    def size(self) -> int:
        """Return the number of bytes of the region."""
        return self.limit - self.base + 1


@dataclass
class Spec:
    """The sidecar settings of one level."""

    name: str
    title: str
    protocol: str
    parent: tuple[str, str] | None
    leaf_bytes: int
    overrides: list[tuple[str, str]]


@dataclass
class Model:
    """The map: the slots of each level in index order and the settings."""

    label: str
    title: str
    unmapped: str
    page: int
    addr_max: int
    rtl: list[str]
    specs: dict[str, Spec]
    levels: dict[str, list[Slot]] = field(default_factory=dict)

    def windows(self) -> set[tuple[str, str]]:
        """Return the (level, entry) pairs that another level hangs below."""
        return {s.parent for s in self.specs.values() if s.parent}


def fmt(value: int) -> str:
    """Return an address as 0x2000_1000."""
    return f"0x{value >> 16:04X}_{value & 0xFFFF:04X}"


def human(size: int) -> str:
    """Return a size in the largest unit that divides it."""
    for unit, scale in UNITS:
        if size % scale == 0:
            return f"{size // scale} {unit}"
    return f"{size} B"


def load_sidecar(path: Path) -> dict[str, Any]:
    """Load and check the shape of the sidecar file. Raise FactError on a problem."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        raise FactError(f"cannot parse {path}: {exc}") from exc

    def bad(what: str) -> FactError:
        return FactError(f"cannot parse {path}: {what}")

    if not isinstance(data, dict) or not isinstance(data.get("levels"), dict) or not data["levels"]:
        raise bad("the top level needs 'family', 'rtl' and 'levels'")
    if data.get("family") != path.stem:
        raise bad(f"'family' must be {path.stem!r}")
    if not isinstance(data.get("label"), str) or not LABEL_RE.match(f"tab:{data['label']}"):
        raise bad("'label' must be a book label")
    for key in ("title", "unmapped"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise bad(f"'{key}' must be a text")
    rtl = data.get("rtl")
    if not isinstance(rtl, list) or not rtl or not all(isinstance(r, str) for r in rtl):
        raise bad("'rtl' must be a list of paths")
    for key, default in (("page_bytes", 4096), ("address_bits", 32)):
        data[key] = data.get(key, default)
        if not isinstance(data[key], int) or data[key] <= 0:
            raise bad(f"'{key}' must be a positive integer")
    if data["page_bytes"] & (data["page_bytes"] - 1):
        raise bad("'page_bytes' must be a power of two")
    seen: list[str] = []
    for name, lv in data["levels"].items():
        if not isinstance(name, str) or not LEVEL_RE.match(name) or not isinstance(lv, dict):
            raise bad(f"bad level {name!r}")
        for key in ("title", "protocol"):
            if not isinstance(lv.get(key), str) or not lv[key].strip():
                raise bad(f"level {name}: '{key}' must be a text")
        for key in ("package", "prefix", "count", "base", "limit"):
            if not isinstance(lv.get(key), str) or not NAME_RE.match(lv[key]):
                raise bad(f"level {name}: '{key}' must be a name")
        entries = lv.get("entries")
        ok = isinstance(entries, dict) and entries
        if not ok or not all(
            NAME_RE.match(str(k)) and isinstance(v, dict) for k, v in entries.items()
        ):
            raise bad(f"level {name}: 'entries' must map names to mappings")
        for key, info in entries.items():
            for field_name in ("target", "note"):
                if not str(info.get(field_name) or "").strip():
                    raise bad(f"level {name}: entry {key}: '{field_name}' is empty")
        parent = lv.get("parent")
        if parent is None and seen or parent is not None and not seen:
            raise bad(f"level {name}: only the first level has no 'parent'")
        if parent is not None:
            lvl = parent.get("level") if isinstance(parent, dict) else None
            if lvl not in seen or parent.get("entry") not in data["levels"][lvl]["entries"]:
                raise bad(f"level {name}: 'parent' must name an entry of an earlier level")
        lv["leaf_bytes"] = lv.get("leaf_bytes", 0)
        if not isinstance(lv["leaf_bytes"], int) or lv["leaf_bytes"] < 0:
            raise bad(f"level {name}: 'leaf_bytes' must be a size in bytes")
        lv["overrides"] = lv.get("overrides") or []
        for ov in lv["overrides"]:
            if not isinstance(ov, dict) or not {ov.get("entry"), ov.get("over")} <= set(entries):
                raise bad(f"level {name}: an override must name two entries of the level")
        seen.append(name)
    return data


def compile_files(sl: Slang, files: list[Path]) -> Any:
    """Compile the files. Raise FactError on a parse or elaboration error."""
    d = sl.driver()
    d.addStandardArgs()
    names = " ".join(f'"{f.as_posix()}"' if " " in str(f) else f.as_posix() for f in files)
    if not (
        d.parseCommandLine(f"slang {names}", sl.options())
        and d.processOptions()
        and d.parseAllSources()
    ):
        raise FactError(f"cannot parse {files[0]}: slang could not load the files")
    comp = d.createCompilation()
    errors = [x for x in comp.getAllDiagnostics() if x.isError()]
    if errors:
        engine = sl.pyslang.DiagnosticEngine(comp.sourceManager)
        client = sl.pyslang.TextDiagnosticClient()
        engine.addClient(client)
        for e in errors[:5]:
            engine.issue(e)
        raise FactError(
            f"cannot parse {files[0]}: elaboration errors\n{client.getString().strip()}"
        )
    return comp


def package_constants(comp: Any, name: str) -> dict[str, Const]:
    """Return the elaborated parameters of a package by name."""
    pkg = comp.getPackage(name)
    if pkg is None:
        raise FactError(f"package {name} not found in the RTL files of the sidecar")
    out: dict[str, Const] = {}
    for sym in pkg:
        if type(sym).__name__ == "ParameterSymbol":
            typ = sym.type
            out[sym.name] = Const(
                str(typ), int(typ.bitWidth), str(sym.value), bool(typ.isUnpackedArray)
            )
    return out


def array_values(level: str, consts: dict[str, Const], name: str, count: int) -> list[int]:
    """Return the elements of an array constant, packed or unpacked, one integer each."""
    const = consts.get(name)
    if const is None:
        raise FactError(f"{level}: constant {name} not found in the package")
    if const.unpacked:
        raw = const.value.strip()
        parts = raw[1:-1].split(",") if raw.startswith("[") and raw.endswith("]") else []
        values = [None if "[" in p else parse_int(p) for p in parts]
    else:
        total = parse_int(const.value)
        if total is None or count == 0 or const.width % count:
            raise FactError(f"{level}: constant {name} is not an array of {count} elements")
        step = const.width // count
        values = [(total >> (i * step)) & ((1 << step) - 1) for i in range(count)]
    if len(values) != count or None in values:
        raise FactError(f"{level}: constant {name} must hold {count} integer elements")
    return [v for v in values if v is not None]


def read_level(name: str, lv: dict[str, Any], consts: dict[str, Const]) -> list[Slot]:
    """Return the slots of one level from the index constants and the two arrays."""
    prefix = lv["prefix"]
    count_const = consts.get(lv["count"])
    count = parse_int(count_const.value) if count_const else None
    if count is None:
        raise FactError(f"{name}: constant {lv['count']} not found or not an integer")
    index: dict[str, int] = {}
    for cname, const in consts.items():
        if cname.startswith(prefix) and cname != lv["count"] and const.type_text == "int unsigned":
            value = parse_int(const.value)
            if value is None:
                raise FactError(f"{name}: constant {cname} is not an integer")
            index[cname[len(prefix) :]] = value
    if sorted(index.values()) != list(range(count)):
        raise FactError(
            f"{name}: {len(index)} index constants {prefix}* but {lv['count']} is {count}, "
            "or the indexes are not 0 up to the count"
        )
    bases = array_values(name, consts, lv["base"], count)
    limits = array_values(name, consts, lv["limit"], count)
    slots = [
        Slot(name, key, prefix + key, i, bases[i], limits[i])
        for key, i in sorted(index.items(), key=lambda kv: kv[1])
    ]
    return slots


def build(sl: Slang, root: Path, data: dict[str, Any]) -> tuple[Model, list[str]]:
    """Return the model of the map and the findings of the two-way check with the sidecar."""
    files = [root / f for f in data["rtl"]]
    for f in files:
        if not f.is_file():
            raise FactError(f"cannot parse {f}: file does not exist")
    comp = compile_files(sl, files)
    specs = {
        n: Spec(
            n,
            lv["title"],
            lv["protocol"],
            (lv["parent"]["level"], lv["parent"]["entry"]) if lv.get("parent") else None,
            lv["leaf_bytes"],
            [(o["entry"], o["over"]) for o in lv["overrides"]],
        )
        for n, lv in data["levels"].items()
    }
    model = Model(
        data["label"],
        data["title"],
        data["unmapped"],
        data["page_bytes"],
        (1 << data["address_bits"]) - 1,
        data["rtl"],
        specs,
    )
    findings: list[str] = []
    cache: dict[str, dict[str, Const]] = {}
    for name, lv in data["levels"].items():
        pkg = lv["package"]
        if pkg not in cache:
            cache[pkg] = package_constants(comp, pkg)
        slots = read_level(name, lv, cache[pkg])
        entries = lv["entries"]
        for s in slots:
            if s.key not in entries:
                findings.append(f"{name}: RTL region {s.key} ({s.constant}) has no sidecar entry")
                continue
            s.target, s.note = str(entries[s.key]["target"]), str(entries[s.key]["note"])
        keys = {s.key for s in slots}
        findings += [
            f"{name}: sidecar entry {k} has no region in the RTL" for k in entries if k not in keys
        ]
        model.levels[name] = slots
    return model, findings


def span(slot: Slot) -> str:
    """Return the range of a slot as text."""
    return f"{fmt(slot.base)}-{fmt(slot.limit)}"


def is_leaf(model: Model, slot: Slot) -> bool:
    """Return True when no level hangs below the slot."""
    return (slot.level, slot.key) not in model.windows()


def descendants(model: Model, level: str, key: str) -> list[Slot]:
    """Return the leaf slots of every level below an entry."""
    out: list[Slot] = []
    for name, spec in model.specs.items():
        if spec.parent == (level, key):
            for s in model.levels[name]:
                out += [s] if is_leaf(model, s) else descendants(model, name, s.key)
    order = list(model.specs)
    return sorted(out, key=lambda s: (s.base, order.index(s.level), s.index))


def find_slot(model: Model, level: str, key: str) -> Slot | None:
    """Return the slot of an entry, or None when the RTL has no such region."""
    return next((s for s in model.levels[level] if s.key == key), None)


def overlap(a: Slot, b: Slot) -> bool:
    """Return True when two slots share an address."""
    return a.base <= b.limit and b.base <= a.limit


def check_level(model: Model, spec: Spec, slots: list[Slot], bad: set[int]) -> list[str]:
    """Return the findings of one level: form, grid, leaf size, overlap and overrides."""
    out: list[str] = []
    lvl = spec.name
    for s in slots:
        if s.limit < s.base:
            out.append(f"{lvl}: {s.key}: the limit {fmt(s.limit)} is below the base {fmt(s.base)}")
            bad.add(id(s))
            continue
        if s.base % model.page or (s.limit + 1) % model.page:
            out.append(f"{lvl}: {s.key} ({span(s)}) is not aligned to {model.page} bytes")
        if spec.leaf_bytes and is_leaf(model, s):
            if s.size != spec.leaf_bytes:
                out.append(f"{lvl}: {s.key} must be {spec.leaf_bytes} bytes and is {s.size} bytes")
            elif s.base % spec.leaf_bytes:
                out.append(f"{lvl}: {s.key} is not aligned to its size of {spec.leaf_bytes} bytes")
    good = [s for s in slots if id(s) not in bad]
    declared = set(spec.overrides)
    overlapping: set[tuple[str, str]] = set()
    for i, a in enumerate(good):
        for b in good[i + 1 :]:
            if not overlap(a, b):
                continue
            overlapping.add((a.key, b.key))
            if (a.key, b.key) not in declared and (b.key, a.key) not in declared:
                out.append(f"{lvl}: {a.key} and {b.key} overlap and no override is declared")
    for entry, over in spec.overrides:
        top, low = find_slot(model, lvl, entry), find_slot(model, lvl, over)
        if top is None or low is None or id(top) in bad or id(low) in bad:
            continue
        head = f"{lvl}: override {entry} over {over}"
        if not overlap(top, low):
            out.append(f"{head}: the windows do not overlap")
        elif top.index < low.index:
            out.append(f"{head}: {entry} must have a higher index than {over}")
        elif top.base < low.base or top.limit > low.limit:
            out.append(f"{head}: {entry} must lie inside {over}")
    return out


def check_pages(model: Model, window: Slot) -> list[str]:
    """Return the findings for the pages of a window: each has exactly one owning leaf slot."""
    leaves = descendants(model, window.level, window.key)
    out: list[str] = []
    for page in range(window.base, window.limit + 1, model.page):
        owners = [s for s in leaves if s.base <= page <= s.limit]
        head = f"{window.level}: {window.key}: page {fmt(page)} is claimed by"
        if not owners:
            out.append(f"{head} no slot")
        elif len(owners) > 1:
            names = ", ".join(f"{s.level} {s.key}" for s in owners)
            out.append(f"{head} {len(owners)} slots ({names})")
    return out


def check_map(model: Model) -> list[str]:
    """Return the findings of the structure checks. An empty list means the map holds."""
    out: list[str] = []
    bad: set[int] = set()
    first = next(iter(model.specs))
    for name, spec in model.specs.items():
        out += check_level(model, spec, model.levels[name], bad)
        if spec.parent:
            parent = find_slot(model, *spec.parent)
            if parent is None or id(parent) in bad:
                continue
            for s in model.levels[name]:
                if id(s) not in bad and (s.base < parent.base or s.limit > parent.limit):
                    out.append(
                        f"{name}: {s.key} ({span(s)}) lies outside {parent.level} {parent.key}"
                    )
    for s in model.levels[first]:
        if id(s) not in bad and not is_leaf(model, s):
            out += check_pages(model, s)
    return out


def path_of(model: Model, slot: Slot) -> str:
    """Return the access path of a slot: the protocol and the slot index of each level."""
    parts = []
    cur: Slot | None = slot
    while cur is not None:
        spec = model.specs[cur.level]
        parts.append(f"{spec.protocol} slot {cur.index}")
        cur = find_slot(model, *spec.parent) if spec.parent else None
    return ", ".join(reversed(parts))


def range_cell(base: int, limit: int) -> str:
    """Return the Range cell: the first and the last address on two lines."""
    return f"\\code{{{fmt(base)}}}\\newline\\code{{{fmt(limit)}}}"


def combined_rows(model: Model) -> list[list[str]]:
    """Return the rows of the table in address order: leaf slots and the unmapped ranges."""
    first = next(iter(model.specs))
    rows: list[list[str]] = []

    def gap(base: int, limit: int) -> None:
        rows.append(
            [
                range_cell(base, limit),
                human(limit - base + 1),
                "none",
                "-",
                describe(model.unmapped),
            ]
        )

    cursor = 0
    for region in sorted(model.levels[first], key=lambda s: s.base):
        if region.base > cursor:
            gap(cursor, region.base - 1)
        for s in [region] if is_leaf(model, region) else descendants(model, first, region.key):
            rows.append(
                [
                    range_cell(s.base, s.limit),
                    human(s.size),
                    describe(s.target),
                    describe(path_of(model, s)),
                    describe(s.note),
                ]
            )
        cursor = region.limit + 1
    if cursor <= model.addr_max:
        gap(cursor, model.addr_max)
    return rows


def level_rows(slots: list[Slot]) -> list[list[str]]:
    """Return the rows of the table of one level, in index order."""
    return [
        [
            str(s.index),
            code(s.constant),
            range_cell(s.base, s.limit),
            human(s.size),
            describe(s.target),
            describe(s.note),
        ]
        for s in slots
    ]


def header_line(model: Model) -> str:
    """Return the first line of each generated file."""
    sources = ", ".join(model.rtl)
    return (
        f"% Generated by tools/docs/gen_memory_map.py from {sources} "
        f"and {SIDECAR.as_posix()}. Do not edit."
    )


def render(model: Model) -> dict[str, str]:
    """Return the text of each output file by file name."""
    head = header_line(model)
    outputs = {
        "memory-map.tex": head
        + "\n"
        + longtable(
            ALL_COLS,
            describe(model.title),
            f"tab:{model.label}:all",
            ["Range", "Size", "Target", "Path", "Note"],
            combined_rows(model),
        )
        + "\n"
    }
    for name, spec in model.specs.items():
        outputs[f"memory-map-{name}.tex"] = (
            head
            + "\n"
            + longtable(
                LEVEL_COLS,
                describe(spec.title),
                f"tab:{model.label}:{name}",
                ["Slot", "Constant", "Range", "Size", "Target", "Note"],
                level_rows(model.levels[name]),
            )
            + "\n"
        )
    return outputs


def main(argv: list[str] | None = None) -> int:
    """Run the command line tool."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="fail if an output is stale")
    ap.add_argument("--root", type=Path, default=REPO)
    args = ap.parse_args(argv)
    root = args.root.resolve()
    sidecar = root / SIDECAR
    if not sidecar.is_file():
        print(f"gen_memory_map: no sidecar file {sidecar}", file=sys.stderr)
        return 2
    try:
        sl = load_slang()
    except ImportError:
        print(
            "gen_memory_map: pyslang is not installed: pip install pyslang==11.0.0",
            file=sys.stderr,
        )
        return 3
    try:
        model, findings = build(sl, root, load_sidecar(sidecar))
        findings += check_map(model)
        outputs = {} if findings else render(model)
    except FactError as exc:
        print(f"gen_memory_map: {exc}", file=sys.stderr)
        return 2
    for line in findings:
        print(f"gen_memory_map: {line}")
    if findings:
        return 1
    out_dir = root / OUT_DIR
    files = {out_dir / name: text for name, text in outputs.items()}
    orphans = (
        [p for p in sorted(out_dir.glob("*.tex")) if p not in files] if out_dir.is_dir() else []
    )
    if args.check:
        stale = 0
        for path, text in sorted(files.items()):
            current = path.read_bytes().replace(b"\r\n", b"\n") if path.exists() else None
            if current != text.encode("utf-8"):
                state = "missing" if current is None else "out of date"
                print(f"gen_memory_map: {path.relative_to(root).as_posix()} is {state}")
                stale += 1
        for path in orphans:
            print(
                f"gen_memory_map: {path.relative_to(root).as_posix()} "
                "is not produced by the sidecar"
            )
            stale += 1
        if stale:
            print("gen_memory_map: run python tools/docs/gen_memory_map.py")
            return 1
        print(f"gen_memory_map: {len(files)} files are in sync")
        return 0
    for path in orphans:
        path.unlink()
        print(f"gen_memory_map: deleted {path.relative_to(root).as_posix()} (no sidecar)")
    for path, text in sorted(files.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print(f"gen_memory_map: wrote {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
