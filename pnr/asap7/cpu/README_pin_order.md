# `pin_order.cfg` — why the CPU macro's boundary is pinned

`pin_order.cfg` is consumed by `FP_PIN_ORDER_CFG` in `config.json`. It fixes the
side and ordering of every signal pin on the `rv32i_cpu_top` hard macro.

The file itself carries **no comments** — LibreLane's parser
(`librelane/scripts/odbpy/ioplace_parser/parse.py`) only recognises `#N`/`#E`/
`#S`/`#W`/`#BUS_SORT` direction markers and `@annotation` lines. Any other line
beginning with `#` is parsed as a pin identifier and the step dies with
`identifier/regex '#' requires a direction to be set first`. Hence this README.

## What goes wrong without it

Without `FP_PIN_ORDER_CFG`, OpenROAD's IO placement free-floats the macro's pins
based on whatever internal placement that particular block run produced — and
block-level placement here is not reproducible (setup WS bounced +21.64 /
+14.36 / +2.80 ps across three runs of near-identical RTL).

Measured across two consecutive regenerations (GH #96, 2026-08-09), diffing all
401 signal pins between the two LEFs:

- **393 of 401 pins moved**, some by ~126 µm inside a 130 × 130 µm macro.
- Only `clk_i` stayed fixed at (6.078, 0.0); `rst_n_i` moved 31.728 → 25.572.

That churn propagated all the way to the integrating SoC:

| Stage | Run 21 (good) | Run 22 (bad) |
| --- | --- | --- |
| post-CTS `cpu_clk` worst hold skew | −485.6 ps | **−922.1 ps** |
| post-CTS hold-violating endpoints | 805 | **4702** |
| hold buffers inserted | 680 | **4814** |
| final `HB4xp67` population | 1934 | **6017** |
| final `cpu_clk` setup WNS | −60.66 ps | **−596.00 ps** |
| final `sys_clk` setup WNS | +83.79 ps | +40.78 ps |

Chain: pin reshuffle → SoC placement perturbed around `u_cpu` → TritonCTS builds
a worse-balanced `cpu_gated_clk_regs` subtree (a new `delaybuf_0_cpu_clk`
appears; `u_cpu_cg.u_icg` CLK→GCLK goes 79.3 → 285.1 ps, same cell type, so
loading/placement not library) → skew roughly doubles → the resizer pads
hundreds of short paths for hold → those chains (9+ deep) eat the setup budget.

**Rejected hypothesis, recorded so it is not re-tried:** the RTL edit that
forced the regeneration made `apb_pready_o`/`apb_pslverr_o` registered outputs,
and the obvious theory was that their faster clk→Q caused the hold explosion.
Measured delta is only ~9–14 ps (`apb_pready_o` cell_rise 247.9 → 238.7 ps) —
one to two orders of magnitude too small for a ~900 ps skew swing. The RTL
change merely *triggered* a regeneration; the instability is the bug.
The 25 ps hold margin from bead `s9f` is likewise not the amplifier: raw
pre-fix violations were already hundreds of ps.

## Provenance and regeneration

The current file was generated from the **known-good run-21 abstract** — the
macro that closed the SoC at `cpu_clk` −60.66 ps / 1189.5 MHz.

To regenerate after a deliberate port-list change, classify each `PIN` in a
reference LEF by which edge its first `RECT` touches (`y1==0` → S, `y2==SIZE`
→ N, `x1==0` → W, else E), sort each side by the along-edge coordinate (the
parser expects low→high), escape `[`/`]` since entries are anchored regexes, and
emit `#N`/`#E`/`#S`/`#W` sections. Power/ground are **excluded** — `io_place.py`
filters `POWER`/`GROUND` bterms itself, so the file lists 401 signal pins only.

The step errors if a design pin is missing from this file or vice versa, so
adding a port fails loudly rather than silently reverting to free-floating.
