# Physical verification (DRC + LVS) of the ICC2 arm GDS, Sky130 `rv32i_cpu_top` (step B7a)

**Comparison run, measure and report only.** The layout was not modified and no P&R was run. Subject: `pnr/commercial/impl/icc2/runs/b5a_icc2/out/`
(`rv32i_cpu_top.gds`, `.def`, `.full.pnl.v`). Open decks only (Calibre/PVS have no public Sky130 decks): Magic 8.3.489, Netgen 1.5.278,
KLayout 0.29.4 and OpenROAD `edf00dff` inside `ghcr.io/librelane/librelane:2.4.13` (podman), PDK open_pdks `0fe599b2`. Magic and Netgen run
LibreLane's own scripts and `_env.tcl` settings (copied from the OpenROAD-arm run `b2_openroad`); KLayout runs `sky130A_mr.drc` with the
LibreLane options (`feol beol offgrid seal`, `floating_metal=false`). Harness, one command per arm: `pnr/commercial/signoff/drclvs/`
(`make -C pnr/commercial/signoff/drclvs ARM=icc2|innovus|openroad <target>`, targets in the Makefile header). Every tool ran under
`guard_run.sh` (= `safe_run.sh` + a MemAvailable watchdog that `podman kill`s the container below 1.5 GB), one heavy tool at a time.

## Result in one paragraph
**The ICC2 GDS as written cannot be verified: it has three defects, found before any rule ran** (below). On a measurement copy that repairs
them, **LVS is clean except for 7 floating n-well (VPB) islands: Netgen reports "Circuits match uniquely" once those 7 nets are merged, and
mismatches on exactly those 7 nets (13 pins) when they are not**; all 503 signal ports and every signal net match the netlist, and the
power nets are intact. **KLayout DRC: 4,877 violations in 9 rules** (OpenROAD arm: 0): 4,659 (li.1/li.3) come from **14 ICC2 signal wires on li1, up to
400 um long, routed straight through SRAM macro interiors**; 218 are outside the macros. Magic DRC and antenna: see the table.

## Table against the OpenROAD reference
| Check | OpenROAD / LibreLane (`b2_openroad`) | ICC2 (`b5a_icc2`) | Read with |
|---|---|---|---|
| GDS integrity | GDS written by Magic from DEF + macro GDS; complete | **3 defects** (SRAM instances point at an empty, name-truncated cell; no pin metal; 245 orphan library cells) | section "GDS checks" |
| LVS, as delivered | Netgen "Circuits match uniquely" (Magic DEF+LEF extraction) | **MISMATCH**, 7 well-island nets; 34,794 vs 34,788 device classes, 35,501 vs 35,494 nets | ICC2 DEF cannot be read by Magic (via names), so the ICC2 extraction is from the GDS (std cells and SRAM as LEF abstracts), see "LVS" |
| LVS, 7 well islands merged | n/a | **Circuits match uniquely** (34,788 devices, 35,494 nets, 505 ports) | the merge is an analysis step, not a pass |
| KLayout DRC | **0** | **4,877** (li.3 4,055; li.1 604; m4.5ab 132; nwell.2a 66; m3.6 6; nwell.1 4; hvtp.1 4; hvtp.2 4; m2.2 2) | run on the ICC2 GDS with SRAM refs repaired, as delivered (no pin metal) |
| KLayout DRC, outside SRAM footprints | 0 | 218 | |
| Magic DRC total | 27,733,913 (log `[INFO] COUNT`) | **PENDING** (killed by the memory watchdog, see below) | |
| Magic DRC inside SRAM footprints (45a) | 27,730,287 (all but 3,626) | **PENDING** | same classifier for both: streaming awk over the report (`scripts/magic_drc_classify.sh`, reproduces the OpenROAD figures exactly from its 1.17 GB report) |
| Magic DRC outside SRAM, by rule | 3,626, all `nwell.4` (abstract artifact) | **PENDING** | |
| Antenna | 116 nets / 119 pins (OpenROAD `check_antennas`) | **532 nets / 601 pins** (same checker, same tech-LEF rules; 640 violated layer reports on met1-met4 and their vias) | ICC2 native 0 (`check_routes -antenna`) used its own rule set and treats diode-protected nets as safe. Run on the ICC2 DEF with via names mapped to the tech-LEF vias (wire areas unchanged); the OpenROAD figure is after its antenna repair, so this is not a like-for-like repair state either |

