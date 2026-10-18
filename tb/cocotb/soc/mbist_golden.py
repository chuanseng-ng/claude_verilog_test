"""
mbist_golden.py -- independent Python golden model of the MBIST algorithms and of the fault semantics of
tb/cocotb/soc/sram_fi_core.sv (bead claude_verilog_test-j41m.14, DFT_ARCHITECTURE.md section 16.2).

The algorithm element lists below are written from the algorithm DEFINITIONS in section 16.2 (March C-,
retention, checkerboard + March C-, byte lane), NOT read from the RTL microcode ROM. A suite that compared
the RTL with a copy of its own ROM would prove nothing; here the RTL has to reproduce the first failure
(address, element, slot, background, port, XOR mask) that this model computes on the same faulty memory.

Element numbering is the microcode address documented in section 16.2 (CM 0-5, RETENTION 6-8, CKBD 9-18,
LANE 19-21), because the status block reports `rec_elem` as that address.
"""

from dataclasses import dataclass

FFFF = 0xFFFF_FFFF
BG = (0x0000_0000, 0x5555_5555, 0x3333_3333, 0x0F0F_0F0F, 0x00FF_00FF, 0x0000_FFFF)


@dataclass(frozen=True)
class Elem:
    down: bool
    ops: tuple  # (("r"|"w", pol), ...)
    ck: bool = False
    pause: bool = False
    lane: bool = False
    rev: bool = False


def _e(d, ops, **kw):
    return Elem(d == "dn", tuple(ops), **kw)


R0, R1, W0, W1 = ("r", 0), ("r", 1), ("w", 0), ("w", 1)

# index == microcode address
ELEMS = (
    # MARCH_CM = March C-: up(w0) up(r0,w1) up(r1,w0) down(r0,w1) down(r1,w0) down(r0)
    _e("up", [W0]), _e("up", [R0, W1]), _e("up", [R1, W0]),
    _e("dn", [R0, W1]), _e("dn", [R1, W0]), _e("dn", [R0]),
    # RETENTION: up(w0); pause up(r0,w1); pause up(r1)
    _e("up", [W0]), _e("up", [R0, W1], pause=True), _e("up", [R1], pause=True),
    # CKBD: up(wc) up(rc) up(w~c) up(r~c) then March C- on the checkerboard
    _e("up", [W0], ck=True), _e("up", [R0], ck=True), _e("up", [W1], ck=True), _e("up", [R1], ck=True),
    _e("up", [W0], ck=True), _e("up", [R0, W1], ck=True), _e("up", [R1, W0], ck=True),
    _e("dn", [R0, W1], ck=True), _e("dn", [R1, W0], ck=True), _e("dn", [R0], ck=True),
    # LANE: up(w0); up(lanes 0..3, write ~P); up(lanes 3..0, write P)
    _e("up", [W0]), Elem(False, (), lane=True), Elem(False, (), lane=True, rev=True),
)  # fmt: skip

ALG_RANGE = {0: (0, 5), 1: (6, 8), 2: (0, 8), 3: (9, 18), 4: (19, 21), 5: (0, 21)}
ALG_NAME = {0: "MARCH_CM", 1: "RETENTION", 2: "MARCH_CM_RET", 3: "CKBD", 4: "LANE", 5: "FULL"}


def expand4(m):
    r = 0
    for i in range(4):
        if (m >> i) & 1:
            r |= 0xFF << (8 * i)
    return r


@dataclass
class Fault:
    """Same encoding as sram_fi_core.sv (fi_kind ...)."""

    kind: int = 0
    a_addr: int = 0
    a_bit: int = 0
    v_addr: int = 0
    v_bit: int = 0
    val: int = 0
    dir: int = 0
    ret_t: int = 0

    def label(self):
        names = {0: "none", 1: "SAF", 2: "TF", 3: "CFin", 4: "CFid", 5: "CFst", 6: "AFnone", 7: "AFalias",
                 8: "AFmulti", 9: "RET", 10: "WMASK"}  # fmt: skip
        return (f"{names[self.kind]}(a={self.a_addr}.{self.a_bit} v={self.v_addr}.{self.v_bit} "
                f"val={self.val} dir={self.dir})")  # fmt: skip


