"""Simulator-neutral descent through generate scopes for cocotb handles.

Verilator exposes ``u_dut.g_aes.u_aes`` as nested scopes.  VCS flattens the generate block into
the child's *name* (``u_dut`` has a child literally called ``"g_aes.u_aes"``), so the nested
attribute access raises ``AttributeError``.  ``hsub`` tries the nested form first (unchanged
behaviour under Verilator) and falls back to the flattened one.
"""

from __future__ import annotations


def hsub(handle, *names: str):
    """``hsub(h, "g_aes", "u_aes")`` == ``h.g_aes.u_aes`` on Verilator, ``h["g_aes.u_aes"]`` on VCS."""
    try:
        cur = handle
        for n in names:
            cur = getattr(cur, n)
        return cur
    except AttributeError:
        return handle._id(".".join(names), extended=False)


def _is_struct(handle) -> bool:
    return not hasattr(handle, "value")


def pget(handle) -> int:
    """Read a (possibly struct-typed) port as one packed integer.

    Verilator exposes a packed-struct port as a single vector; VCS exposes it as a scope whose children
    are the members (declaration order, first member = MSB).  ``pget`` hides the difference."""
    if not _is_struct(handle):
        return int(handle.value)
    v = 0
    for m in handle:
        v = (v << _width(m)) | pget(m)
    return v


def _width(handle) -> int:
    return len(handle) if not _is_struct(handle) else sum(_width(m) for m in handle)


def pset(handle, value: int) -> None:
    """Drive a (possibly struct-typed) port from one packed integer (see ``pget`` for the layout)."""
    if not _is_struct(handle):
        handle.value = value
        return
    members = list(handle)
    shift = _width(handle)
    for m in members:
        w = _width(m)
        shift -= w
        pset(m, (value >> shift) & ((1 << w) - 1))
