# `pin_order.cfg` — GPU macro boundary pin

`pin_order.cfg` is consumed by `FP_PIN_ORDER_CFG` in `config.json`. It fixes
the side and ordering of every signal pin on the `gpu_top` hard macro.

Like the CPU macro's `pin_order.cfg` (`pnr/asap7/cpu/pin_order.cfg`), this
file carries **no comments**. LibreLane's parser
(`librelane/scripts/odbpy/ioplace_parser/parse.py`) only recognises `#N`/
`#E`/`#S`/`#W`/`#BUS_SORT` direction markers and `@annotation` lines — any
other line starting with `#` is parsed as a pin identifier and the step dies
with `identifier/regex '#' requires a direction to be set first`. See
`pnr/asap7/cpu/README_pin_order.md` for the measured evidence of why this
matters and the full failure chain (pin reshuffle → SoC placement
perturbation around the macro → CTS skew doubling → hold-buffer explosion →
setup WNS collapse), root-caused for the CPU macro in GH #96.

## Why this file is untuned

The CPU's `pin_order.cfg` was **hand-tuned by function** after generation,
because that macro had a measured timing regression to fix (run 21 → run 22,
`cpu_clk` setup WNS −60.66 → −596.00 ps). The GPU macro has no such
regression — the multiclock SoC (run 23) signed off on the `sys_clk` fabric
domain at +74.8 ps with the GPU's boundary exactly as OpenROAD produced it
that run.

This file is therefore generated directly from the checked-in,
run-23-signed-off `pnr/asap7/soc/macro/gpu_top.lef` via
`pnr/scripts/gen_pin_order.py`, with **no manual reordering**. Its only job
is to pin the boundary to the abstract the SoC already closed against, so
that a future GPU-macro regeneration cannot silently reshuffle it the way
the CPU macro's regeneration did. Tuning it now — moving pins around for a
timing benefit that hasn't been measured — would move the abstract away
from the one run 23 signed off, which is exactly the kind of unreviewed
churn this file exists to prevent.

## Regeneration

```
python3 pnr/scripts/gen_pin_order.py pnr/asap7/soc/macro/gpu_top.lef \
    -o pnr/asap7/gpu/pin_order.cfg
```

Only regenerate after a deliberate GPU port-list change. The generator
classifies each `PIN` by which edge its first `RECT` touches, sorts each
side low → high along the edge, and excludes `POWER`/`GROUND` pins (the
`gpu_top.lef` has 327 total `PIN` records; 2 are `VDD`/`VSS`, leaving 325
signal pins in `pin_order.cfg` — the same pattern as the CPU's 403-total /
401-signal split). The step errors if a design pin is missing from this
file or vice versa, so adding a port fails loudly rather than reverting to
free-floating placement.

## What "pinned" actually guarantees — and what it doesn't

`FP_PIN_ORDER_CFG` constrains **side and along-edge order only**. Given a
fixed side/order, `io_place` distributes pins **evenly** along each edge.
The checked-in `pnr/asap7/soc/macro/gpu_top.lef` was produced by
free-floating placement, whose spacing is irregular by construction — so
an order-only config can never reproduce those exact coordinates, and
that is not a bug in this file.

Measured (GH #96 validation run, `RUN_2026-08-10_19-04-14`, pin positions
read from `24-odb-customioplacement/gpu_top.def`, which settles bterm
placement — later steps don't move pins):

- Side and along-edge order: **exact match on all 4 sides** (N 9/9, E
  143/143, S 170/170, W 3/3), 0 mismatches against `pin_order.cfg`.
- Absolute along-edge coordinate vs the checked-in LEF: **0 of 325 pins
  land at the same position** — median displacement 42.6 µm, p90
  ~117 µm, max 223.5 µm (on a 340 × 340 µm die). E-side pins collapse
  onto a regular `x = 338.0 µm` track, N/S onto `y = 338.0` / `2.0 µm` —
  the signature of even distribution replacing irregular placement.

**The correct determinism criterion is therefore not "pins land on the
checked-in LEF's coordinates."** It is the one the CPU macro was
validated against (`pnr/asap7/cpu/README_pin_order.md`): **two
regenerations with the same `pin_order.cfg` produce identical pin
placement**, because with side/order fixed and `io_place`'s even
distribution being a pure function of side, order, die size, and IO
pitch parameters, there is nothing left free to vary. For the GPU this
holds by construction from the same argument that makes it true for the
CPU; it has not been re-proven with a second independent GPU run here
(that run would only reconfirm byte-identical output, not add new
information — see the validation-run report on
`claude_verilog_test-606` for whether it was run anyway).

**Consequence, not yet acted on:** the *next* time `gpu_top` is
regenerated with this `pin_order.cfg`, the macro's boundary will shift
once — by the amounts above — relative to the currently checked-in
`pnr/asap7/soc/macro/gpu_top.lef`, in a side/order-preserving way (unlike
the CPU's 393/401 cross-edge reshuffle, this is milder and one-time, not
churn-per-regeneration). That shift still means `pnr/asap7/soc/macro/
gpu_top.{lef,lib,...}` and the run-23 SoC sign-off baseline would need a
deliberate refresh + re-validation before the *next* GPU macro
regeneration is folded into an SoC build. This file does not perform
that refresh — it only stops future regenerations from being
non-deterministic on top of it.

Two pins (`rst_n`, `m_axi_wdata[17]`) sit geometrically near a die
corner (`RECT 336 11.208 340 11.4` and `RECT 336 329.268 340 329.46`
respectively — touching the E edge at `x2 = 340` while `y` sits only
~11 µm from the S/N edge). Checked directly: under the generator's own
rule (`y1==0`→S, `y2==SIZE_Y`→N, `x1==0`→W, else E) *and* under a
nearest-edge rule (distance to E = 0 in both cases, versus ≥10.5 µm to
S/N), both agree on **E** — there is no actual rule disagreement for
these two pins, despite their corner-adjacent geometry.
