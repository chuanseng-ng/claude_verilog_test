# Pin Order Configuration — rv32i_cpu_top Sky130 Stage 1 (v2 — GH #104)

`pin_order.cfg` in this directory is consumed directly by LibreLane's
`Odb.CustomIOPlacement` step (`ioplace_parser`). That parser has **no comment
syntax** — the only special tokens it recognizes are direction markers
(`#N`, `#S`, `#E`, `#W`, `#NR`, `#SR`, `#ER`, `#WR`, or `#BUS_SORT`) matched by
the regex `^#\s*([NEWS]R?|BUS_SORT)`. Every other line, including any other
`#`-prefixed text, is parsed as a literal pin-name regex. Keep the `.cfg` file
limited to direction markers, blank lines, and bare signal names — put all
rationale/history here instead.

## History

A v1 of `pin_order.cfg` existed but was never wired into `config.json` (no
`FP_PIN_ORDER_CFG` reference) — the committed macro's actual pin placement
came from LibreLane's default automatic IO placement, which produced a severe
imbalance: N=255, S=125, E=20, W=1 (of 403 total pins, verified directly from
the LEF PIN geometry). That single-edge concentration (256/565 pin RECTs on
the top edge) caused an unroutable met4 escape-throat congestion (GRT-0118,
82% of all SoC-level routing overflow) once this macro was integrated into
the Sky130 SoC alongside the sram_controller macro — confirmed via standalone
GRT congestion diagnostics after floorplan/PDN-only fixes (macro-edge
clearance, PDN stripe-pitch coarsening) failed to resolve it. See
`design_state.json` / `memory/pd/run_state.md` for the full diagnosis chain.

A first regen attempt (`RUN_2026-07-19_16-00-25`) crashed at step
25-odb-customioplacement with `identifier/regex '#====...' requires a
direction to be set first` — the header/rationale comment blocks in the v2
`.cfg` (including inline `# AXI4 ...` group comments) were being parsed as
illegal pin regexes. Fixed by stripping ALL comment text from the `.cfg` and
moving it here.

## v2 Strategy

Balance ~401 total signal bits roughly evenly across all 4 edges
(~100 bits/edge), grouped for SoC-routability sense:

- **N (95 bits)** — AXI4 WRITE channel (AW+W+B) + clock/reset/irq/commit_valid.
  N faces the SoC's open flat-logic region (crossbar, AXI-Lite interconnect)
  above the CPU macro in the SoC floorplan — the natural consumer-adjacent
  edge.
- **S (97 bits)** — AXI4 READ channel (AR+R) + trap/debug-state misc.
- **E (113 bits)** — APB3 debug slave + debug_rs1_data_o (paired: both are
  part of the debug-observability path).
- **W (96 bits)** — commit interface (commit_pc_o/commit_insn_o) +
  debug_rs2_data_o.

This rebalance addresses the PIN-CLUSTERING root cause. The SoC integration
ALSO repositions both macros away from the die's (20,20) corner (previously
only 20 µm margin on south/west) to give every edge genuine escape room —
see `pnr/sky130/soc/macro_placement.cfg`.

## v3: DFT scan boundary (bead j41m.4, DFT_ARCHITECTURE.md 14.10)

Six pins are added, all on the **N edge**, appended after `commit_valid_o` so every existing N-edge
entry keeps its position in the list: `scan_mode_i`, `scan_en_i`, `scan_in_i[1:0]`, `scan_out_o[1:0]`
(N 95 -> 101 bits; 401 -> 407 signal bits, checked by matching every port bit of the sv2v netlist against exactly one entry). S/E/W are untouched. N was chosen because it faces the SoC's open
flat-logic region where `u_dft_ctrl` and the top-level scan ports (`scan_in_i[7:6]`, `scan_out_o[7:6]`)
are routed from; it is also the edge that already carries `clk_i`/`rst_n_i`.

There is deliberately **no** `scan_clk_i` and **no** `scan_rst_ni` pin: `clk_i` is already the muxed test
clock (soc_top's `dft_clk_mux` sits ahead of `u_cpu_cg`) and the macro's only reset is the synchronous
`rst_n_i`, which `soc_top` drives from a net that equals `scan_rst_ni` in scan mode.

MEASURED (RUN_2026-10-16_02-27-26, `tools/verif/lef_pin_diff.py` old vs new LEF): appending 6 names
to the N list **did move the other N-edge pins**. 409 pins in the new LEF (403 + 6); of the 403 existing
pins, 308 are identical (all S, E, W and the 2 power pins) and **95 moved, exactly the 95 pre-existing
N-edge signal pins** (the ioplacer re-spaces the whole edge: max shift 214.4 um, mean 106.3 um along x,
same layer met2). The 6 new pins sit at the east end of N (x = 3393.5 .. 3570.9 um). `ERRORS_ON_UNMATCHED_IO:
both` did its job (every port bit matched one entry). Consequence: the SoC must be re-placed/re-routed
against the new LEF (it was, RUN_2026-10-16_04-53-49); a stale SoC run against the old LEF is invalid.
If a later change must not move the N pins, they would have to be pinned at fixed coordinates (a different
mechanism than this file), which was not attempted.
