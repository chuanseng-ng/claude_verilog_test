#!/usr/bin/env python3
"""Generate the signal and parameter tables of the books from the RTL.

The ports and parameters come from the RTL (pyslang). The words come from a sidecar file,
docs/manual/common/facts/<family>.yaml, which holds a description for each port and parameter.
The tool writes docs/manual/common/generated/facts/<module>-signals.tex and -params.tex.
Without --family it also finds a generated file that no sidecar produces: --check reports it
and a normal run deletes it.

Usage:
    python tools/docs/gen_fact_tables.py [--family NAME] [--check] [--root DIR]

Exit codes:
    0  success, or every output is in sync with --check
    1  an output is stale, missing or orphaned, or the sidecar lacks an entry or has a stale one
    2  the sidecar or the RTL cannot be parsed, or the two passes disagree
    3  pyslang is not installed (pip install pyslang==11.0.0)
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_doc_labels import LABEL_RE  # noqa: E402
from doc_tables import longtable  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FACTS_DIR = Path("docs/manual/common/facts")
OUT_DIR = Path("docs/manual/common/generated/facts")
DOMAIN_WORDS = ("clock", "async", "quasi-static")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
LITERAL_RE = re.compile(r"^-?(?:\d[\d_]*|\d*'[sS]?[bBdDhHoO][0-9a-fA-FxXzZ_?]+|'[01xXzZ])$")
CODE_SPAN_RE = re.compile(r"^[A-Za-z0-9_.:/\[\]()=+*<>',!-]*$")
BUILTIN_TYPES = ("", "logic", "bit", "reg", "wire")
SIZED_DIMS = ("RangeDimensionSpecifier",)
OTHER_SIDECARS = ("memory_map",)  # in the same directory, read by gen_memory_map.py
DIRECTIONS = {"input": "in", "output": "out", "inout": "inout", "in": "in", "out": "out"}
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
SIGNAL_COLS = ("p{31mm}", "p{9mm}", "p{19mm}", "p{22mm}", "p{58mm}")
PARAM_COLS = ("p{30mm}", "p{27mm}", "p{19mm}", "p{20mm}", "p{45mm}")


class FactError(Exception):
    """The sidecar or the RTL cannot be parsed. The exit code is 2."""


@dataclass
class Slang:
    """The pyslang modules that the tool needs."""

    pyslang: Any
    syntax: Any
    driver: Any
    options: Any


@dataclass
class Port:
    """One port of a module as written and as elaborated."""

    name: str
    direction: str
    type_text: str
    dims: list[str]
    width: int = 0
    usizes: list[int] = field(default_factory=list)
    udims: list[str] = field(default_factory=list)


@dataclass
class Param:
    """One overridable parameter of a module as written and as elaborated."""

    name: str
    type_text: str
    default_text: str
    value: str = ""
    usizes: list[int] = field(default_factory=list)
    udims: list[str] = field(default_factory=list)


@dataclass
class ModuleFacts:
    """The facts of one module. env holds the integer value of every parameter."""

    name: str
    ports: list[Port] = field(default_factory=list)
    params: list[Param] = field(default_factory=list)
    env: dict[str, int] = field(default_factory=dict)


def tex_escape(text: str) -> str:
    """Escape the LaTeX special characters of a plain text."""
    return "".join(_ESCAPES.get(c, c) for c in text)


def describe(text: str) -> str:
    """Return a description as LaTeX. Text between backticks is set as code."""
    parts = str(text).strip().split("`")
    if len(parts) % 2 == 0:
        raise FactError(f"unbalanced backtick in description: {text!r}")
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            out.append(tex_escape(part))
        elif CODE_SPAN_RE.match(part) and part:
            out.append(f"\\code{{{part}}}")
        else:
            raise FactError(f"unsupported character in code span `{part}`")
    return "".join(out)


def code(text: str) -> str:
    """Return RTL text set as code. Stop on text that cannot be set safely."""
    depth = 0
    for c in text:
        depth += (c == "{") - (c == "}")
        if depth < 0:
            break
    if re.search(r"[%#\\]", text) or depth != 0:
        raise FactError(f"unsupported character in RTL text: {text!r}")
    return f"\\code{{{text}}}"


def load_slang() -> Slang:
    """Import pyslang, or raise ImportError."""
    import pyslang  # noqa: PLC0415 - optional dependency
    from pyslang import syntax  # noqa: PLC0415
    from pyslang.driver import CommandLineOptions, Driver  # noqa: PLC0415

    return Slang(pyslang, syntax, Driver, CommandLineOptions)


def node_text(syntax: Any, node: Any, directives: bool = False) -> str:
    """Return the source text of a syntax node without comments, on one line."""
    printer = syntax.SyntaxPrinter()
    printer.setIncludeComments(False)
    printer.setIncludeDirectives(directives)
    printer.print(node)
    return " ".join(printer.str().split())


def kind_of(node: Any) -> str:
    """Return the syntax kind name without the enum prefix."""
    return str(node.kind).split(".")[-1]


def syntax_pass(sl: Slang, rtl: Path, module: str) -> ModuleFacts:
    """Read the ports and parameters as written in the source text."""
    try:
        tree = sl.syntax.SyntaxTree.fromFile(str(rtl), sl.pyslang.SourceManager())
    except Exception as exc:  # pyslang raises its own exception types
        raise FactError(f"cannot parse {rtl}: {exc}") from exc
    mods = [
        m
        for m in tree.root.members
        if kind_of(m) == "ModuleDeclaration" and m.header.name.valueText == module
    ]
    if not mods:
        raise FactError(f"cannot parse {rtl}: module {module} not found")
    header = mods[0].header
    if re.search(r"`\s*(?:ifn?def|elsif|else|endif|if)\b", node_text(sl.syntax, header, True)):
        raise FactError(f"cannot parse {module}: conditional compilation in the module header")
    facts = ModuleFacts(module)
    if header.parameters is not None:
        for decl in header.parameters.declarations:
            kind = kind_of(decl)
            if kind == "TypeParameterDeclaration":
                raise FactError(f"cannot parse {module}: type parameters are not supported")
            if kind != "ParameterDeclaration":
                continue
            if decl.keyword.valueText == "localparam":
                continue
            type_text = node_text(sl.syntax, decl.type)
            for d in decl.declarators:
                udims = unpacked_dims(sl, module, "parameter", d)
                default = node_text(sl.syntax, d.initializer.expr) if d.initializer else ""
                facts.params.append(Param(d.name.valueText, type_text, default, udims=udims))
    ports = header.ports
    if ports is None:
        return facts
    pkind = kind_of(ports)
    if pkind != "AnsiPortList":
        raise FactError(f"cannot parse {module}: only an ANSI port list is supported ({pkind})")
    previous: tuple[str, str] | None = None
    for port in ports.ports:
        if str(port.kind).startswith("TokenKind"):
            continue
        kind = kind_of(port)
        if kind != "ImplicitAnsiPort":
            raise FactError(f"cannot parse {module}: unsupported port form {kind}")
        head = port.header
        hkind = kind_of(head)
        if hkind not in ("VariablePortHeader", "NetPortHeader"):
            raise FactError(f"cannot parse {module}: unsupported port header {hkind}")
        name = port.declarator.name.valueText
        udims = unpacked_dims(sl, module, "port", port.declarator)
        direction = head.direction.valueText
        type_text = node_text(sl.syntax, head.dataType)
        if not direction:
            if previous is None:
                raise FactError(f"cannot parse {module}: port {name} has no direction")
            direction, type_text = previous
        previous = (direction, type_text)
        dims = re.findall(r"\[([^\[\]]*)\]", type_text)
        facts.ports.append(Port(name, direction, type_text, dims, udims=udims))
    return facts


def unpacked_dims(sl: Slang, module: str, what: str, declarator: Any) -> list[str]:
    """Return the text of each unpacked dimension of a declarator: [N] gives N, [3:0] gives 3:0."""
    out = []
    for dim in declarator.dimensions:
        spec = getattr(dim, "specifier", None)
        text = (
            node_text(sl.syntax, spec) if spec is not None and kind_of(spec) in SIZED_DIMS else ""
        )
        if not text:
            name = declarator.name.valueText
            raise FactError(
                f"cannot parse {module}: unsupported unpacked dimension on {what} {name}"
            )
        out.append(text)
    return out


def parse_int(raw: str) -> int | None:
    """Return the integer value of an elaborated constant, or None."""
    raw = raw.strip()
    m = re.match(r"^(-?)(?:\d+)?'[sS]?([bBdDhHoO])([0-9a-fA-F_]+)$", raw)
    if m:
        base = {"b": 2, "d": 10, "h": 16, "o": 8}[m.group(2).lower()]
        try:
            value = int(m.group(3).replace("_", ""), base)
        except ValueError:
            return None
        return -value if m.group(1) else value
    return int(raw) if re.match(r"^-?\d+$", raw) else None


def format_value(raw: str) -> str:
    """Return an elaborated constant in compact form: 32'd5 gives 5."""
    m = re.match(r"^\d+'d(\d+)$", raw)
    return m.group(1) if m else raw


