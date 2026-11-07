#!/usr/bin/env python3
"""cap2d.py -- small 2-D (cross-section) capacitance solver used to pre-fit the Sky130 ITF without an hour-long
grdgenxo run per candidate.  numpy only (no scipy on this host).

Model: finite-volume Laplace on a tensor grid, cell-centred potentials, conductors are Dirichlet cells, the
substrate (z = 0) is the ground plane, the other three boundaries are Neumann.  Dielectrics are planar slabs
(the ITF convention: a conductor is embedded at the bottom of the slab listed above it in the ITF; the slab's ER
fills the conductor level AND the gap above the conductor), optional conformal liner around a conductor.

It is a SURROGATE: it is validated against StarRC on the same patterns (tune/validate), then used for the knob
fit.  Final numbers always come from grdgenxo + StarXtract.

Units: um, aF/um (capacitance per unit length).  eps0 = 8.8541878 aF/um.
"""
import math, re, sys
import numpy as np

EPS0 = 8.8541878128  # aF/um


# ---------------------------------------------------------------- ITF parsing (slabs and conductors)
def parse_itf(path):
    """returns (slabs, conds, z) where slabs = [(z0, z1, er)] bottom-up, conds = {name: (zbot, thick, wmin, smin)}"""
    txt = open(path).read()
    blocks = re.findall(r"(DIELECTRIC|CONDUCTOR)\s+(\w+)\s*\{([^}]*)\}", txt)
    order = []   # file order, top -> bottom
    for kind, name, body in blocks:
        kv = dict((k, float(v)) for k, v in re.findall(r"(\w+)\s*=\s*([-\d.eE+]+)", body))
        order.append((kind, name, kv))
    z = 0.0
    slabs, conds = [], {}
    zbot = {}
    for kind, name, kv in reversed(order):      # bottom -> top: dielectric z ranges
        if kind == "DIELECTRIC":
            slabs.append([z, z + kv["THICKNESS"], kv["ER"], name]); zbot[name] = z
            z += kv["THICKNESS"]
    prev = None
    for kind, name, kv in order:                # file order: a conductor is embedded in the dielectric listed just above it
        if kind == "DIELECTRIC":
            prev = name
        else:
            conds[name] = (zbot[prev], kv["THICKNESS"], kv.get("WMIN"), kv.get("SMIN"))
    return slabs, conds


class Stack:
    """slabs: list of [z0, z1, er]; conds: name -> (zbot, thick); liner: optional dict(name->(thick_side, thick_top, er))"""

    def __init__(self, slabs, conds, air_er=1.0, headroom=4.0):
        self.slabs = [list(s[:3]) for s in slabs]
        self.conds = conds
        self.ztop = self.slabs[-1][1] + headroom
        self.air_er = air_er

    def er_at(self, z):
        for z0, z1, er in self.slabs:
            if z0 <= z < z1:
                return er
        return self.air_er


def lines_between(pts, hmin, hmax, grow=0.35):
    """tensor-grid lines through every mandatory coordinate, graded cell size h(x)=hmin+grow*dist."""
    pts = sorted(set(round(p, 6) for p in pts))
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        # inverse-CDF placement of nodes by integral dx/h(x), h = clip(hmin + grow*min(x-a, b-x), hmax)
        xs = np.linspace(a, b, 2001)
        h = np.minimum(hmin + grow * np.minimum(xs - a, b - xs), hmax)
        cdf = np.concatenate([[0], np.cumsum(0.5 * (1 / h[1:] + 1 / h[:-1]) * np.diff(xs))])
        n = max(1, int(round(cdf[-1])))
        t = np.linspace(0, cdf[-1], n + 1)
        out.extend(np.interp(t[1:], cdf, xs))
    return np.array(out)


