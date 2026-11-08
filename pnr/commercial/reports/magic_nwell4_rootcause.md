# Magic `nwell.4` outside / straddling the SRAM footprints: root cause (cleanup item 2)

Scope: the three Sky130 `rv32i_cpu_top` arms (OpenROAD B2, ICC2 b6, Innovus b6). Date 2026-11-08.
Status words: **MEASURED** = produced by a run listed in section 8; **INFERRED** = not isolated by an experiment.

## 1. Result

All `nwell.4` items outside or straddling the SRAM footprints, on all three arms, are one artefact of the Magic
sign-off mode, not a layout defect:

- The sign-off Magic DRC (`scripts/magic/gds_abs_drc.tcl`) loads the std cells as **PDK LEF abstracts**
  (`gds noduplicates true` keeps the abstract when the GDS also carries the cell). An abstract carries the cell's
  `nwell` rectangle but **no tap implant and no licon** (MEASURED: `sky130_fd_sc_hd__tapvpwrvgnd_1` in the LEF has
  `nwell`, `pwell`, `met1`, `li1` only). Magic's `nwell.4` is "nwell with no `nsc`" (an n-substrate contact), so
  every std-cell n-well strip is reported.
- The same layout checked with the **std cells taken from the GDS** (real tap diffusion and licon) reports **0**
  `nwell.4` in every window tried (9 windows x 3 arms), while the LEF mode reproduces the full-run coordinates
  exactly in the same windows (MEASURED, section 4).
- An independent geometric check on the flattened real GDS (KLayout, the `nwell.4` definition: merged n-well region
  with no `licon1 & tap & nsdm`) finds **0 of 2,413 / 3,435 / 2,438 n-well regions without a contact** (ICC2 / Innovus /
  OpenROAD; includes the SRAMs) (MEASURED, section 5).
- Therefore: **no layout fix and no ECO is needed, and none was made.** Nothing was re-extracted or re-timed. The
  disposition is a **PROPOSED waiver (section 7), not waived**; the user decides. The flow-side alternative that
  removes the artefact instead of waiving it is in section 7.5.

Counts do not change: OpenROAD 3,626 / ICC2 3,035 + 592 / Innovus 4,226 + 737 (`comparison.json` unchanged except the
note text and the new `nwell_regions_without_nsc` rows).

## 2. Rule and mechanism

`sky130A.tech` (`$PDK_ROOT/sky130A/libs.tech/magic/sky130A.tech`):

```
 templayer nwell_with_tap          (line 1660)
 bloat-all nsc,mvnsc nwell,pnp
 templayer nwell_missing_tap nwell,pnp
 and-not nwell_with_tap
 ...
 variants (full)                    (line 4086)
 cifmaxwidth nwell_missing_tap 0 bend_illegal "All nwells must contain metal-connected N+ taps (nwell.4)"
```

Every n-well area that no `nsc` bloats into is an error, in `drc(full)` only. `nsc` is a licon on an n-tap, which
exists only in the real cell geometry. The LEF abstract has none, so the check cannot pass in LEF mode, whatever
the layout. The earlier wording ("abstract LEF views don't expose the n-well geometry", `memory/pd/knowledge.md`)
had the outcome right and the mechanism slightly wrong: the abstract **does** carry the n-well, it lacks the tap
contact.

Why a handful of thousand items and not one per cell: Magic reports the area in tiles. In both full reports, 3,331
of 3,627 (ICC2) items have an x edge on a multiple of 314.56 um (MEASURED), the rest end on a SRAM or the core edge.
One merged strip is therefore reported up to 12 times. The n-well strips are 2.83 um high (an N row and the abutting
FS row merge) and 5.44 um apart, which is why they stack up in the `y` lists. The KLayout merged-region counts
(ICC2 468 outside + 585 straddling, Innovus 1,489 + 586, OpenROAD 1,078 + 0) are the region-level view of the same items.

Why SRAM interiors show 0 `nwell.4`: the OpenRAM cells are loaded from the GDS with their own tap geometry. This
is also why the 27.7 M inside-footprint items of bead `45a` are a different class (other rules) and are not touched
here.

## 3. Classes, per arm (counts from the full Magic reports; coordinates in `drclvs/reports/*_nwell4_items.txt.gz`)

SRAM footprints are `runs/<arm>/sram_boxes.txt`. "Straddle" = the item overlaps a footprint by more than the 0.01 um
classifier tolerance.