def elaborate(sl: Slang, module: str, files: list[Path]) -> ModuleFacts:
    """Elaborate the module at its default parameters. Return widths and values."""
    d = sl.driver()
    d.addStandardArgs()
    names = " ".join(f'"{f.as_posix()}"' if " " in str(f) else f.as_posix() for f in files)
    args = f"slang --ignore-unknown-modules --top {module} {names}"
    if not (d.parseCommandLine(args, sl.options()) and d.processOptions() and d.parseAllSources()):
        raise FactError(f"cannot parse {module}: slang could not load {files[0]}")
    comp = d.createCompilation()
    errors = [x for x in comp.getAllDiagnostics() if x.isError()]
    if errors:
        engine = sl.pyslang.DiagnosticEngine(comp.sourceManager)
        client = sl.pyslang.TextDiagnosticClient()
        engine.addClient(client)
        for e in errors[:5]:
            engine.issue(e)
        raise FactError(f"cannot parse {module}: elaboration errors\n{client.getString().strip()}")
    tops = [i for i in comp.getRoot().topInstances if i.name == module]
    if not tops:
        raise FactError(f"cannot parse {module}: module not found by elaboration")
    body = tops[0].body
    facts = ModuleFacts(module)
    for p in body.portList:
        if type(p).__name__ != "PortSymbol":
            raise FactError(f"cannot parse {module}: unsupported port {p.name}")
        direction = str(p.direction).split(".")[-1].lower()
        element, sizes = split_unpacked(module, p.name, p.type)
        facts.ports.append(Port(p.name, direction, "", [], int(element.bitWidth), sizes))
    for p in body.parameters:
        if type(p).__name__ != "ParameterSymbol":
            continue
        raw = str(p.value)
        number = parse_int(raw)
        if number is not None:
            facts.env[p.name] = number
        if not getattr(p, "isLocalParam", False):
            _, sizes = split_unpacked(module, p.name, p.type)
            facts.params.append(Param(p.name, str(p.type), "", format_value(raw), sizes))
    return facts


