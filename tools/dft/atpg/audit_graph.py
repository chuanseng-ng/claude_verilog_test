#!/usr/bin/env python3
"""Graph side of the untestable-fault audit: the cut BLIF as Quaigh graded it, a ternary simulator, fault cones, an
independent SAT miter, and a cell-level view of the Verilog netlist that names the roots of every constant.

Nothing here calls Quaigh.  The BLIF is read by `load_blif` (own parser), constants are found by own three-valued simulation,
the fault is proven untestable or testable by Glucose (python-sat), and every satisfying assignment is re-checked by a plain
bit-parallel simulation of the same graph.  The cell-level view (`CellDesign`) reads `netlist_cellpin.v` and `libcells.v`,
so it shares neither the BLIF nor the pin-buffer wrapper with the cut.

Doc: tm:ch:dft-architecture
"""

import heapq
import random
import re
import sys
from collections import deque
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import netlist_lib  # noqa: E402

X = 2  # unknown in the three-valued simulation
CAP_GATES = 600_000  # a miter bigger than this is reported as too large, never as a verdict


def teval(cubes: Sequence[str], phase: int, ivals: Sequence[int]) -> int:
    """Three-valued value of one BLIF `.names` gate.  `cubes` is the on-set (phase 1) or off-set (phase 0)."""
    anyx = False
    on = 0
    for c in cubes:
        r = 1
        for ch, v in zip(c, ivals):
            if ch == "-":
                continue
            if v == X:
                r = X
            elif v != (1 if ch == "1" else 0):
                r = 0
                break
        if r == 1:
            on = 1
            break
        if r == X:
            anyx = True
    else:
        on = X if anyx else 0
    return on if (phase == 1 or on == X) else 1 - on