## GDS checks (done first)
1. **Geometry or references?** Both. Standard cells and SRAM geometry are in the file (`write_gds -merge_files` merged `sky130_fd_sc_hd.gds` and
   the SRAM GDS; 441 std-cell structures, none empty; SRAM `sky130_sram_1kbyte_1rw1r_32x256_8` with 20,516 own shapes). **But the 10 SRAM
   instances in the top cell reference `sky130_sram_1kbyte_1rw1r_32x25_0`, an EMPTY structure.** The real name is 33 characters; ICC2 shortened it to 32 with a
   `_0` suffix while the merged macro GDS keeps the full name, unreferenced. As delivered, the layout contains no SRAM at all (placement matches the DEF).
   Repair for measurement (`scripts/gds_fix_refs.py`, original untouched): re-point the 10 instances to the unique orphan root whose name starts with the stem;
   the macro's content is byte-identical (137,719 shapes) to the PDK GDS and to the OpenROAD-arm GDS. **ICC2 fix: add `-long_names` to the `write_gds` call** (`06_finish.tcl:67`;
   man page: "Writes out names longer than 32 characters ... By default, the command limits each name string to 32 characters"). Not run.
2. **Orphan roots.** The merge also leaves 245 unreferenced library structures as extra top cells; KLayout's deck aborts ("multiple top cells"). Pruned in the
   measurement copy. **ICC2 fix: `write_gds -merge_adding`** ("the output file will have exactly one top cell", child-cell conflicts resolved by a name prefix) **or
   `-merge_gds_top_cell <macro top>`** ("only the cells in its hierarchy are considered ... all remaining cells are removed"). Both from the X-2025.06-SP3 man page, not run;
   `-merge_adding` may rename the macro (prefix) and needs a check that the SRAM keeps its name.
