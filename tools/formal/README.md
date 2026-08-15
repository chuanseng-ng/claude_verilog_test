# `tools/formal` — EQY sv2v-vs-RTL equivalence (bead `claude_verilog_test-q7n`)

Phase 5 M11/M12 ASAP7 SoC synthesis does not run on the source RTL: Synlig
cannot synthesise this SoC's SystemVerilog, so `pnr/Makefile` runs `sv2v`
first and Yosys consumes `pnr/asap7/soc/soc_top_sv2v.v`. Until this bead,
correctness of that conversion rested entirely on the cocotb `soc_all` suite
passing against the *original* RTL — there was no formal equivalence between
the sv2v output and the source. This directory adds a committed, re-runnable
Yosys EQY harness that compares individual modules, gold (SystemVerilog RTL)
vs gate (the module's block extracted from the actual netlist that gets
synthesised).

## Re-running

```bash
tools/formal/run_eqy.sh --tier 1          # or --tier 2, --tier 3, --all
make -C tools/formal eqy-tier1            # equivalent Makefile targets
```

`run_eqy.sh` wraps everything in one `nix develop ~/Downloads/Github/librelane
--command ...` session (eqy/yosys/sby are only on that devshell's PATH, not
this repo's own `flake.nix`), so the devshell startup cost is paid once per
invocation regardless of how many modules are requested. Add `--json-out
<path>` to also write the aggregate JSON summary to disk.

Files:
- `modules.json` — the registry: which modules are checked (tier, gold source
  files, defines, netlist module names to extract) and which are known-blocked
  (with the specific parser error and an isolated repro, so nobody re-litigates
  the same dead end).
- `run_eqy.py` — extracts each module from the flat sv2v netlist, generates a
  `.eqy` config, runs `eqy`, and parses the result into a compact JSON verdict
  with a real exit code (0 PASS / 1 FAIL / 2 ERROR / 3 no modules matched),
  following the same discipline as `tools/eda/summarize.py`.
- `fixtures/icg_stub.v` — blackbox declaration for `ICGx1_ASAP7_75t_R` (see
  Tier 1 below).

## Verdict discipline (bead `dwp`)

A tool exiting 0 with an empty or unparsable report must never read as PASS.
`run_eqy.py`'s `parse_verdict()` treats eqy's own `DONE (PASS...)` as
**necessary but not sufficient**: it also requires the workdir's `matched.ids`
to be non-empty and the `PASS` marker file to exist, or it downgrades the
result to `ERROR` with an explicit reason. eqy's own exit codes were verified
empirically (not assumed) against this Yosys 0.46 build: `0` on `DONE
(PASS...)`, `2` on `DONE (FAIL...)`, `1` on a setup/read failure before any
partition is attempted (no `matched.ids` ever written).

**The harness's real discriminating power was verified, not assumed.** Two
negative controls were run against `cdc_2ff_sync` before trusting any PASS
result:
1. Corrupting the shift-chain data path (`sync_q[i] <= sync_q[i]` instead of
   `sync_q[i - 1]`) → eqy correctly reported `DONE (FAIL, rc=2)`, pinpointing
   exactly `cdc_2ff_sync.sync_q.1` as the failed partition.
2. Corrupting the async-reset constant (`1'sb0` → `1'sb1`) → **eqy did NOT
   catch this.** This is not a harness bug — it is eqy's default `sat`
   strategy's documented scope: `formalff -ff2anyinit` treats the gate side's
   register initial value as free/unconstrained for the induction proof, so
   the proof establishes "once gold and gate converge to the same state, they
   stay equivalent forever," not "both sides reset to the same value." This
   matches standard gate-level LEC methodology (most commercial LEC tools
   treat reset-value fidelity as a separate check, not part of the main
   combinational-equivalence sweep). **Scope statement:** these EQY runs do
   *not* independently prove reset-value fidelity. sv2v is a lexical/structural
   lowering (not an optimising synthesis), so reset literals were additionally
   confirmed unchanged by direct textual diff between gold and gate for every
   module actually run (see each module's extracted `gate_*.v` — reset
   constants are visually identical to the source).

## What is proven (Tiers 1–3, all via the committed script, all reproduced twice)

| Tier | Module | Status | Matched points | Partitions proved | Runtime |
| --- | --- | --- | --- | --- | --- |
| 1 | `rv32i_clock_gate` | **PASS** | 8 | 1 (whole module, combinational) | 0.3 s |
| 2 | `cdc_2ff_sync` | **PASS** | 6 | 3 (`q_o`, `sync_q.0`, `sync_q.1`) | 0.5 s |
| 3 | `async_axi_fifo` (hierarchical: + `cdc_2ff_sync`, `cdc_reset_sync`, `cdc_gray_fifo`) | **PASS** | 286 | 476 | ~31 s |

- **Tier 1** (`rv32i_clock_gate`, 29 lines): trivial leaf, directly gated by
  `USE_ICG_CELL` (one of the two live `SOC_SV2V_DEFINES`). Under
  `__pnr__+USE_ICG_CELL` it instantiates the ASAP7 `ICGx1` liberty cell;
  `fixtures/icg_stub.v` blackboxes it identically on both sides, so the proof
  is a structural/connectivity check ("does gold's `u_icg` instance connect
  the same way gate's does") — it does not and cannot say anything about the
  liberty cell's internal behaviour (out of scope for this bead; that's an STA
  concern, not a conversion-equivalence one).
- **Tier 2** (`cdc_2ff_sync`, 105 lines): sequential leaf, the base CDC
  synchroniser primitive. Checked at the instantiation defaults
  (`WIDTH=1`/`STAGES=2`); other widths used elsewhere in the design are not
  separately re-checked by this harness.
- **Tier 3** (`async_axi_fifo` + its 3 CDC submodules, 334+201+130+105 = 770
  lines total): the full dual-clock AXI4 CDC bridge — per CLAUDE.md, the
  single most safety-critical CDC structure in this SoC (GH #91/#93/#96). A
  genuine 4-module hierarchy, gray-code pointer synchronisation across clock
  domains, per-channel FIFO storage arrays. This is the highest-value proof in
  the set: it directly covers the exact structure that GH #93 found two real
  RTL bugs in (a reset-polarity bug and a `wr_ready_o` reset-gating bug), both
  fixed and now formally shown structurally equivalent between RTL and the
  netlist that actually gets synthesised.

**This is the strongest achievable result given a hard frontend constraint**
(see below): the modules actually checkable with this toolchain happen to
include the design's most safety-critical CDC path, not just arbitrary leaves.

## Yosys 0.46's native `-sv` frontend: a real, confirmed limitation

Per the task's tooling directive, only `eqy`/`yosys`/`sby`/`smtbmc` from the
librelane nix devshell were used — no new equivalence checker or SV frontend
was sourced. Within that constraint, **Yosys 0.46's built-in `read_verilog
-sv` cannot parse two constructs used throughout `rtl/soc/*.sv`**, confirmed
with isolated 7-line repros (not just observed as a side effect on the real
files):

1. **`import pkg::*;` (wildcard package import), in any position.** A minimal
   synthetic module doing nothing but `import foo_pkg::*; assign o = WIDTH;`
   fails: `unexpected TOK_PACKAGESEP, expecting '(' or '['`. Note **scope
   resolution without import (`pkg::CONST`) works fine** — confirmed with the
   same kind of isolated repro — which is why Tier 3's `async_axi_fifo` (whose
   parameters use `axi_pkg::AXI_ADDR_WIDTH` scope resolution, "no file-scope
   import" by the design team's own choice, per its header comment) was
   checkable at all.
2. **Unpacked-array parameters** (`parameter logic [31:0] NAME [N]`) and
   **packed 2-D array parameters** (`parameter logic [N-1:0][31:0] NAME`) both
   fail to parse (`unexpected '['...`), confirmed with an isolated
   `parameter logic [31:0] X[2]` repro.

Modules blocked by these (full list + exact errors in `modules.json`
`blocked_modules`): `dma_engine` (the only packed-struct-as-memory module in
the whole SoC — the single highest-value target lost to this), `axi4_crossbar`
(packed-2D-array params, chosen deliberately by the design team to *avoid* a
different Synlig issue, but still unreadable by plain Yosys `-sv`),
`axi_lite_register_bank`, `apb4_register_bank`, `axil_to_apb` (unpacked-array
params or wildcard import), `boot_rom` (2 package imports, not attempted once
the limitation was confirmed structural).

## The `__pnr__`-guarded files: handled explicitly, not silently ignored

Per the task brief, `__pnr__` deliberately changes `rtl/soc/boot_rom.sv` (ROM
preload) and strips the non-synthesizable param-check `initial`/`$fatal`
blocks from `axi_lite_register_bank.sv`, `apb4_register_bank.sv`, and
`axil_to_apb.sv` (PR #152 / GH #116 item C). **All four of those files are in
the blocked set above** — none could be run through EQY. Two things were done
instead of silently ignoring this:

1. **Textual/manual verification (not a formal proof, clearly labelled as
   such):** `grep -c '\$fatal\|readmemh' pnr/asap7/soc/soc_top_sv2v.v` returns
   **0** — the gate netlist contains neither construct anywhere, confirming
   `__pnr__` was in effect for the actual conversion that produced the netlist
   this bead is checking against. Each source file's `` `ifndef __pnr__ ``
   guard was read directly (`apb4_register_bank.sv:57-62`,
   `axil_to_apb.sv:88` region, `axi_lite_register_bank.sv`, `boot_rom.sv:37,102`)
   and confirmed to gate exactly the constructs absent from the gate netlist.
2. Every EQY run that *was* possible always passes `__pnr__` (and
   `USE_ICG_CELL`) on the gold side via `modules.json`'s `defines`, matching
   `SOC_SV2V_DEFINES` in `pnr/Makefile` exactly — none of the checked tiers
   happen to be affected by `__pnr__` themselves (rv32i_clock_gate,
   cdc_2ff_sync, async_axi_fifo hierarchy have no `` `ifdef __pnr__ `` of their
   own), so this is a defines-hygiene guarantee, not a substitute for actually
   proving the three blocked files.

This is real, disclosed residual risk: **the three param-check-block files and
the boot ROM's `__pnr__` branch are verified by direct reading and grep, not
by formal equivalence.** They are good candidates to revisit if a working SV
frontend (Synlig `synlig-sv.so` is present in the librelane nix closure but
was not reachable from the devshell's `yosys` binary without additional
plugin-path engineering that was judged out of scope for this bead — see
`modules.json` `blocked_modules` for the exact failure mode if someone wants
to pick this up) becomes available.

## Known environmental blocker hit during this work

The host filesystem (`/dev/sdb2`, 117 GB) was measured at **111 GB used / 38
MB free (100%)** partway through this bead's work — unrelated to this task
(this harness's own scratch usage was ~72 MB total, already cleaned up; the
other ~111 GB is other sessions'/worktrees' data on a shared host, not touched
per instructions). All three tiers above completed and were reproduced
*before* the disk filled. A subsequent clean re-run of the full `--all` set
was attempted for final verification and Tier 3 failed mid-partition-write
with `No space left on device` (after already writing 285/286 matched points
— consistent with the successful run, just interrupted by the environment, not
a logic failure). **Tiers 1 and 2 were confirmed complete and PASS via the
final committed script twice.** Tier 3's numbers above are from the last fully
completed run (config byte-identical to what `modules.json` now generates);
re-running `make -C tools/formal eqy-tier3` once host disk space is available
is recommended to get a third, fully clean confirmation from the committed
script end-to-end — this is a documented follow-up, not a gap in the proof
technique itself.

## What is and is NOT proven, restated plainly

**Proven:** `rv32i_clock_gate`, `cdc_2ff_sync`, and the `async_axi_fifo` +
`cdc_2ff_sync` + `cdc_reset_sync` + `cdc_gray_fifo` hierarchy (the dual-clock
AXI4 CDC bridge) are logically equivalent between the source SystemVerilog and
the exact netlist module blocks that ASAP7 SoC synthesis consumes, at the
instantiated default parameterisations, up to the scope limits stated above
(no independent reset-value check by the SAT proof; compensated by textual
diff).

**NOT proven:** every other module in `SOC_SV_FILES` — in particular the
entire AXI4/AXI-Lite fabric layer (`axi4_crossbar`, `axi_lite_interconnect`,
`axi4_to_axilite`, `axilite_to_axi4`, `axil_to_apb`, `apb_interconnect`,
`soc_bus`), the register banks, `dma_engine`, `sram_controller`, `boot_rom`,
and all the peripherals (`uart_controller`, `spi_controller`, `timer`,
`interrupt_controller`) — none of these were run through EQY. Most either use
`import pkg::*` or array-shaped parameters and are blocked by the Yosys `-sv`
frontend limitation above; several were simply not attempted once the pattern
was confirmed structural rather than file-specific, to avoid spending further
effort on runs known to fail the same way.

## sv2v conversion bugs found

**None.** Every module that could be run through EQY (Tiers 1–3, 4 distinct
netlist modules total) proved logically equivalent to its source RTL on the
first attempt with no RTL or netlist changes required.

## Recommendation on bead `claude_verilog_test-q7n`

**Stays open.** Real, reproducible formal equivalence now exists for 4 of the
~28 modules in the sv2v-converted netlist — including, not incidentally, the
design's most safety-critical CDC structure — which is a genuine improvement
over "cocotb only" for that subset. But the majority of `SOC_SV_FILES`,
including the entire bus fabric and all four `__pnr__`-affected files, remains
unverified by formal equivalence, blocked by a confirmed Yosys `-sv` frontend
limitation rather than by RTL/netlist defects. Closing q7n on this subset
would overstate what has actually been shown. Suggested next step if someone
picks this up: get a working SystemVerilog frontend (Synlig, already present
in the librelane nix closure per this investigation, or a newer Yosys) wired
into the devshell's `yosys` binary, which per this investigation's isolated
repros would very plausibly unblock most of the `blocked_modules` list without
requiring any change to the gold RTL.