class Blif:
    """The combinational view of a cut BLIF: net ids, one driver per net, latch Q as a free input, latch D and POs observed."""

    def __init__(self) -> None:
        self.id: Dict[str, int] = {}
        self.name: List[str] = []
        self.gin: List[Optional[Tuple[int, ...]]] = []
        self.gcub: List[Tuple[str, ...]] = []
        self.gph: List[int] = []
        self.fo: List[Optional[List[int]]] = []
        self.obs = bytearray()
        self.clk = bytearray()
        self.free = bytearray()  # PI, latch Q, undriven
        self.val = bytearray()
        self.rank: List[int] = []
        self.n_latches = 0
        self.free_mode = False
        self.relaxed: set = set()  # nets treated as free inputs in free mode (the nets a cut exclusion ties constant)
        self.relax_group: Dict[int, str] = {}  # relaxed net -> the tied net it stands for; one SAT variable per tied net
        self.val_base = bytearray()
        self.val_free = bytearray()

    def nid(self, name: str) -> int:
        i = self.id.get(name)
        if i is None:
            i = len(self.name)
            self.id[name] = i
            self.name.append(name)
            self.gin.append(None)
            self.gcub.append(())
            self.gph.append(1)
            self.fo.append(None)
        return i

    def parse(self, text: str) -> None:
        pis: List[int] = []
        pos: List[int] = []
        latch_d: List[int] = []
        latch_q: List[int] = []
        clocks: List[int] = []
        cur: Optional[Tuple[int, Tuple[int, ...], List[str], List[str]]] = None
        for ln in text.replace("\\\n", " ").split("\n"):
            if not ln:
                continue
            if ln[0] != ".":
                if cur is not None:
                    cur[3].append(ln)
                continue
            if cur is not None:
                self._finish(cur)
                cur = None
            f = ln.split()
            if f[0] == ".names":
                o = self.nid(f[-1])
                cur = (o, tuple(self.nid(n) for n in f[1:-1]), [], [])
            elif f[0] == ".inputs":
                pis += [self.nid(n) for n in f[1:]]
            elif f[0] == ".outputs":
                pos += [self.nid(n) for n in f[1:]]
            elif f[0] == ".latch":
                latch_d.append(self.nid(f[1]))
                latch_q.append(self.nid(f[2]))
                if len(f) >= 5:
                    clocks.append(self.nid(f[4]))
        if cur is not None:
            self._finish(cur)
        n = len(self.name)
        self.obs = bytearray(n)
        self.clk = bytearray(n)
        self.free = bytearray(n)
        for i in pos + latch_d:
            self.obs[i] = 1
        for i in clocks:
            self.clk[i] = 1
        for i in pis + latch_q:
            self.free[i] = 1
        self.n_latches = len(latch_q)
        for o in range(n):
            if self.gin[o] is None:
                self.free[o] = 1
            else:
                for i in set(self.gin[o]):
                    if self.fo[i] is None:
                        self.fo[i] = [o]
                    else:
                        self.fo[i].append(o)
        self._levelise()

    def _finish(self, cur) -> None:
        o, ins, rows, _ = cur[0], cur[1], cur[2], cur[3]
        rows = cur[3]
        cubes: List[str] = []
        phase = 1
        for r in rows:
            t = r.split()
            if not ins:
                phase = 1
                if t and t[0] == "1":
                    cubes.append("")
                continue
            cubes.append(t[0])
            phase = int(t[1])
        self.gin[o] = ins
        self.gcub[o] = tuple(cubes)
        self.gph[o] = phase

    def _levelise(self) -> None:
        n = len(self.name)
        need = [0] * n
        queue = deque()
        for o in range(n):
            g = self.gin[o]
            if g is not None:
                k = sum(1 for i in set(g) if self.gin[i] is not None)
                need[o] = k
                if k == 0:
                    queue.append(o)
        order: List[int] = []
        while queue:
            o = queue.popleft()
            order.append(o)
            for d in self.fo[o] or ():
                need[d] -= 1
                if need[d] == 0:
                    queue.append(d)
        n_gates = sum(1 for g in self.gin if g is not None)
        if len(order) != n_gates:
            raise SystemExit(f"combinational loop in the cut: {n_gates - len(order)} gates not levelised")
        self.rank = [0] * n
        for r, o in enumerate(order, 1):
            self.rank[o] = r
        self.val = bytearray([X]) * n
        for o in order:
            self.val[o] = teval(self.gcub[o], self.gph[o], [self.val[i] for i in self.gin[o]])  # type: ignore[union-attr]
        self.order = order
        self.val_base = self.val
        self.val_free = self.val

    def set_relaxed(self, nets: Iterable[int], groups: Optional[Dict[int, str]] = None) -> None:
        """Prepare free mode: the given gate-driven nets become unknown, and every constant they carried is recomputed.
        `groups` maps a net to the tied net it stands for; nets of one group share one SAT variable (one source, many loads)."""
        self.relaxed = {n for n in nets if self.gin[n] is not None}
        self.relax_group = {n: g for n, g in (groups or {}).items() if n in self.relaxed}
        v = bytearray([X]) * len(self.name)
        for o in self.order:
            if o not in self.relaxed:
                v[o] = teval(self.gcub[o], self.gph[o], [v[i] for i in self.gin[o]])  # type: ignore[union-attr]
        self.val_free = v

    def mode(self, free: bool) -> None:
        """Switch the analysis between the cut as graded (base) and the cut with the relaxed nets free (free)."""
        self.val = self.val_free if free else self.val_base
        self.free_mode = free

    # ---- per-fault analysis -------------------------------------------------------------------------------------------

    def cone(self, site: int, v: int) -> Dict[int, int]:
        """Nets where the stuck value can differ from the good value, by event-driven three-valued simulation.
        A gate whose faulty and good outputs are the same constant is a block; X against X is kept (it may differ)."""
        fv: Dict[int, int] = {site: v}
        heap: List[int] = []
        seen = set()
        for d in self.fo[site] or ():
            heapq.heappush(heap, self.rank[d])
            seen.add(d)
        rank_net = None
        if heap:
            rank_net = {self.rank[d]: d for d in seen}
        while heap:
            r = heapq.heappop(heap)
            o = rank_net[r]  # type: ignore[index]
            ins = self.gin[o]
            new = teval(self.gcub[o], self.gph[o], [fv.get(i, self.val[i]) for i in ins])  # type: ignore[union-attr]
            good = self.val[o]
            if new == good and new != X:
                continue
            fv[o] = new
            for d in self.fo[o] or ():
                if d not in seen:
                    seen.add(d)
                    rank_net[self.rank[d]] = d
                    heapq.heappush(heap, self.rank[d])
        return fv

    def struct_reach(self, site: int, limit: int = 3_000_000) -> Tuple[int, int, int]:
        """Structural fanout, constants ignored: (gates, observation nets, clock nets) reached.  Stops at `limit` gates."""
        seen = {site}
        q = deque([site])
        n_obs = int(self.obs[site])
        n_clk = int(self.clk[site])
        while q and len(seen) < limit:
            o = q.popleft()
            for d in self.fo[o] or ():
                if d not in seen:
                    seen.add(d)
                    n_obs += self.obs[d]
                    n_clk += self.clk[d]
                    q.append(d)
        return len(seen) - 1, n_obs, n_clk

    def fanin_closure(self, roots: Iterable[int], limit: int = CAP_GATES) -> Optional[List[int]]:
        """Gate-driven nets feeding `roots`, in topological order; None when over `limit`."""
        seen = set()
        stop = self.relaxed if self.free_mode else ()
        stack = [r for r in roots if self.gin[r] is not None and r not in stop]
        for r in stack:
            seen.add(r)
        while stack:
            o = stack.pop()
            for i in self.gin[o]:  # type: ignore[union-attr]
                if self.gin[i] is not None and i not in seen and i not in stop:
                    seen.add(i)
                    stack.append(i)
                    if len(seen) > limit:
                        return None
        return sorted(seen, key=self.rank.__getitem__)

    def eval_words(self, nets: Sequence[int], base: Dict[int, int], width: int, override: Optional[Dict[int, int]] = None) -> Dict[int, int]:
        """Bit-parallel two-valued evaluation.  `base` gives the value word of every free net it reads; `override` pins nets."""
        mask = (1 << width) - 1
        out: Dict[int, int] = dict(base)
        ov = override or {}
        for o in nets:
            if o in ov:
                out[o] = ov[o]
                continue
            iv = [out[i] if i in out else (mask if self.val[i] == 1 else 0) for i in self.gin[o]]  # type: ignore[union-attr]
            acc = 0
            for c in self.gcub[o]:
                t = mask
                for ch, w in zip(c, iv):
                    if ch == "1":
                        t &= w
                    elif ch == "0":
                        t &= ~w & mask
                acc |= t
            out[o] = acc if self.gph[o] == 1 else ~acc & mask
        return out