| Arm | Class | Items | Geometry | Touches |
|---|---|---|---|---|
| OpenROAD B2 | O1 field / channel strips | 3,474 outside | 2.83 x <=314.56 um, rows of fill/decap/tap + logic | none; ends on tile edges and SRAM halo edges |
| | O2 left-pocket strips | 152 outside | x 20.05 to **89.89**, 2.83 high | SRAM left edge at x=100 (10 um halo, no cell in it); decap_12/decap/tap |
| ICC2 b6 | I1 field / channel strips | 3,035 outside | same geometry as O1 | none |
| | I2 channel strips cut by a SRAM edge | 444 straddle | 2.83 high, penetration into the footprint 0.01, 0.03, 0.09 or 0.13 um (constant per SRAM column) | SRAM left/right edges in the 102 um channel |
| | I3 left-pocket strips | 148 straddle | x 20.05 to **100.01**, penetration 0.01 um | SRAM left edge x=100; fill_1/2/4/8 + decap_3 + tap |
| Innovus b6 | N1 field / channel strips | 3,035 outside | **3,016 identical to I1**; 19 channel strips start at x=119.87 instead of 20.05 | none |
| | N2 channel strips cut by a SRAM edge | 444 straddle | **identical to I2** | SRAM edges |
| | N3 isolated tap-sized wells | 1,191 outside + 292 straddle = 1,483 | 0.84 x 1.61, 2.22 x 1.61, 1.76 x 1.23 um, ...; 1,464 in the left pocket on the 12.9 um tap lattice (x1 = 21.81 ... 98.17) | the 292 end at x=100.01 (SRAM edge) |
| | N4 pocket strip | 1 straddle | 79.96 wide | SRAM edge |

Totals check: OpenROAD 3,474 + 152 = 3,626. ICC2 3,035 + 444 + 148 = 3,627. Innovus 3,035 + 444 + 1 + 1,483 = 4,963.
No class touches a PDN shape, the die edge (the right-hand strips end on tile edges at x <= 3,460), or a decap/fill
cell *as a defect*: decap, fill and tap cells are simply the cells whose abstract n-well is in the strip.

### 3.1 Innovus-specific tap wells (N3) and the +145 straddle difference

MEASURED from the DEFs (components with x2 <= 100 um, y2 <= 920 um):

| Arm | Cells in the left pocket |
|---|---|
| ICC2 b6 | 11,104: fill_8 5,717, fill_1 1,431, fill_2 1,157, **tapvpwrvgnd_1 1,137**, fill_4 983, decap_3 621, few logic |
| Innovus b6 | 1,944: **tapvpwrvgnd_1 1,302**, decap_3 624, 7 logic/decap_*; **no fill_\* cell** (whole die: 3,392 fill vs ICC2 523,316) |
| OpenROAD | 7,366: ef_decap_12 3,203, fill_1 928, decap_3 847, tapvpwrvgnd_1 847, ... |