def solve(stack, rects, excite, hmin=0.02, hmax=0.6, xmargin=2.5, tol=1e-7, maxit=20000, liner=None, verbose=False):
    """rects: list of (name, x0, x1, z0, z1) conductors; excite: name driven at 1 V (all others + substrate 0).
    liner: optional (er, t_side, t_top) conformal dielectric hugging every conductor (ER of the liner).
    returns dict name -> charge (aF/um) (positive on the driven one)"""
    xs_m = [r[1] for r in rects] + [r[2] for r in rects]
    xmin, xmax = min(xs_m) - xmargin, max(xs_m) + xmargin
    xm = list(xs_m) + [xmin, xmax]
    zm = [0.0, stack.ztop] + [s[0] for s in stack.slabs] + [s[1] for s in stack.slabs]
    zm += [r[3] for r in rects] + [r[4] for r in rects]
    if liner:
        er_l, ts, tt = liner
        xm += [r[1] - ts for r in rects] + [r[2] + ts for r in rects]
        zm += [r[3] - ts for r in rects] + [r[4] + tt for r in rects]
    X = lines_between(xm, hmin, hmax)
    Z = lines_between(zm, hmin, hmax)
    nx, nz = len(X) - 1, len(Z) - 1
    xc = 0.5 * (X[1:] + X[:-1]); zc = 0.5 * (Z[1:] + Z[:-1])
    dx = np.diff(X); dz = np.diff(Z)
    er = np.empty((nx, nz))
    for j in range(nz):
        er[:, j] = stack.er_at(zc[j])
    cid = -np.ones((nx, nz), dtype=int)
    names = [r[0] for r in rects]
    if liner:
        for (nm, x0, x1, z0, z1) in rects:
            mx = (xc > x0 - ts) & (xc < x1 + ts); mz = (zc > z0 - ts) & (zc < z1 + tt)
            er[np.ix_(mx, mz)] = er_l
    for k, (nm, x0, x1, z0, z1) in enumerate(rects):
        mx = (xc > x0) & (xc < x1); mz = (zc > z0) & (zc < z1)
        cid[np.ix_(mx, mz)] = k
    cond = cid >= 0
    # half-resistance per cell for each direction; conductor cells contribute 0 (potential at face)
    rx = np.where(cond, 0.0, 0.5 * dx[:, None] / er)      # per unit area
    rz = np.where(cond, 0.0, 0.5 * dz[None, :] / er)
    # x faces between i and i+1: area = dz_j, conductance = dz_j / (rx[i]+rx[i+1]) ... (rx already carries 0.5 dx)
    with np.errstate(divide="ignore"):
        gx = dz[None, :] / (rx[:-1, :] + rx[1:, :])                   # (nx-1, nz)
        gz = dx[:, None] / (rz[:, :-1] + rz[:, 1:])                   # (nx, nz-1)
        gb = dx / rz[:, 0]                                            # substrate face (dirichlet 0), per column
    gx[~np.isfinite(gx)] = 0.0; gz[~np.isfinite(gz)] = 0.0; gb[~np.isfinite(gb)] = 0.0
    # conductor-conductor faces carry no information
    gx[cond[:-1, :] & cond[1:, :]] = 0.0; gz[cond[:, :-1] & cond[:, 1:]] = 0.0
    gb[cond[:, 0]] = 0.0
    V = np.zeros((nx, nz))
    k0 = names.index(excite)
    V[cid == k0] = 1.0
    free = ~cond
    diag = np.zeros((nx, nz))
    diag[:-1, :] += gx; diag[1:, :] += gx; diag[:, :-1] += gz; diag[:, 1:] += gz; diag[:, 0] += gb
    def apply(p):               # (A p) on free cells, p zero on conductor cells
        y = diag * p
        y[:-1, :] -= gx * p[1:, :]; y[1:, :] -= gx * p[:-1, :]
        y[:, :-1] -= gz * p[:, 1:]; y[:, 1:] -= gz * p[:, :-1]
        return y * free
    # rhs: neighbours that are driven conductors
    b = np.zeros((nx, nz))
    b[:-1, :] += gx * V[1:, :]; b[1:, :] += gx * V[:-1, :]
    b[:, :-1] += gz * V[:, 1:]; b[:, 1:] += gz * V[:, :-1]
    b *= free
    dinv = np.where(free & (diag > 0), 1.0 / np.where(diag > 0, diag, 1.0), 0.0)
    x = np.zeros((nx, nz))
    r = b.copy()
    zv = dinv * r; p = zv.copy(); rz0 = float((r * zv).sum()); bn = math.sqrt(float((b * b).sum())) or 1.0
    it = 0
    while it < maxit:
        Ap = apply(p)
        al = rz0 / float((p * Ap).sum())
        x += al * p; r -= al * Ap
        it += 1
        if math.sqrt(float((r * r).sum())) < tol * bn:
            break
        zv = dinv * r; rz1 = float((r * zv).sum())
        p = zv + (rz1 / rz0) * p; rz0 = rz1
    if verbose:
        print("  grid %dx%d  it=%d" % (nx, nz, it), file=sys.stderr)
    # charge on each conductor: sum over faces to free cells of g*(V_c - phi_nb)
    Q = np.zeros(len(names))
    full = x + V      # driven cells carry V, free cells x
    def acc(mask_c, mask_n, g, phi_c, phi_n, cidc):
        pass
    # x-direction faces
    for (cA, cB, g, sl_a, sl_b) in (("x", None, gx, (slice(0, -1), slice(None)), (slice(1, None), slice(None))),
                                    ("z", None, gz, (slice(None), slice(0, -1)), (slice(None), slice(1, None)))):
        a_c = cid[sl_a]; b_c = cid[sl_b]; pa = full[sl_a]; pb = full[sl_b]
        m1 = (a_c >= 0) & (b_c < 0)          # a is conductor, b is dielectric
        np.add.at(Q, a_c[m1], (g * (pa - pb))[m1])
        m2 = (b_c >= 0) & (a_c < 0)
        np.add.at(Q, b_c[m2], (g * (pb - pa))[m2])
    # substrate is held at 0: charge on conductors from the bottom boundary face only exists for conductor cells touching z=0
    Q *= EPS0
    return dict(zip(names, Q)), it
