"""
func_cov.py -- functional-coverage (covergroup) plumbing for the cocotb suites.
tools/verif/coverage_report.py measures Verilator *code* coverage only. This module is glue over
``cocotb-coverage``: it builds coverpoints and crosses idempotently and writes one YAML file per
simulator process. tools/verif/functional_coverage_report.py merges and gates those files.
Evaluation and how a peripheral adds a model: ``Doc: tm:flow:functional-coverage``.
Design rules:
* Never a hard dependency of the simulation. If ``cocotb_coverage`` cannot be imported, every
  sampler is a no-op and ``export`` does nothing. The CI gate then fails (it needs the model's
  data), so a missing package cannot turn the gate green.
* Sampling is pure Python on values the test already has. No simulator handle is read, so a sample
  cannot race the DUT.
* One export per process, at exit. cocotb runs every test of a MODULE in one simulator process and
  ``coverage_db`` is a process-wide singleton, so the database is cumulative. :func:`enable_export`
  registers ``export`` with ``atexit``. ``export`` is idempotent.
* Export is opt-in through FUNC_COV_DIR (a directory). Unset: sample in memory, write nothing.
Sampler API: ``point(name, bins, labels=None, rel=None)`` matches bins with ``rel(value, bin)``
(default ==), and the FIRST match wins. ``ranges(name, spec)`` takes inclusive ``[(label,
lo, hi)]``.
``pair(cross_name, a, b, ignore=())`` samples two coverpoints and their cross; ``a`` and ``b`` are
``(name, bins, labels)``. ``ignore`` lists cross bins impossible by construction. A legal but
unreachable combination goes in the waiver file, with a reason.
Doc: tm:suite:soc-func-cov
"""

from __future__ import annotations

import atexit
import os
import sys

try:  # the package is optional at simulation time, mandatory in CI (see module docstring)
    from cocotb_coverage import coverage as _cc
except ImportError:  # pragma: no cover - exercised only on hosts without the package
    _cc = None

AVAILABLE = _cc is not None

_exports: list = []
_registered = False


def _noop(*_args) -> None:
    """Sampler used when cocotb-coverage is not installed."""


def _in_range(value, bound) -> bool:
    return bound[0] <= value <= bound[1]


def point(name: str, bins, labels=None, rel=None):
    """Create (idempotently) the coverpoint `name` and return its ``sample(value)`` function."""
    if _cc is None:
        return _noop
    cover = _cc.CoverPoint(
        name,
        xf=lambda value: value,
        bins=list(bins),
        bins_labels=list(labels) if labels is not None else None,
        rel=rel,
    )

    @cover
    def sample(value):
        """Record one value against the bins of the coverpoint."""

    return sample


def ranges(name: str, spec):
    """Coverpoint over inclusive integer ranges, ``spec = [(label, lo, hi), ...]``."""
    return point(
        name,
        [(lo, hi) for _label, lo, hi in spec],
        [label for label, _lo, _hi in spec],
        rel=_in_range,
    )


def pair(cross_name: str, a, b, ignore=()):
    """Two coverpoints and their cross; returns ``sample(a_value, b_value)``."""
    if _cc is None:
        return _noop
    (a_name, a_bins, a_labels), (b_name, b_bins, b_labels) = a, b
    point_a = _cc.CoverPoint(
        a_name,
        xf=lambda x, y: x,
        bins=list(a_bins),
        bins_labels=list(a_labels) if a_labels is not None else None,
    )
    point_b = _cc.CoverPoint(
        b_name,
        xf=lambda x, y: y,
        bins=list(b_bins),
        bins_labels=list(b_labels) if b_labels is not None else None,
    )
    cross = _cc.CoverCross(cross_name, items=[a_name, b_name], ign_bins=list(ignore))

    @point_a
    @point_b
    @cross
    def sample(a_value, b_value):
        """Record one (a, b) pair against both coverpoints and their cross."""

    return sample


def export(tag: str):
    """Write the process-wide coverage database to ``$FUNC_COV_DIR/<tag>__<pid>.yml``.

    Returns the path, or None when export is disabled (no ``FUNC_COV_DIR``) or the package is
    missing.  Safe to call repeatedly: the file is rewritten with the cumulative database.
    """
    directory = os.environ.get("FUNC_COV_DIR", "")
    if not directory or _cc is None:
        return None
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{tag}__{os.getpid()}.yml")
    _cc.coverage_db.export_to_yaml(path)
    return path


def enable_export(tag: str) -> None:
    """Arrange for ``export(tag)`` to run when this simulator process exits (idempotent)."""
    global _registered
    if tag not in _exports:
        _exports.append(tag)
    if not _registered:
        atexit.register(_export_all)
        _registered = True


def _export_all() -> None:
    for tag in _exports:
        try:
            export(tag)
        except OSError as exc:  # never let a full disk turn a passing suite red at exit
            print(f"func_cov: could not export coverage for {tag}: {exc}", file=sys.stderr)


def report(logger=print, bins: bool = False) -> None:
    """Log the in-memory coverage trie (a local debugging aid)."""
    if _cc is not None:
        _cc.coverage_db.report_coverage(logger, bins=bins)


def summary() -> dict:
    """``{item name: (covered, size)}`` for every item in the in-memory database."""
    if _cc is None:
        return {}
    return {n: (item.coverage, item.size) for n, item in _cc.coverage_db.items()}