def split_unpacked(module: str, name: str, typ: Any) -> tuple[Any, list[int]]:
    """Return the element type of a declaration and the size of each unpacked dimension."""
    sizes: list[int] = []
    while typ.isUnpackedArray:
        rng = getattr(typ, "range", None)
        if rng is None:
            raise FactError(f"cannot parse {module}: unsupported unpacked dimension on {name}")
        sizes.append(int(rng.width))
        typ = typ.elementType
    return typ, sizes


def eval_size(expr: str, env: dict[str, int]) -> int | None:
    """Return the value of a constant expression of parameters, or None when it is unknown."""
    text = expr.replace("$clog2", "clog2")
    unknown = False

    def sub(m: re.Match[str]) -> str:
        nonlocal unknown
        name = m.group(0)
        if name == "clog2":
            return name
        if name in env:
            return str(env[name])
        unknown = True
        return "0"

    text = re.sub(r"[A-Za-z_]\w*", sub, text)
    if unknown or not re.fullmatch(r"[\d\s+\-*/%()]*(?:clog2[\d\s+\-*/%()]*)*", text):
        return None
    try:
        value = eval(text.replace("/", "//"), {"__builtins__": {}}, {"clog2": _clog2})  # noqa: S307
    except Exception:  # an expression that is not plain arithmetic
        return None
    return value if isinstance(value, int) else None