3. **Pin metal missing.** `write_gds -output_pin text` writes pin names only. The pin rectangles (met2 0.28 x 4.0 um, met3 4.0 x 0.6 um, 503 of them, at the die edge)
   are in the DEF but not the GDS; the text sits at the rectangle's centre, 1.7 um from the nearest metal stub, so **0 of 503 pin texts touch metal** and an extraction
   from the GDS has 503 unconnected port nodes. **ICC2 fix: `write_gds -output_pin geometry` (or `all`, which is the command's default; `06_finish.tcl:67` passes `-output_pin text` explicitly).** Added from the DEF in a second measurement copy (`scripts/gds_add_pins.py`) for LVS only. KLayout DRC ran without it
   (the 6 `m3.6` min-area hits at x = 3596 um, the die's right edge, look like the stubs of these pins).
4. **Layer/datatype map** (spot check, `reports/icc2_gds_inspect.txt`): li1 67:20, met1 68:20, met2 69:20, met3 70:20, met4 71:20, met5 72:20, nwell 64:20, diff 65:20,
   poly 66:20, licon 66:44, npc/nsdm/psdm 95:20/93:44/94:20 present with the Sky130 numbers; vias are `$$mcon_cc`, `$$via_cc`, `$$via2_cc`, `$$via3_cc`, `$$via4_cc`
   array cells (mcon 67:44, via 68:44, ... inside them). Pin text is on 69:5 and 70:5. The mapping is right. There is no VPWR/VGND text; the power labels for the
   extraction were placed on the first met4 PG strap of each net, taken from the DEF.
5. **Power nets.** The netlist ties SRAM `vccd1`/`vssd1` to `VPWR`/`VGND`, as the OpenROAD arm does (`PDN_MACRO_CONNECTIONS`). In the layout every instance's
   VPWR/VGND/VPB/VNB pin is on VPWR/VGND except the 7 islands below (`scripts/spice_well_islands.py`).

## LVS
Method (the ICC2 DEF cannot be used: it names vias `via_cc`, `mcon_cc`, ... that are not in the tech LEF, so Magic's DEF reader dropped 408,960 via references, and it
uses via arrays): Magic extraction from the repaired GDS plus the pin rectangles, std cells and SRAM as the PDK LEF abstracts (same abstract-cell scope as LibreLane's DEF-mode LVS, so
cell internals are not compared in either arm), against `rv32i_cpu_top.full.pnl.v` (PG netlist with taps, endcaps, fillers) through LibreLane's `netgen/setup.tcl`.
Two netlist artifacts had to be removed in a measurement copy of the netlist (connectivity unchanged): the `supply1 VPWR; supply0 VGND;` declarations (Netgen makes phantom devices of them) and
**three nets that differ only in case (`\u_core/N1435` vs `\u_core/n1435`, same for 1438 and 1439), which Netgen merges because it reads the PDK SPICE case-insensitively.**
- Port-level check, independent of Netgen (`scripts/port_conn_compare.py`): for all 503 signal ports the set of (cell, pin) attached to the port net is identical in the layout and the netlist (0 differences).
- Netgen on the cleaned netlist, layout as extracted: MISMATCH, 34,794 vs 34,788 device classes, 35,501 vs 35,494 nets. The only unmatched nets (besides the VPWR/VGND fragments they cause)
  are 7 well-tie islands, each one cell group whose `VPB` (n-well) pin is not connected to the VPWR net: 13 pins on `a22o_1` x3, `nor2b_1`, `decap_3` (an endcap), `fill_8` and `fill_1`, around
  x = 1870-2040 um, y = 890-910 um, in the 200 um gap between two SRAMs where rows are cut by the macros. The ICC2 tap/endcap placement does not reach them (taps 63,237, endcaps 4,210; OpenROAD
  uses a 10 um tap halo at macros). This is a real well-tap gap (floating n-well), not an extraction artifact; it cannot be told apart from a LEF-abstract limitation without the cell GDS, but the OpenROAD arm,
  checked the same way, has none.
- Same, with the 7 island nets renamed VPWR in the extracted SPICE: **Circuits match uniquely** (34,788 devices, 35,494 nets, 505 ports). Nothing else differs: no opens, no shorts on any signal or PG net.
- Not covered: transistor-level LVS of cell internals and the SRAM (abstracts in both arms); shorts between ICC2's li1 wires and SRAM-internal polygons are not visible to an abstract-based LVS (see DRC).

## KLayout DRC (`reports/icc2_klayout_drc_by_rule.txt`, `icc2_klayout_drc_locate.txt`)
| Rule | Count | Where | Cause |
|---|---|---|---|
| li.3 (li spacing 0.17) | 4,055 | all inside 3 SRAM footprints | ICC2 signal wires on li1 over the macro |
| li.1 (li width 0.17) | 604 | all inside the same 3 | same |
| m4.5ab (met4 spacing 0.4 to wide met4) | 132 | channels, x 1342-2839, y 141-1597 | signal met4 too close to the 3.1 um PG straps |
| nwell.2a (nwell spacing 1.27) | 66 | x 1536-2741, y 345-1163 | cell/filler n-well gaps in the SRAM channels |
| m3.6 (met3 min area 0.24) | 6 | right die edge | probably the missing pin metal |
| nwell.1, hvtp.1, hvtp.2 | 4 each | x 1945-1998, y 862-906 | same area as the well islands |
| m2.2 (met2 spacing 0.14) | 2 | top/bottom die edge, x 2241-2278 | |
**The li1 finding, root cause in the ICC2 scripts (not changed):** li1 is an enabled routing layer, and nothing keeps the router off it.
(1) `pdk/sky130/scripts/gen_techfile.py` writes every `ROUTING` layer of the tech LEF, li1 included, into the .tf with `isDefaultLayer = 1` and a pitch (lines ~170-178).
(2) The generated `pdk/sky130/build/ndm/sky130_tech_setup.tcl` line 5 is `set_attribute -objects [get_layers li1] -name routing_direction -value vertical`, i.e. li1 gets a routing direction like
met2/met4; its header comment (line 3) says "li1 ... excluded from signal routing", but no statement implements that. Only the track creation skips li1 (`gen_techfile.py:251`), so li1 has no track grid
and the router uses it off-grid for pin access and long hops. (3) The only layer restriction in the flow is `set_ignored_layers -min_routing_layer met1 -max_routing_layer met4`
(`impl/icc2/scripts/setup_design.tcl:17`, repeated in `reload.tcl:2`), which limits the layers used by optimisation and RC estimation, not `route_auto` (`05_route.tcl:20`), and no `route.*` app option sets a minimum routing layer
anywhere in `05_route.tcl`, `05b_repair.tcl` or `05c_repair.tcl`. (4) The SRAM LEF obstructs met1-met4 only (no li1 OBS), so li1 is open over the macro. Candidate fixes to verify, not applied: set a hard minimum
layer for the router (`report_app_options route.common.*` lists the net-min-layer options) or give the tech setup an explicit line that removes li1 from routing (e.g. `routing_direction none`), and add a li1 routing blockage over the macros.
The router used li1 as a long-haul layer: 14 wire segments in the top cell lie over SRAM footprints (for example 391 um and 387 um vertical traces through
`gen_data_sram_1`, 398 um and 400 um through two icache SRAMs). The SRAM LEF obstructs met1-met4 but not li1. li1 over the OpenRAM interior is a real DRC problem and a probable short
to macro-internal li; the abstract LVS cannot see it. The OpenROAD arm has none (its router does not use li1).

## Magic DRC and antenna
**Magic DRC: PENDING.** Three attempts. (1) Killed at 9.00 GiB RSS by my own watchdog cap (set too low: the OpenROAD-arm run peaked at 9 GiB and was killed by LibreLane at 10 GB);
(2) lost to the host power-off of 10-27; (3) ran 42 min (GDS mode, SRAM real, ~8.2 GiB RSS) and was killed by the watchdog at MemAvailable 1.46 GiB while Innovus, PrimeTime and StarRC jobs
were running (host load 20-40); Magic writes its report only at the end, so no partial result exists. The harness is ready and the classifier is validated on the OpenROAD report.
One line, to run when `MemAvailable >= 11 GiB` and the other jobs are idle (about 30 min):
`cd pnr/commercial/signoff/drclvs && GUARD_RSS_GB=11 make ARM=icc2 SRAM_MODE=real mdrc mdrc-class` (writes `reports/icc2_magic_drc_real_by_rule.tsv`: per rule, inside SRAM / straddling / outside).
A lighter variant that skips the SRAM-internal flood (SRAM as LEF abstract, about 3 GiB, gives only the outside-SRAM rules): `... make ARM=icc2 SRAM_MODE=abstract mdrc mdrc-class`.
Expectation (inference, not measured): the 10 SRAM instances are the same macro as in the OpenROAD arm, so the inside-SRAM count should be of the order of 27.7 M; the open
question is the outside count (3,626 `nwell.4` in the OpenROAD arm), where the 7 well islands and the li1 wires over the macros may add entries.

**Antenna:** 532 nets / 601 pins violate (OpenROAD `check_antennas -verbose`, `reports/icc2_antenna.rpt`), against 116 / 119 in the OpenROAD arm. ICC2's own check reported 0 because of its rule set (see caveats in
`icc2_pnr_summary.md`). Magic and KLayout have no antenna check in the Sky130 decks used here (the KLayout deck has none).

## Tool gotchas (for the agent suite)
- The LibreLane image is nix-built: `#!/bin/bash` scripts fail with "no such file"; invoke `bash script.sh`. `/tmp` is not mounted; keep helper files under `$HOME`.
- podman `--memory` is not enforced here and safe_run's `MemoryMax` is not either: only a watchdog that `podman kill`s on MemAvailable works. Its start gate is in whole GiB truncated
  (10.8 GiB reads as "10G").
- ICC2 `write_gds`: names over 32 characters are truncated and the instances keep the short name (empty structure); the merged libraries become orphan top cells; `-output_pin text` has no pin metal.
  Check these three before trusting any GDS check on an ICC2 GDS.
- ICC2 DEF via names are ContactCodes (`via_cc`, `mcon_cc`, ...); Magic and OpenROAD readers do not know them, and Magic does not read `DO n BY m STEP` via arrays.
- Magic: `port makeall` silently does nothing on GDS text labels; `findlabel NAME; port make` works. Without port-flagged labels the extracted top subckt has no pins. `gds noduplicates true`
  keeps LEF abstracts when the GDS also defines the cell.
- Netgen folds case across Verilog names once a case-insensitive SPICE has been read: nets `N1435`/`n1435` become one. Rename before LVS. A `supply1`/`supply0` declaration becomes a phantom device.
- Netgen's mismatch report is a cascade: a handful of VPB islands produced 29,600 "Net:" fragments until the port list and the case collisions were fixed. Fix inputs first, then read the fragment list.
- KLayout's `sky130A_mr.drc` needs a single top cell.
- `guard_run.sh` v1 polled `podman inspect` every 3 s and cost about one CPU; v2 uses `scripts/watchdog.sh` (PID looked up once, `/proc` polled every 10 s). With a container watchdog, set the RSS cap above the tool's real peak (Magic DRC: 9-10 GiB).
- A stale container name (`podman ps -a`) after a host power-off blocks `podman run --name`; `podman rm -f` it first.

## Files
`pnr/commercial/signoff/drclvs/{Makefile,arms/,scripts/,reports/}`; run products (gitignored) in `runs/icc2/` (repaired GDS `runs/icc2/gds/`, LVS inputs `lvs_in/`, KLayout XML `kdrc/`, Netgen reports `lvsgds_clean/`, `lvsgds_merged/`).
Superseded attempts (DEF-mode extraction that dropped the vias; GDS extraction before the pin metal was added) are in `runs/icc2_attempt_nopins/` and `runs/icc2/lvsgds_attempt1_noports/` and are not results.