# ---- SAT -------------------------------------------------------------------------------------------------------------------


class Miter:
    """CNF for one fault: good copy over the fanin closure, faulty copy over the live cone, OR of the observation differences."""

    def __init__(self, b: Blif) -> None:
        self.b = b
        self.nv = 0
        self.clauses: List[List[int]] = []
        self.gvar: Dict[int, int] = {}
        self.fvar: Dict[int, int] = {}
        self.grp: Dict[str, int] = {}

    def new(self) -> int:
        self.nv += 1
        return self.nv

    def good(self, net: int) -> int:
        v = self.gvar.get(net)
        if v is None:
            key = self.b.relax_group.get(net) if self.b.free_mode else None
            if key is not None:
                v = self.grp.get(key)
                if v is None:
                    v = self.grp[key] = self.new()
            else:
                v = self.new()
            self.gvar[net] = v
        return v

    def gate(self, out: int, ins: List[int], cubes: Sequence[str], phase: int) -> None:
        terms: List[int] = []
        always = False
        for c in cubes:
            lits = [i if ch == "1" else -i for ch, i in zip(c, ins) if ch != "-"]
            if not lits:
                always = True
                break
            if len(lits) == 1:
                terms.append(lits[0])
                continue
            t = self.new()
            for lt in lits:
                self.clauses.append([-t, lt])
            self.clauses.append([t] + [-lt for lt in lits])
            terms.append(t)
        o = out if phase == 1 else -out
        if always:
            self.clauses.append([o])
        elif not terms:
            self.clauses.append([-o])
        else:
            for t in terms:
                self.clauses.append([-t, o])
            self.clauses.append([-o] + terms)

    def build_good(self, nets: Sequence[int]) -> None:
        for o in nets:
            self.gate(self.good(o), [self.good(i) for i in self.b.gin[o]], self.b.gcub[o], self.b.gph[o])  # type: ignore[union-attr]
        for i in list(self.gvar):
            if self.b.gin[i] is None and not self.b.free[i]:
                continue
            if self.b.gin[i] is None and self.b.val[i] != X:
                self.clauses.append([self.gvar[i] if self.b.val[i] == 1 else -self.gvar[i]])