def _clog2(n: int) -> int:
    return 0 if n <= 1 else math.ceil(math.log2(n))


def dim_size(dim: str, env: dict[str, int]) -> int | None:
    """Return the number of elements that one packed dimension declares, or None."""
    if ":" in dim:
        hi, lo = (eval_size(x, env) for x in dim.split(":", 1))
        return None if hi is None or lo is None else abs(hi - lo) + 1
    return eval_size(dim, env)


def base_type(port: Port) -> str:
    """Return the type of a port without its packed dimensions."""
    return " ".join(re.sub(r"\[[^\[\]]*\]", " ", port.type_text).split())


def merge(written: ModuleFacts, built: ModuleFacts) -> ModuleFacts:
    """Combine the two passes. Stop when they disagree."""
    module = written.name
    if [p.name for p in written.ports] != [p.name for p in built.ports]:
        raise FactError(f"cannot parse {module}: the port lists of the two passes differ")
    if [p.name for p in written.params] != [p.name for p in built.params]:
        raise FactError(f"cannot parse {module}: the parameter lists of the two passes differ")
    written.env = built.env
    for w, b in zip(written.ports, built.ports, strict=True):
        w.width = b.width
        if w.direction not in DIRECTIONS:
            raise FactError(f"cannot parse {module}: port {w.name}: direction {w.direction!r}")
        w.direction = DIRECTIONS[w.direction]
        w.usizes = b.usizes
        check_unpacked(module, "port", w, built.env)
        if base_type(w) in BUILTIN_TYPES:
            sizes = [dim_size(d, built.env) for d in w.dims]
            if None not in sizes:
                expected = math.prod(s for s in sizes if s is not None)
                if expected != w.width:
                    raise FactError(
                        f"cannot parse {module}: port {w.name}: the declared range gives "
                        f"{expected} bits and elaboration gives {w.width}"
                    )
    for w, b in zip(written.params, built.params, strict=True):
        w.value = b.value
        w.usizes = b.usizes
        check_unpacked(module, "parameter", w, built.env)
        if not w.type_text:
            w.type_text = b.type_text
    return written


def check_unpacked(module: str, what: str, item: Port | Param, env: dict[str, int]) -> None:
    """Stop when the written unpacked dimensions and the elaborated ones disagree."""
    if len(item.udims) != len(item.usizes):
        raise FactError(
            f"cannot parse {module}: {what} {item.name}: {len(item.udims)} unpacked dimension(s) "
            f"as written and {len(item.usizes)} after elaboration"
        )
    for dim, size in zip(item.udims, item.usizes, strict=True):
        expected = dim_size(dim, env)
        if expected is not None and expected != size:
            raise FactError(
                f"cannot parse {module}: {what} {item.name}: the unpacked dimension gives "
                f"{expected} elements and elaboration gives {size}"
            )


def unpacked_cell(item: Port | Param) -> str:
    """Return the unpacked dimensions as written, each followed by its count when it is a name."""
    cells = []
    for dim, size in zip(item.udims, item.usizes, strict=True):
        text = f"[{dim.replace(' ', '')}]"
        cells.append(code(text) if dim.strip().isdigit() else f"{code(text)} ({size})")
    return " ".join(cells)


def width_cell(port: Port) -> str:
    """Return the Width cell: the packed width, then the unpacked dimensions."""
    packed = packed_width_cell(port)
    return f"{packed} {unpacked_cell(port)}" if port.udims else packed


def packed_width_cell(port: Port) -> str:
    """Return the packed width: the declared range in compact form, then the default width."""
    if base_type(port) not in BUILTIN_TYPES:
        return f"{code(port.type_text)} ({port.width})"
    dims = port.dims
    if not dims:
        return "1"
    if len(dims) == 1 and ":" in dims[0]:
        hi, lo = (x.strip() for x in dims[0].split(":", 1))
        m = re.match(r"^(.*?)\s*-\s*1$", hi)
        if lo == "0" and m:
            text = m.group(1).strip()
        elif lo == "0" and hi.isdigit():
            text = str(int(hi) + 1)
        else:
            text = f"[{hi}:{lo}]"
    else:
        text = "".join(f"[{x.strip()}]" for x in dims)
    if text.isdigit():
        return text
    return f"{code(text.replace(' ', ''))} ({port.width})"