class PyMem:
    """Word-level mirror of sram_fi_core.sv (retention, kind 9, needs time and is not modelled here)."""

    def __init__(self, aw, fault=None):
        self.n = 1 << aw
        self.m = [0] * self.n
        self.f = fault or Fault()
        assert self.f.kind != 9, "retention is checked by its own test, not by the golden model"

    def rd(self, w):
        f = self.f
        if f.kind == 6 and w == f.v_addr:
            return 0
        v = self.m[f.a_addr if (f.kind == 7 and w == f.v_addr) else w]
        if f.kind == 8 and w == f.v_addr:
            v &= self.m[f.a_addr]
        if f.kind == 1 and w == f.v_addr:
            v = (v & ~(1 << f.v_bit)) | ((f.val & 1) << f.v_bit)
        if f.kind == 5 and w == f.v_addr and ((self.m[f.a_addr] >> f.a_bit) & 1) == (f.dir & 1):
            v = (v & ~(1 << f.v_bit)) | ((f.val & 1) << f.v_bit)
        return v

    def _wr(self, w, data, mask):
        f = self.f
        if f.kind == 10:
            mask = (mask & ~(1 << (f.v_bit & 3))) | ((f.val & 1) << (f.v_bit & 3))
        old = self.m[w]
        em = expand4(mask)
        new = (old & ~em) | (data & em)
        ob, nb = (old >> f.v_bit) & 1, (new >> f.v_bit) & 1
        if f.kind == 2 and w == f.v_addr:
            if f.dir == 1 and not ob and nb:
                new &= ~(1 << f.v_bit)
            if f.dir == 0 and ob and not nb:
                new |= 1 << f.v_bit
        if f.kind == 1 and w == f.v_addr:
            new = (new & ~(1 << f.v_bit)) | ((f.val & 1) << f.v_bit)
        self.m[w] = new
        if f.kind in (3, 4) and w == f.a_addr:
            oab, nab = (old >> f.a_bit) & 1, (new >> f.a_bit) & 1
            if oab != nab and nab == (f.dir & 1):
                if f.kind == 3:
                    self.m[f.v_addr] ^= 1 << f.v_bit
                else:
                    self.m[f.v_addr] = (self.m[f.v_addr] & ~(1 << f.v_bit)) | ((f.val & 1) << f.v_bit)

    def wr(self, w, data, mask=0xF):
        f = self.f
        if f.kind == 6 and w == f.v_addr:
            return
        if f.kind == 7 and w == f.v_addr:
            self._wr(f.a_addr, data, mask)
            return
        self._wr(w, data, mask)
        if f.kind == 8 and w == f.v_addr:
            self._wr(f.a_addr, data, mask)


def golden_first_fail(alg, aw, has_p1, fault, bg_sweep=False, bg_sel=0):
    """Run `alg` on a PyMem with `fault`; return None (pass) or the first-failure record dict."""
    lo, hi = ALG_RANGE[alg]
    mem = PyMem(aw, fault)
    n = 1 << aw
    bgs = range(6) if bg_sweep else (bg_sel,)
    for bg in bgs:
        p = BG[bg]
        for ei in range(lo, hi + 1):
            e = ELEMS[ei]
            order = range(n - 1, -1, -1) if e.down else range(n)
            for a in order:
                if e.lane:
                    for s in range(8):
                        k = (3 - (s >> 1)) if e.rev else (s >> 1)
                        if s % 2 == 0:
                            mem.wr(a, p if e.rev else p ^ FFFF, 1 << k)
                        else:
                            exp = p ^ expand4(((1 << k) - 1) if e.rev else ((2 << k) - 1))
                            got = mem.rd(a)
                            if got != exp:
                                return _rec(a, ei, s, bg, has_p1, got ^ exp)
                    continue
                for si, (kind, pol) in enumerate(e.ops):
                    pe = pol ^ ((a & 1) if e.ck else 0)
                    data = p ^ (FFFF if pe else 0)
                    if kind == "w":
                        mem.wr(a, data, 0xF)
                    else:
                        got = mem.rd(a)
                        if got != data:
                            return _rec(a, ei, si, bg, has_p1, got ^ data)
    return None


