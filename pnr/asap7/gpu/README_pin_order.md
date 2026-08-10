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