def default_cell(param: Param) -> str:
    """Return the Default cell: the text as written, then the resolved value."""
    text = param.default_text
    if param.udims or LITERAL_RE.match(text) or param.value == text:
        return code(text)
    return f"{code(text)} ({code(param.value)})"


def header_line(rtl: str, yaml_path: str) -> str:
    """Return the first line of each generated file."""
    return f"% Generated by tools/docs/gen_fact_tables.py from {rtl} and {yaml_path}. Do not edit."


def render_signals(facts: ModuleFacts, entry: dict[str, Any], rtl: str, yaml_path: str) -> str:
    """Return the text of <module>-signals.tex."""
    rows = []
    for p in facts.ports:
        info = entry["ports"][p.name]
        dom = info["domain"]
        dom_cell = dom if dom in DOMAIN_WORDS else code(dom)
        rows.append(
            [code(p.name), p.direction, width_cell(p), dom_cell, describe(info["description"])]
        )
    table = longtable(
        SIGNAL_COLS,
        f"Signals of \\code{{{facts.name}}}",
        f"tab:{entry['label']}:signals",
        ["Signal", "Dir", "Width", "Clock domain", "Description"],
        rows,
    )
    return header_line(rtl, yaml_path) + "\n" + table + "\n"


def render_params(facts: ModuleFacts, entry: dict[str, Any], rtl: str, yaml_path: str) -> str:
    """Return the text of <module>-params.tex."""
    if not facts.params:
        body = f"\\par The module \\code{{{facts.name}}} has no parameters.\\par"
        return header_line(rtl, yaml_path) + "\n" + body + "\n"
    rows = []
    for p in facts.params:
        info = entry["params"][p.name]
        type_cell = code(p.type_text) + (f" {unpacked_cell(p)}" if p.udims else "")
        rows.append(
            [
                code(p.name),
                type_cell,
                default_cell(p),
                describe(info["legal"]),
                describe(info["description"]),
            ]
        )
    table = longtable(
        PARAM_COLS,
        f"Parameters of \\code{{{facts.name}}}",
        f"tab:{entry['label']}:params",
        ["Parameter", "Type", "Default", "Legal values", "Description"],
        rows,
    )
    return header_line(rtl, yaml_path) + "\n" + table + "\n"