Innovus left the pocket (hard placement blockage, only taps and endcaps) unfilled, so every tap cell's well is an
isolated 0.84 um island and Magic reports each island on its own. ICC2 and OpenROAD fill the same area, which merges
the wells into one strip per row pair, reported once per tile. The abstract artefact is the same; only the *number* of
items changes with the amount of fill. This is the whole Innovus-specific difference: **+1,191 outside** is the 1,191
isolated tap wells (the 148 pocket strips of ICC2 are straddles, so they are not in the outside number), and the
**+145 straddle** is `(292 isolated tap wells + 1 strip) - 148 ICC2 pocket strips = 145`, exactly (MEASURED, counts
above). The earlier hypothesis in `innovus_b6_report.md` section 8 ("a Magic reading of the tap-only rows in the
blocked pocket; the ICC2 arm has logic cells there and shows none") is **superseded**: ICC2 has fill there and does
show 148 pocket items; the cause is the std-cell abstract, not the pocket.

Observation, not a defect: the Innovus pocket has no filler. KLayout `nwell.2a` 0, the island checker 0 untied wells and
the nsc check 0 wells without contact all hold, so no rule needs filler there. Adding filler would only change how
Magic's items are grouped (it would merge them into strips) and would require re-running the whole sign-off chain on a
candidate for an item that is not a violation. Not done.

### 3.2 Straddle (I2, I3, N2, N4)

The item runs 0.01 to 0.13 um into the SRAM bounding box. INFERRED: the std-cell n-well extends 0.19 um past each
cell edge in the LEF (the tap cell's `nwell` rectangle is x -0.19..0.65 for a 0.46 um cell), so the last cell before a
SRAM edge pushes the strip a few 10 nm into the macro bbox. KLayout `nwell.1`/`nwell.2a` are 0 in both arms, so the
overlap is not a spacing problem. OpenROAD has no straddle because its 10 um halo keeps the cells away from the macro.

## 4. A/B test: same layout, std cells from LEF abstracts vs from the GDS (Magic 8.3.489, drc(full))

Windows are clipped out of each arm's final GDS (KLayout `Layout.clip`, hierarchy kept, `nwell4/clip_gds.py`). P = x 0..101,
y 0..930 (left pocket plus a 1 um SRAM sliver). C = x 0..700, y 419..519 (channel between the I$ and D$ SRAM rows).
F = x 1250..1580, y 925..1265 (one tile column of dense logic). "Edge" = item touches the clip boundary (a well cut
by the window; excluded). Script: `nwell4/magic_drc_variant.tcl` (`STD=lef` reads the PDK LEF and sets `gds noduplicates true`
exactly like `gds_abs_drc.tcl`; `STD=gds` reads neither). Table: `drclvs/reports/nwell4_ab_windows.tsv`.

| Window | OpenROAD LEF -> GDS | ICC2 b6 LEF -> GDS | Innovus b6 LEF -> GDS |
|---|---|---|---|
| P (left pocket) | 153 (+73 edge) -> **0** | 148 (+20) -> **0** | 1,465 (+2) -> **0** |
| C (channel) | 39 (+43) -> **0** | 34 (+17) -> **0** | 192 (+67) -> **0** (+2 edge) |
| F (logic field) | 265 (+398) -> **0** | 86 (+149) -> **0** | 315 (+483) -> **0** |

Same-coordinate check (ICC2, window P): the LEF-mode item `20.050 311.385 100.010 314.215` is identical to the first
item of the full-die report, and 148 of 148 pocket items match the full run (the 20 extra edge items are the clip cut).
The Innovus pocket reproduces its isolated tap wells (1,465) in LEF mode and none in GDS mode. The GDS-mode windows
do not isolate the *other* rules (they show clip-edge and cut-cell effects of the clipping itself, identical in
both modes) and are not a replacement for the full-die run.

## 5. Independent geometric check (KLayout, full die, real std-cell GDS)

`nwell4/nwell_nsc_check.py`: `nsc = licon1(66/44) & (tap(65/44) & nsdm(93/44))`, `nwell = merged nwell(64/20)`,
report `nwell not_interacting nsc`. Run on the GDS that fed Magic (fixed GDS for ICC2/Innovus, the Magic-streamed GDS
for OpenROAD).

| Arm | merged n-well regions | n-tap contacts | **regions without contact** | all regions inside / straddle / outside SRAM |
|---|---|---|---|---|
| OpenROAD B2 | 2,438 | 226,242 | **0** | 1,360 / 0 / 1,078 |
| ICC2 b6 | 2,413 | 233,434 | **0** | 1,360 / 585 / 468 |
| Innovus b6 | 3,435 | 234,588 | **0** | 1,360 / 586 / 1,489 |

Reports: `drclvs/reports/<arm>_nwell4_nsc_check.txt`. This is the strongest statement available: on the real geometry
every n-well region, including the 1,489 Innovus islands, contains a licon on an n-tap.

## 6. Disposition per class

| Class | Verdict | Fix? |
|---|---|---|
| O1, I1, N1 (field / channel strips) | tool / abstract artefact | no layout change; PROPOSED waiver W1 |
| I2, N2 (channel strips cut by a SRAM edge) | same artefact; edge overlap 0.01 to 0.13 um is the cell n-well overhang | PROPOSED waiver W2 |
| O2, I3, N4 (left-pocket strips) | same artefact | PROPOSED waiver W3 |
| N3 (Innovus isolated tap wells) | same artefact, counted per island because the pocket is unfilled | PROPOSED waiver W4; no filler ECO (not a violation) |

No class is a real layout defect, so no ECO, no re-extraction and no StarRC -> PrimeTime re-run was needed.

## 7. PROPOSED waivers (needs user sign-off; nothing below is waived)

Common conditions (all must hold or the waiver is void):

- C1. Rule string exactly `All nwells must contain metal-connected N+ taps (nwell.4)`, reported by Magic `drc(full)` in the
  sign-off mode of `scripts/magic/gds_abs_drc.tcl` (std cells = `sky130_fd_sc_hd` LEF abstracts, `SRAM_MODE=real`).
- C2. The item bounding box is not inside any SRAM footprint (zero such items exist), and any footprint overlap is
  at most 0.13 um.
- C3. `nwell4/nwell_nsc_check.py` on the same GDS reports `nwell_regions_without_nsc: total=0`.
- C4. The per-arm item count does not exceed the number stated below. A new item, or an item of any other rule outside
  the footprints, is not covered and re-opens the waiver.
- C5. Void if the Magic std-cell source is changed to the GDS (section 7.5): the expected count is then 0 and the
  waiver is not needed.

**W1 (PROPOSED, needs user sign-off): n-well strips of fill / decap / tap / logic rows, outside the footprints.**
Mechanism: LEF abstract n-well without tap contact (sections 2, 4). Match: C1-C5 and a bbox height of 0.30 to 2.84 um
and a width of 3 um or more, not within 0.13 um of a footprint. Count: OpenROAD 3,474, ICC2 3,035, Innovus 3,035.
Evidence: `drclvs/reports/<arm>_nwell4_items.txt.gz`, `nwell4_ab_windows.tsv`, `<arm>_nwell4_nsc_check.txt`.

**W2 (PROPOSED, needs user sign-off): n-well strips whose end overlaps a SRAM footprint by 0.13 um or less.**
Mechanism: as W1 plus the 0.19 um n-well overhang of the last abutting cell. Match: C1-C5 and a footprint overlap of
0.01 to 0.13 um, height 2.84 um or less, width 3 um or more, x or y within 0.13 um of a footprint edge in the channel
(y 417.5..520). Count: ICC2 444, Innovus 444, OpenROAD 0.

**W3 (PROPOSED, needs user sign-off): left-pocket n-well strips (x <= 100.01 um, y <= 921 um), width 3 um or more.**
Match: C1-C5 and the bbox inside x 20.05..100.01, y 20..921. Count: OpenROAD 152 (outside, ends at x=89.89), ICC2 148
(straddle, ends at x=100.01), Innovus 1 (straddle).

**W4 (PROPOSED, needs user sign-off): Innovus isolated tap-cell wells in the unfilled left pocket.**
Mechanism: as W1; each tap cell's well is a separate island because the pocket carries no filler. Match: C1-C5,
width under 3 um, bbox inside x 20.05..112 um, y 20..921 um. Count: Innovus 1,483 (1,191 outside + 292 straddling, of
which 1,464 lie in the pocket and 19 in the adjoining channel). ICC2 and OpenROAD: 0.

Sum per arm: OpenROAD 3,626 (W1 3,474 + W3 152); ICC2 3,627 (W1 3,035 + W2 444 + W3 148); Innovus 4,963 (W1 3,035 +
W2 444 + W3 1 + W4 1,483).

### 7.5 Alternative that removes the artefact instead of waiving it (not run, user decision)

Run the sign-off Magic with the std cells taken from the layout GDS (`magic_drc_variant.tcl`, `STD=gds`) for the full
die. The windows show 0 `nwell.4`. Cost: one Magic run of about 25 min per arm at the current 9 to 11 GB peak
(unmeasured for GDS std cells; `GUARD_RSS_GB=11`), and a new baseline for every other rule outside the SRAMs, since the
std cell internals would then be checked too (the clipped runs show this is not neutral: the LEF mode adds
`LU.2`/`LU.3`, "Can't overlap those layers" and `met1.7` items that the GDS mode does not, see `nwell4_ab_windows.tsv`).
Not run because it changes the sign-off deck mode for all arms.

## 8. Reproduction (all from the repo root; Magic/KLayout in the LibreLane container, one tool at a time)

```
# full-die independent check (about 11 min per arm)
bash pnr/commercial/signoff/drclvs/nwell4/chain_kl.sh
# window A/B (clip + two Magic runs per arm and window; 60 s between jobs)
bash pnr/commercial/signoff/drclvs/nwell4/chain_magic_ab.sh
python3 -I pnr/commercial/signoff/drclvs/nwell4/ab_summary.py pnr/commercial/signoff/drclvs/nwell4/out
```

The Magic nwell.4 item lists were extracted by streaming the 1.1 GB reports with awk (rule block only). Runs of this
task: KLayout nsc check 3 x ~11 to 15 min; Magic A/B 18 runs (3 arms x 3 windows x 2 modes) plus 9 clips, each about 1 to 3 min.
The first A/B attempt clipped without the child cells (`add_this_cell`); it was discarded and rerun with `add_cell`.
A first hand-built Magic test row (cells placed with `getcell`) placed no cell and reported 0 in both modes; it is
not evidence and was deleted.

## 9. Limits

- A/B is by window (pocket, channel, one logic tile column per arm), not a full-die GDS-std Magic run.
- The straddle penetration cause (section 3.2) is INFERRED.
- The LEF-vs-GDS differences in other rules (`LU.2`, `LU.3`, `met1.7`) in the clipped runs are not analysed.
- The independent check uses the GDS the DRC used; the n-tap definition (`licon1 & tap & nsdm`) is the Magic `nsc` as
  best read from the tech file, not an executed copy of the Magic CIF operation.
