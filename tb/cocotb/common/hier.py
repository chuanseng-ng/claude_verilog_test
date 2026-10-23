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