def _rec(a, ei, si, bg, has_p1, mask):
    return {"addr": a, "elem": ei, "slot": si, "bg": bg, "port": 0b11 if has_p1 else 0b01, "mask": mask}


# ---------------------------------------------------------------------------
# Status block decode (section 16.5)
# ---------------------------------------------------------------------------
def decode_status(st):
    return {
        "done": st & 1,
        "busy": (st >> 1) & 1,
        "cfg_err": (st >> 2) & 1,
        "fail_any": (st >> 3) & 1,
        "fail": (st >> 4) & 0x3FF,
        "addr": (st >> 14) & 0x3FF,
        "elem": (st >> 24) & 0x1F,
        "slot": (st >> 29) & 0x7,
        "bg": (st >> 32) & 0x7,
        "port": (st >> 35) & 0x3,
        "mask": (st >> 37) & FFFF,
    }


def cfg_word(alg=2, bg_sweep=0, bg_sel=0, pause_mant=0, pause_exp=0, mask_sel=0, rd_sel=0):
    return (alg | (bg_sweep << 3) | (bg_sel << 4) | (pause_mant << 7) | (pause_exp << 15)
            | (mask_sel << 18) | (rd_sel << 22))  # fmt: skip


def ctl_word(run=1, dom_core=1, dom_cpu=0, **kw):
    """The 29-bit MBIST_CTRL word (section 16.5): run | cfg << 1 | dom_core << 27 | dom_cpu << 28."""
    return run | (cfg_word(**kw) << 1) | (dom_core << 27) | (dom_cpu << 28)


# ---------------------------------------------------------------------------
# Fault catalogue for a memory of 2**aw words
# ---------------------------------------------------------------------------
def catalogue(aw):
    n = 1 << aw
    cells = [(0, 0), (5, 7), (n - 1, 31), (17 % n, 16), (n // 2, 3), (n // 2 + 1, 8), (1, 0)]
    pairs = [  # (aggressor addr, bit, victim addr, bit); the last is intra-word
        (4, 3, 5, 3), (5, 3, 4, 3), (0, 0, n - 1, 31), (n - 1, 31, 0, 0), (20 % n, 31, 21 % n, 0), (9, 2, 9, 5),
    ]  # fmt: skip
    out = []
    for a, b in cells:
        for v in (0, 1):
            out.append(("SAF", Fault(1, v_addr=a, v_bit=b, val=v)))
        for d in (0, 1):
            out.append(("TF", Fault(2, v_addr=a, v_bit=b, dir=d)))
    for aa, ab, va, vb in pairs:
        inter = aa != va
        for d in (0, 1):
            out.append(("CFin" if inter else "CFin_intra", Fault(3, aa, ab, va, vb, 0, d)))
            for v in (0, 1):
                out.append(("CFid" if inter else "CFid_intra", Fault(4, aa, ab, va, vb, v, d)))
                out.append(("CFst" if inter else "CFst_intra", Fault(5, aa, ab, va, vb, v, d)))
    for v, a in ((0, n - 1), (7, 3), (3, 40 % n)):
        out.append(("AFnone", Fault(6, v_addr=v)))
        out.append(("AFalias", Fault(7, a_addr=a, v_addr=v)))
        out.append(("AFmulti", Fault(8, a_addr=a, v_addr=v)))
    for lane in range(4):
        for v in (0, 1):
            out.append(("WMASK", Fault(10, v_bit=lane, val=v)))
    return out