def sat_testable(b: Blif, site: int, v: int, fv: Dict[int, int], conf_budget: int = 3_000_000) -> Dict:
    """Is there an input assignment that detects `site` stuck-at `v`?  Returns {"result": "testable"|"untestable"|"unknown",
    "verified": bool, "gates": n}.  `fv` is the ternary cone from Blif.cone (restricts the faulty copy)."""
    from pysat.solvers import Glucose4  # imported late: the pure parts of the audit run without python-sat

    cone = sorted(fv, key=lambda n: b.rank[n])
    members = set(cone)
    useful: Dict[int, bool] = {}
    for n in reversed(cone):
        useful[n] = bool(b.obs[n]) or any(useful.get(d, False) for d in (b.fo[n] or ()) if d in members)
    live = [n for n in cone if useful[n] and n != site]
    if not useful.get(site, False):
        return {"result": "untestable", "verified": True, "gates": 0, "note": "no live path"}
    side = set()
    for n in live:
        for i in b.gin[n]:  # type: ignore[union-attr]
            if i not in members or not useful.get(i, False):
                side.add(i)
    roots = set(side) | {site} | set(live)
    closure = b.fanin_closure(roots)
    if closure is None:
        return {"result": "unknown", "verified": False, "gates": -1, "note": "closure over cap"}
    m = Miter(b)
    m.build_good(closure)
    m.fvar[site] = m.new()
    m.clauses.append([m.fvar[site] if v else -m.fvar[site]])
    for n in live:
        m.fvar[n] = m.new()
        m.gate(m.fvar[n], [m.fvar[i] if i in m.fvar else m.good(i) for i in b.gin[n]], b.gcub[n], b.gph[n])  # type: ignore[union-attr]
    diffs: List[int] = []
    for n in [site] + live:
        if b.obs[n]:
            d = m.new()
            g, f = m.good(n), m.fvar[n]
            m.clauses += [[-d, g, f], [-d, -g, -f], [d, -g, f], [d, g, -f]]
            diffs.append(d)
    m.clauses.append(diffs)
    # constants the simulation proved are pinned in the good copy of the free nets only; every other gate keeps its own CNF
    for i, gv in m.gvar.items():
        if b.gin[i] is None and b.val[i] != X:
            m.clauses.append([gv if b.val[i] == 1 else -gv])
    s = Glucose4(bootstrap_with=m.clauses)
    s.conf_budget(conf_budget)
    r = s.solve_limited()
    out = {"result": "unknown", "verified": False, "gates": len(closure) + len(live)}
    if r is False:
        out["result"] = "untestable"
        out["verified"] = True
    elif r is True:
        model = set(x for x in s.get_model() if x > 0)
        base = {i: (1 if gv in model else 0) for i, gv in m.gvar.items() if b.gin[i] is None or (b.free_mode and i in b.relaxed)}
        goodv = b.eval_words(closure, base, 1)
        fval = b.eval_words([n for n in live], {**goodv, site: v}, 1, override=None)
        fval[site] = v
        hit = any(b.obs[n] and ((goodv.get(n, 1 if b.val[n] == 1 else 0)) != fval.get(n, goodv.get(n, 0))) for n in [site] + live)
        out["result"] = "testable"
        out["verified"] = bool(hit)
    s.delete()
    return out