def load_family(path: Path) -> dict[str, Any]:
    """Load and check the shape of a sidecar file. Raise FactError on a problem."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        raise FactError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("modules"), dict):
        raise FactError(f"cannot parse {path}: the top level needs 'family' and 'modules'")
    if data.get("family") != path.stem:
        raise FactError(f"cannot parse {path}: 'family' must be {path.stem!r}")
    for name, entry in data["modules"].items():
        if not isinstance(entry, dict) or not NAME_RE.match(str(name)):
            raise FactError(f"cannot parse {path}: bad module entry {name!r}")
        if not isinstance(entry.get("rtl"), str):
            raise FactError(f"cannot parse {path}: {name} needs 'rtl'")
        deps = entry.setdefault("deps", [])
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            raise FactError(f"cannot parse {path}: {name}: 'deps' must be a list of paths")
        if not isinstance(entry.get("label"), str) or not LABEL_RE.match(entry["label"]):
            raise FactError(f"cannot parse {path}: {name}: 'label' must be a book label")
        for key in ("params", "ports"):
            entry[key] = entry.get(key) or {}
            if not isinstance(entry[key], dict) or not all(
                isinstance(v, dict) for v in entry[key].values()
            ):
                raise FactError(f"cannot parse {path}: {name}: '{key}' must map names to mappings")
    return data


def check_entries(facts: ModuleFacts, entry: dict[str, Any]) -> list[str]:
    """Return the findings of the two-way check between the RTL and the sidecar."""
    module = facts.name
    found = []
    for kind, names, need in (
        ("port", [p.name for p in facts.ports], ("domain", "description")),
        ("parameter", [p.name for p in facts.params], ("legal", "description")),
    ):
        table = entry["ports" if kind == "port" else "params"]
        for n in names:
            info = table.get(n)
            if info is None:
                found.append(f"{module}: missing description for {kind} {n}")
                continue
            for key in need:
                if not str(info.get(key) or "").strip():
                    found.append(f"{module}: missing description for {kind} {n} ({key})")
        for n in table:
            if n not in names:
                found.append(f"{module}: stale entry {kind} {n} is not in the RTL")
    clocks = {n for n, i in entry["ports"].items() if i.get("domain") == "clock"}
    for n, info in entry["ports"].items():
        dom = info.get("domain")
        if dom and dom not in DOMAIN_WORDS and dom not in clocks:
            found.append(f"{module}: port {n}: domain {dom!r} is not a clock port or a keyword")
    return found


def generate(sl: Slang, root: Path, family: Path) -> tuple[dict[Path, str], list[str]]:
    """Return the output files of a family and the findings."""
    data = load_family(family)
    yaml_rel = family.relative_to(root).as_posix()
    outputs: dict[Path, str] = {}
    findings: list[str] = []
    for module, entry in data["modules"].items():
        rtl = root / entry["rtl"]
        files = [rtl] + [root / d for d in entry["deps"]]
        for f in files:
            if not f.is_file():
                raise FactError(f"cannot parse {module}: {f} does not exist")
        facts = merge(syntax_pass(sl, rtl, module), elaborate(sl, module, files))
        bad = check_entries(facts, entry)
        findings += bad
        if bad:
            continue
        stem = module.replace("_", "-")
        out = root / OUT_DIR
        outputs[out / f"{stem}-signals.tex"] = render_signals(facts, entry, entry["rtl"], yaml_rel)
        outputs[out / f"{stem}-params.tex"] = render_params(facts, entry, entry["rtl"], yaml_rel)
    return outputs, findings


def main(argv: list[str] | None = None) -> int:
    """Run the command line tool."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--family", help="one sidecar file, for example cdc")
    ap.add_argument("--check", action="store_true", help="fail if an output is stale")
    ap.add_argument("--root", type=Path, default=REPO)
    args = ap.parse_args(argv)
    root = args.root.resolve()
    facts_dir = root / FACTS_DIR
    if args.family:
        families = [facts_dir / f"{args.family}.yaml"]
    else:
        families = sorted(p for p in facts_dir.glob("*.yaml") if p.stem not in OTHER_SIDECARS)
    if not families or not all(f.is_file() for f in families):
        print(f"gen_fact_tables: no sidecar file in {facts_dir}", file=sys.stderr)
        return 2
    try:
        sl = load_slang()
    except ImportError:
        print(
            "gen_fact_tables: pyslang is not installed: pip install pyslang==11.0.0",
            file=sys.stderr,
        )
        return 3
    outputs: dict[Path, str] = {}
    findings: list[str] = []
    try:
        for fam in families:
            out, bad = generate(sl, root, fam)
            for path in out:
                if path in outputs:
                    raise FactError(f"two sidecar entries write {path.name}")
            outputs.update(out)
            findings += bad
    except FactError as exc:
        print(f"gen_fact_tables: {exc}", file=sys.stderr)
        return 2
    for line in findings:
        print(f"gen_fact_tables: {line}")
    if findings:
        return 1
    out_dir = root / OUT_DIR
    orphans = []
    if not args.family and out_dir.is_dir():
        orphans = [p for p in sorted(out_dir.glob("*.tex")) if p not in outputs]
    if args.check:
        stale = 0
        for path, text in sorted(outputs.items()):
            current = path.read_bytes().replace(b"\r\n", b"\n") if path.exists() else None
            if current != text.encode("utf-8"):
                state = "missing" if current is None else "out of date"
                print(f"gen_fact_tables: {path.relative_to(root).as_posix()} is {state}")
                stale += 1
        for path in orphans:
            print(
                f"gen_fact_tables: {path.relative_to(root).as_posix()} "
                "is not produced by any sidecar"
            )
            stale += 1
        if stale:
            print("gen_fact_tables: run python tools/docs/gen_fact_tables.py")
            return 1
        print(f"gen_fact_tables: {len(outputs)} files are in sync")
        return 0
    for path in orphans:
        path.unlink()
        print(f"gen_fact_tables: deleted {path.relative_to(root).as_posix()} (no sidecar)")
    for path, text in sorted(outputs.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print(f"gen_fact_tables: wrote {len(outputs)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
