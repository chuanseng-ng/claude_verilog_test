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
The coordinates are now frozen by `pin_template.def` (v4 below).

## v4: frozen pin coordinates (bead lu09)

`pin_template.def` is derived from the committed `macro/rv32i_cpu_top.lef` (`python3 tools/verif/pin_lock.py gen
macro/rv32i_cpu_top.lef pin_template.def`) and wired in as `FP_DEF_TEMPLATE` with `FP_TEMPLATE_MATCH_MODE: strict`.
`pin_order.cfg` is unchanged and still decides which pins exist and on which side; the template decides where.
LibreLane 2.4.13 runs `Odb.ApplyDEFTemplate` right after `Odb.CustomIOPlacement` and overwrites each pin's shape with
the template's, so whatever spacing `CustomIOPlacement` computed is discarded.

Mechanisms evaluated (LibreLane 2.4.13 source, `/home/neuromorphic/Downloads/Github/librelane`):

| Mechanism | Verdict |
| --------- | ------- |
| `FP_DEF_TEMPLATE` (chosen) | Exact coordinates, byte-identical to the committed LEF. Strict mode exits `EX_DATAERR` when the design and template pin sets differ in either direction, so a new pin fails loudly instead of moving anything. |
| Reserved spare slots (`$N` virtual pins in `pin_order.cfg`) | Rejected. `equally_spaced_sequence` spaces `floor(tracks / (pins + virtual))` apart, so inserting `$N` now would itself move all 101 N pins, and a later pin only keeps the pitch while spares remain. It also fails silently once they run out. |
| Explicit placement via `FP_IO_*` | Does not exist in 2.4.13: those variables set pin length, extension and thickness only. `OpenROAD.IOPlacement` (the only `place_pins` caller) is skipped when `FP_PIN_ORDER_CFG` is set. |
| Custom IO placement script / plugin step | Would work, but is new code to own for what `FP_DEF_TEMPLATE` already does. |

Known limits of the chosen mechanism:

- `GlobalPlacementSkipIO` is skipped whenever a template is set (`openroad.py:1407`). That pass only seeds a
  placement that `OpenROAD.GlobalPlacement` redoes (`PL_SKIP_INITIAL_PLACEMENT` defaults to false), so no effect on
  cell placement is expected, but this was not measured. Treat the first harden under the lock as not a single-variable
  comparison with RUN_2026-10-16_02-27-26.
- `ApplyDEFTemplate` does not check that two template pins overlap (measured: two pins on one slot, exit 0, no
  message). `tools/verif/pin_lock.py check` does, together with min spacing and the template-vs-LEF comparison.
- The template does not move `DIEAREA`; a die change only produces a warning. A die change invalidates the lock.

Adding a pin: add its name to `pin_order.cfg`; add a pin line (same format, a free slot, mfg-grid aligned) to
`pin_template.def`; re-harden; commit the new LEF. Between the template edit and the new LEF, `make -C pnr
sky130-cpu-pin-lock-check` reports the new pin as "pending" and still passes. After the harden, run it with
`NEW_LEF=<run>/final/lef/rv32i_cpu_top.lef` to prove no existing pin moved.

The same exposure exists on the ASAP7 CPU and GPU macros (`pnr/asap7/`); the lock is not applied there.

## v5: MBIST boundary (bead c54a, DFT_ARCHITECTURE.md 16.7)

96 pins are added: `mbist_run_i` and `mbist_cfg_i[25:0]` (27 inputs) on the **N** edge, `mbist_status_o[68:0]`
(69 outputs) on the **S** edge. N and S were chosen because they are the least dense edges (101 and 97 pins over
3600 um, against 113 over 1800 um on E); after the change N has 128 and S 166 (46 pins/mm, below E's 63).

`pin_template.def` was extended WITHOUT moving any existing pin: there is no free contiguous edge segment (each
edge is already spread over its full length by the ioplacer), so every new pin sits in the middle of an existing
inter-pin gap, snapped to the met2 track grid (230 nm + k * 460 nm). N: gaps 60..86 (east half, nearest the
scan pins, bits in order), S: gaps 24..92 (bits in order). Resulting pitch next to a neighbour is 17.4 um (N)
and 17.9-18.9 um (S), far above the metal spacing. `make -C pnr sky130-cpu-pin-lock-check` reports the 96 pins
as "pending (in template, not yet in LEF)" until the re-harden; after it, run it with
`NEW_LEF=<run>/final/lef/rv32i_cpu_top.lef` to prove nothing moved. The template DEF diff against main is
additions plus the two count lines (`PINS`/`NETS` 407 -> 503).

`pin_order.cfg` only decides which pins exist per side (`ERRORS_ON_UNMATCHED_IO: both`); the template decides where.
The ASAP7 CPU macro (`pnr/asap7/cpu/pin_order.cfg`, an explicit list that already lacks the j41m.4 scan pins) is not
changed: its re-harden is shelved (ma7/lxv/2kn) and j41m.13 must regenerate it with the DFT and MBIST pins.