def sat_excitable(b: Blif, site: int, v: int, conf_budget: int = 1_000_000) -> str:
    """Can the site take the value 1-v at all?  'yes' | 'no' (a logic-derived constant) | 'unknown'."""
    from pysat.solvers import Glucose4

    closure = b.fanin_closure([site])
    if closure is None:
        return "unknown"
    m = Miter(b)
    m.build_good(closure)
    g = m.good(site)
    for i, gv in m.gvar.items():
        if b.gin[i] is None and b.val[i] != X:
            m.clauses.append([gv if b.val[i] == 1 else -gv])
    m.clauses.append([g if v == 0 else -g])
    s = Glucose4(bootstrap_with=m.clauses)
    s.conf_budget(conf_budget)
    r = s.solve_limited()
    s.delete()
    return "unknown" if r is None else ("yes" if r else "no")


def random_detect(b: Blif, site: int, v: int, fv: Dict[int, int], width: int = 1024, seed: int = 7) -> bool:
    """True if `width` random vectors detect the fault (bit-parallel, two-valued).  A consistency check for untestable verdicts."""
    cone = sorted(fv, key=lambda n: b.rank[n])
    members = set(cone)
    live = [n for n in cone if n != site]
    roots = set(live) | {site}
    for n in live:
        roots.update(i for i in b.gin[n] if i not in members)  # type: ignore[union-attr]
    closure = b.fanin_closure(roots)
    if closure is None:
        return False
    rng = random.Random(seed)
    mask = (1 << width) - 1
    base: Dict[int, int] = {}
    need = set(closure) | roots
    for n in closure:
        need.update(b.gin[n])  # type: ignore[arg-type]
    for n in need:
        if b.gin[n] is None:
            base[n] = mask if b.val[n] == 1 else (0 if b.val[n] == 0 else rng.getrandbits(width))
    goodv = b.eval_words(closure, base, width)
    fvals = b.eval_words(live, {**goodv, site: mask if v else 0}, width)
    fvals[site] = mask if v else 0
    for n in [site] + live:
        if b.obs[n]:
            g = goodv.get(n, mask if b.val[n] == 1 else 0)
            if (g ^ fvals[n]) & mask:
                return True
    return False


# ---- cell-level view (Verilog netlist + Liberty models) --------------------------------------------------------------------

ROOT_CONSTS = {"scan_mode_i": 1, "scan_en_i": 0, "trst_ni": 0, "tck_i": 0, "scan_rst_ni": 1}
LIT_RE = re.compile(r"^\d*'[bBhHdD]([01xXzZ])$")
ANON_RE = re.compile(r"^(_\d+_|net\d+|\d+)$")
GATE_RE = re.compile(r"\\\$_(AND|OR|NOT)_\s+\S+\s*\((.*?)\);", re.S)
ASSIGN_RE = re.compile(r"^\s*assign\s+(\S+)\s*=\s*(.+?);", re.M)
MOD_RE = re.compile(r"^module\s+(\S+?)\s*\((.*?)\);(.*?)^endmodule", re.S | re.M)
PIN_RE = re.compile(r"\.(\w+)\(([^()]*)\)")
ASSIGN_TIE_RE = re.compile(r"^\s*assign\s+(\S.*?)\s*=\s*\d+'b([01])\s*;", re.M)


def excl_group(net: str) -> str:
    """Family of an exclusion-tied net: indices and the last name part stripped (`u_dft_ctrl.u_tap.scan_sel_q[0]` -> `u_dft_ctrl.u_tap`)."""
    base = re.sub(r"\[\d+\]", "", net)
    return base.rsplit(".", 1)[0] if "." in base else base


class CellModel:
    """Combinational function of one Liberty cell (from the Yosys-written model); None outputs for sequential cells."""

    def __init__(self, name: str, body: str) -> None:
        self.name = name
        self.inputs = re.findall(r"^\s*input\s+(\w+);", body, re.M)
        self.outputs = re.findall(r"^\s*output\s+(\w+);", body, re.M)
        self.seq = bool(re.search(r"\\\$_(DFF|DLATCH|SDFF)\w*_\s|\\\$tribuf", body))
        self.gates = [(g, dict(PIN_RE.findall(p))) for g, p in GATE_RE.findall(body)]
        self.assigns = [(a, b.strip()) for a, b in ASSIGN_RE.findall(body)]
        self.cache: Dict[Tuple, Tuple] = {}

    def eval(self, vals: Dict[str, int]) -> Dict[str, int]:
        if self.seq:
            return {o: X for o in self.outputs}
        key = tuple(vals.get(i, X) for i in self.inputs)
        hit = self.cache.get(key)
        if hit is not None:
            return dict(zip(self.outputs, hit))
        w = dict(zip(self.inputs, key))
        changed = True
        pending = list(self.gates)
        while changed:
            changed = False
            rest = []
            for g, p in pending:
                if g == "NOT":
                    if p["A"] in w:
                        a = w[p["A"]]
                        w[p["Y"]] = X if a == X else 1 - a
                        changed = True
                    else:
                        rest.append((g, p))
                elif p["A"] in w and p["B"] in w:
                    a, b = w[p["A"]], w[p["B"]]
                    if g == "AND":
                        w[p["Y"]] = 0 if (a == 0 or b == 0) else (1 if a == 1 and b == 1 else X)
                    else:
                        w[p["Y"]] = 1 if (a == 1 or b == 1) else (0 if a == 0 and b == 0 else X)
                    changed = True
                else:
                    rest.append((g, p))
            pending = rest
        for dst, src in self.assigns:
            m = LIT_RE.match(src)
            w[dst] = int(m.group(1)) if m and m.group(1) in "01" else w.get(src, X)
        res = tuple(w.get(o, X) for o in self.outputs)
        self.cache[key] = res
        return dict(zip(self.outputs, res))


class CellDesign:
    """Cell instances, drivers and loads of the Verilog netlist, three-valued constants with named roots."""

    def __init__(self, netlist: Path, libcells: Path) -> None:
        self.models: Dict[str, CellModel] = {}
        for name, _, body in MOD_RE.findall(Path(libcells).read_text()):
            self.models[name] = CellModel(name, body)
        text = Path(netlist).read_text(errors="replace")
        self.cells = {c.inst: c for c in netlist_lib.iter_cells(text)}
        # `assign net = 1'bV;` lines are the exclusions of the cut: an unscanned flop removed, its Q tied to the reset value
        self.assign_tie: Dict[str, int] = {netlist_lib.norm(n): int(v) for n, v in ASSIGN_TIE_RE.findall(text)}
        self.driver: Dict[str, Tuple[str, str]] = {}
        self.loads: Dict[str, List[Tuple[str, str]]] = {}
        for inst, c in self.cells.items():
            m = self.models.get(c.typ.replace("__core", ""))
            outs = set(m.outputs) if m else set()
            for pin, net in c.pins.items():
                if pin in outs:
                    self.driver[net] = (inst, pin)
                else:
                    self.loads.setdefault(net, []).append((inst, pin))

    def simulate(self, roots: Dict[str, int], assigns: bool = True, drop: Sequence[str] = ()) -> Dict[str, int]:
        """Net -> 0/1 for nets forced constant by `roots` (top-level nets held), the tie cells and literal pins, and (with
        `assigns`) the exclusion ties except the groups in `drop`; nets not in the dict are unknown."""
        val: Dict[str, int] = dict(roots)
        if assigns:
            val.update({n: v for n, v in self.assign_tie.items() if excl_group(n) not in drop})
        queue: deque = deque()
        # every combinational cell is evaluated once: a tie cell, or a cell with a literal 1'b0 / 1'b1 on a pin, has no
        # constant net feeding it that would otherwise put it on the queue
        for inst, c in self.cells.items():
            m = self.models.get(c.typ.replace("__core", ""))
            if m is not None and not m.seq and m.outputs:
                queue.append(inst)
        done = set()
        while queue:
            inst = queue.popleft()
            c = self.cells[inst]
            m = self.models.get(c.typ.replace("__core", ""))
            if m is None or m.seq:
                continue
            iv = {}
            for p in m.inputs:
                net = c.pins.get(p)
                if net is None:
                    continue
                lit = LIT_RE.match(net)
                iv[p] = int(lit.group(1)) if lit and lit.group(1) in "01" else val.get(net, X)
            res = m.eval(iv)
            for p, r in res.items():
                net = c.pins.get(p)
                if net is not None and r != X and val.get(net) != r:
                    val[net] = r
                    for ld in self.loads.get(net, ()):
                        queue.append(ld[0])
            done.add(inst)
        return val

    def const_roots(self, nets: Sequence[str]) -> Dict[str, Dict]:
        """For each net: its constant and what holds it.  kind: `tie` (tie cell or literal pin only), `root-logic` (needs the cut's
        held top-level inputs), `excl-tie` (needs an exclusion tie), `none` (not constant at cell level)."""
        groups = sorted({excl_group(n) for n in self.assign_tie})
        if not hasattr(self, "_rel_root"):
            self._ties = self.simulate({}, assigns=False)
            self._roots_only = self.simulate(ROOT_CONSTS, assigns=False)
            self._full = self.simulate(ROOT_CONSTS)
            self._rel_root = {r: self.simulate({k: v for k, v in ROOT_CONSTS.items() if k != r}, assigns=False) for r in ROOT_CONSTS}
            self._rel_grp = {g: self.simulate(ROOT_CONSTS, drop=(g,)) for g in groups}
        ties, roots_only, full = self._ties, self._roots_only, self._full
        out = {}
        for n in nets:
            lit = LIT_RE.match(n)
            if lit and lit.group(1) in "01":
                out[n] = {"value": int(lit.group(1)), "kind": "literal", "roots": []}
            elif n in ties:
                out[n] = {"value": ties[n], "kind": "tie", "roots": []}
            elif n in roots_only:
                deps = [r for r in ROOT_CONSTS if n not in self._rel_root[r]]
                out[n] = {"value": roots_only[n], "kind": "root-logic", "roots": deps or ["(two or more roots jointly)"]}
            elif n in full:
                deps = [g for g in groups if n not in self._rel_grp[g]]
                out[n] = {"value": full[n], "kind": "excl-tie", "roots": deps or ["(two or more exclusion groups jointly)"]}
            else:
                out[n] = {"value": None, "kind": "none", "roots": []}
        return out

    def named_near(self, net: str, depth: int = 4) -> Optional[str]:
        """Closest net with a source-level name (not `_123_` / `net123`) by walking drivers and loads up to `depth` cells."""
        seen = {net}
        q = deque([(net, 0)])
        while q:
            n, d = q.popleft()
            if n not in ("1'b0", "1'b1") and not ANON_RE.match(n) and not n.startswith("u_dut."):
                return n
            if d >= depth:
                continue
            nxt: List[str] = []
            drv = self.driver.get(n)
            if drv:
                c = self.cells[drv[0]]
                nxt += [x for p, x in c.pins.items() if p != drv[1]]
            for inst, pin in self.loads.get(n, ()):
                c = self.cells[inst]
                m = self.models.get(c.typ.replace("__core", ""))
                nxt += [x for p, x in c.pins.items() if m and p in m.outputs]
            for x in nxt:
                if x not in seen:
                    seen.add(x)
                    q.append((x, d + 1))
        return None
