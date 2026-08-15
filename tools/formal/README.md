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
tools/formal/run_eqy.sh --tier 1            # or --tier 2 .. --tier 5, --all
tools/formal/run_eqy.sh --negative-control --module axil_to_apb
make -C tools/formal eqy-tier1              # equivalent Makefile targets
make -C tools/formal eqy-negative-control
```

`run_eqy.sh` wraps everything in one `nix develop ~/Downloads/Github/librelane
--command ...` session (eqy/yosys/sby are only on that devshell's PATH, not
this repo's own `flake.nix`), so the devshell startup cost is paid once per
invocation regardless of how many modules are requested. Add `--json-out
<path>` and `--workdir-root <dir>` to control where results and scratch land
(keep scratch off the root filesystem — see "Known environmental blocker").

Files:
- `modules.json` — the registry: which modules are checked (tier, gold source
  files, defines, netlist module names to extract, recorded baselines,
  declared negative-control mutations) and which are known-blocked (with the
  specific tool error and an isolated repro, so nobody re-litigates the same
  dead end).
- `run_eqy.py` — extracts each module from the flat sv2v netlist, generates a
  `.eqy` config, runs `eqy`, and parses the result into a compact JSON verdict
  with a real exit code (0 PASS / 1 FAIL / 2 ERROR / 3 no modules matched),
  following the same discipline as `tools/eda/summarize.py`.
- `fixtures/icg_stub.v` — blackbox declaration for `ICGx1_ASAP7_75t_R` (see
  Tier 1 below).

## Two gold-side frontends

| frontend | how gold is read | why |
| --- | --- | --- |
| `yosys-sv` (tiers 1–3) | Yosys 0.46 `read_verilog -sv`, defines as `-D NAME` | native, no plugin |
| `synlig` (tiers 4–5) | Surelog/UHDM `read_systemverilog`, defines as `-DNAME` (glued) | parses `import pkg::*` and array-typed parameters, which `-sv` cannot |

The Synlig plugin's absolute `/nix/store` path is resolved at **runtime** by
`resolve_synlig_plugin()` (glob, never hardcoded — the hash moves whenever
librelane's flake input moves). If it cannot be found the script fails loudly
rather than silently falling back to `yosys-sv`, which would under-report
blocked modules relative to reality.

## Verdict discipline (bead `dwp`)

A tool exiting 0 with an empty or unparsable report must never read as PASS.
`parse_verdict()` treats eqy's own `DONE (PASS...)` as **necessary but not
sufficient**. Two guards sit on top of it:

1. **Empty-match guard** (original): `matched.ids` must be non-empty and the
   `PASS` marker file must exist, or the result is downgraded to `ERROR`.
   eqy's own exit codes were verified empirically against this Yosys 0.46
   build: `0` on `DONE (PASS...)`, `2` on `DONE (FAIL...)`, `1` on a
   setup/read failure before any partition is attempted.
2. **Zero-partition guard** (added 2026-08-15): a PASS that generated **no
   partitions at all** is downgraded to `ERROR`. eqy will print `Successfully
   proved designs equivalent` / `DONE (PASS, rc=0)` with an entirely empty
   `partitions/` directory — the match set is non-empty (names lined up) but
   not one proof obligation was ever created. This is not hypothetical: it is
   what **Tier 1's `rv32i_clock_gate` "PASS" actually was**, and the guard was
   written because of it.
3. **Match-set-drift guard** (added 2026-08-15, and it was needed — see
   below): a PASS whose matched-point or partition count is *below* the
   module's recorded `baseline_matched_points` / `baseline_partitions` is
   downgraded to `ERROR`. A PASS over a shrunken match set proves strictly
   less than the recorded proof and must not be reported as the same result.

## Negative controls — the harness is shown to fail

Every declared negative control lives in `modules.json` (`negative_control`:
file, exactly-once `find`/`replace`, and a note). `--negative-control` injects
the mutation into a **gold-only in-memory copy** and **inverts the verdict**:
the control passes only if eqy either FAILs a partition or the drift guard
refuses to certify. A setup/read `ERROR` never counts as a catch — a tool
falling over is not a tool detecting anything. Modules with no declared
mutation report `SKIP`, never `PASS`.

| module | frontend | injected mutation | result |
| --- | --- | --- | --- |
| `cdc_2ff_sync` | yosys-sv | invert the combinational output `q_o` | caught (FAIL on `cdc_2ff_sync.q_o`) |
| `async_axi_fifo` | yosys-sv | corrupt the binary→gray encoding (`>>1` → `>>2`) of the write pointer | caught (FAIL on `wr_gray_d` in **all five** channel FIFOs) |
| `axil_to_apb` | **synlig** | swap the write/read response states out of `S_ACCESS` | caught (FAIL on `axil_to_apb.state_d`) |
| `boot_rom` | **synlig** | corrupt the INCR burst stride from 4 to 8 bytes | caught (FAIL on `boot_rom.r_addr_q`) |

`rv32i_clock_gate` has **no** negative control and reports `SKIP`: its
unmutated baseline is already `ERROR` (zero partitions — see below), so there
is nothing for a mutation to break. Two were tried anyway and neither counted:
tying `ENA` to `1'b1` was reported `DONE (PASS)`, and swapping `CLK`/`ENA`
broke eqy's matcher (`conflicting matches for gold bit \clk: \clk vs \en`).

**The Synlig frontend is covered by its own controls** (`axil_to_apb`,
`boot_rom`). The pre-existing `-sv`-frontend control did not transfer: a
different frontend can fail differently, and tiers 4–5's PASS results are only
worth anything because the Synlig path was shown to catch a deliberate
corruption.

### What the first round of controls exposed (a real harness hole)

The first three mutations tried were **signal-deleting**, and two of them were
reported `PASS`:

| mutation | effect on the match set | eqy verdict |
| --- | --- | --- |
| `rv32i_clock_gate`: tie `ENA` to `1'b1` | 8 → 8 points, 0 → 0 partitions | `DONE (PASS)` — but so does the *unmutated* baseline; see the zero-partition guard |
| `cdc_2ff_sync`: `sync_q[i] <= d_i` (collapse the 2-FF chain) | **6 → 5 points, 3 → 2 partitions** | `DONE (PASS)` |
| `async_axi_fifo`: re-introduce commit `7a9f9d4`'s `wr_ready_o` bug | matcher broke | `ERROR: conflicting matches for gold bit \wr_clk_i` |

This is bead `dwp`'s failure shape one level up: the report is not *empty*, it
just silently *covers less*. The `cdc_2ff_sync` case is closed two ways — the
drift guard above, and by replacing the mutation with a signal-preserving one
(all rejected mutations are kept in `modules.json` under `design_note` so
nobody re-invents them). The `rv32i_clock_gate` case turned out to be
something worse: chasing it is how the zero-partition guard was found, because
that module's *unmutated* run also proves nothing. The third case is a separate lesson: a mutation that changes the
design's signal set can break eqy's matcher instead of testing the prover, and
a matcher `ERROR` is not a detection.

### A false PASS that eqy's default strategy does not catch

The most important result of this round. On `cdc_2ff_sync`, the mutation

```systemverilog
sync_q[0] <= ~d_i;    // instead of  sync_q[0] <= d_i;
```

is **signal-preserving** (full 6-point / 3-partition match set, so the drift
guard sees nothing) and is **provably present in the gold netlist** — the
generated `gold.il` contains

```
cell $not $not$...gold_patched_cdc_2ff_sync.sv:96$11
  connect \A \d_i
  connect \Y $0\sync_q[0][0:0]
```

against a gate side that wires `\d_i` straight to the flop's `D`. eqy proved
all three partitions and reported `DONE (PASS, rc=0)`.

**Probable mechanism** (mechanism inferred, the failure itself measured): the
miter eqy generates compares gold against gate with

```verilog
okay = okay && (in_gold[i] === 1'bx || in_gold[i] === in_gate[i]);
```

— **a gold-side `x` is accepted unconditionally** — while `formalff -clk2ff
-ff2anyinit` and `setundef -anyseq` are applied to the **gate module only**.
Any gold register that is `x` in the states the prover reaches makes its
partition's assertion vacuous.

**Where the boundary appears to lie**, from the five controls actually run:

| corruption shape | caught? |
| --- | --- |
| combinational module output inverted (`q_o`) | ✅ |
| FF with self-feedback (`r_addr_q + 4` → `+ 8`; `wr_gray_d` `>>1` → `>>2`; `state_d` swap) | ✅ |
| FF with **no** feedback, D driven straight from a primary input (`sync_q[0] <= ~d_i`) | ❌ **false PASS** |
| blackbox cell pin constant (`SE` 0 → 1) | ❌ — but moot: this module produces no partitions at all |
| async-reset constant (`1'sb0` → `1'sb1`, previously recorded) | ❌ |

This generalises the reset-value caveat that was already in this README: it is
not just *init* values that the default `sat` strategy under-checks. **Read
every PASS in the table below as "no counterexample was found by eqy's default
strategy", not as "these two descriptions are equivalent."** Tightening it
would mean a custom strategy (`ASSUME_DEFINED_INPUTS`, or a miter that does
not exempt gold `x`), which is follow-up work, not something this bead closes.

## What is proven

| Tier | Module | Frontend | Status | Matched pts | Partitions | Runtime |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `rv32i_clock_gate` | yosys-sv | **ERROR — vacuous** | 8 | **0** | 0.3 s |
| 2 | `cdc_2ff_sync` | yosys-sv | **PASS** | 6 | 3 | 0.5 s |
| 3 | `async_axi_fifo` + `cdc_2ff_sync` + `cdc_reset_sync` + `cdc_gray_fifo` | yosys-sv | **PASS** | 285 | 476 | 29.5 s |
| 4 | `axil_to_apb` | synlig | **PASS** | 41 | 122 | 8.7 s |
| 4 | `boot_rom` | synlig | **PASS** | 41 | 36 | 4.5 s |
| 4 | `axi_lite_register_bank` | synlig | FAIL (expected, root-caused) | 38 | 574 proved / 2 failed | — |
| 4 | `apb4_register_bank` | synlig | FAIL (expected, root-caused) | 17 | 525 proved / 2 failed | — |
| 4 | `dma_engine` | synlig | ERROR (known limitation, 3 blockers peeled, 4th remains) | 382 | — | — |

Tier-3's matched-point count is **285**, not the 286 previously recorded here:
`matched.ids` has 286 lines, one of which is the `# [*] gold-match *` comment
header that `run_eqy.py` correctly filters out. The 2026-08-15 clean re-run on
a healthy filesystem reproduced 285 points / 476 partitions / PASS exactly.

- **Tier 1** (`rv32i_clock_gate`) — **re-assessed 2026-08-15: its PASS was
  vacuous and it is now reported as ERROR.** eqy matches 8 points (3 ports,
  the `u_icg` cell, its 4 pins) and then declares the designs equivalent
  having generated **zero partitions** — `partitions/` is empty, no proof
  obligation was ever created. The previously recorded "1 partition (whole
  module, combinational)" was wrong. With the liberty cell blackboxed there is
  no logic left for the prover, so formal equivalence adds nothing here over
  reading the 29 lines. The entry is kept in the registry as an
  `expected_status: ERROR` so this stays visible rather than being quietly
  dropped.
- **Tier 2** (`cdc_2ff_sync`): the base CDC synchroniser primitive, at the
  instantiation defaults (`WIDTH=1`/`STAGES=2`). Other widths used elsewhere
  are not separately re-checked.
- **Tier 3** (`async_axi_fifo` + its 3 CDC submodules, 770 lines): the full
  dual-clock AXI4 CDC bridge — per CLAUDE.md the single most safety-critical
  CDC structure in this SoC (GH #91/#93/#96), and the exact structure GH #93
  found two real RTL bugs in.
- **Tier 4** adds the Synlig frontend and with it the two `__pnr__`-guarded
  files that were previously verified only by reading: `axil_to_apb` (whose
  param-check `initial`/`$fatal` block `__pnr__` strips) and `boot_rom` (whose
  `MEM_INIT_FILE` becomes `int unsigned` and whose `$readmemh` preload branch
  is dropped). Both are now genuinely proven, with `-D__pnr__` on the gold
  side matching `SOC_SV2V_DEFINES` in `pnr/Makefile` exactly — apples to
  apples, not a masked mismatch.

## Tier-4 register-bank FAIL — root cause

`axi_lite_register_bank` and `apb4_register_bank` FAIL on exactly two
partitions each: `regs`, plus the read-data register (`rdata_q` / `prdata`).
Everything else proves (574 and 525 partitions respectively).

**It is neither of the two things it most looks like.** It is **not** a
gold-side defines mismatch — both files carry `-DUSE_ICG_CELL -D__pnr__` on
the gold side, matching `SOC_SV2V_DEFINES`, so the `$fatal` param-check block
is absent from both sides. And it is **not** an sv2v conversion defect: sv2v's
output is provably self-consistent (evidence below).

It is also **not** an eqy init-handling artifact, even though gold's
`RESET_VAL` really does elaborate to garbage. The distinction matters: the bad
value is produced by the *frontend*, before eqy sees the design, and eqy's
`formalff -ff2anyinit` neither creates nor masks it — the `_n1_constfold`
diagnostic below repairs only the value, changes nothing about the strategy,
and turns FAIL into PASS. (Consistency check on the other direction: eqy's
miter exempts gold-side `x`, so a *fully* undefined gold `regs` would have
passed vacuously. It fails because the corruption is partial — `WMASK` is all
`x` but `(regs & ~m) | (pwdata & m)` still yields defined bits wherever `regs`
and `pwdata` agree, and those defined bits differ.)

It is **two independent gold-side (Synlig) artifacts stacked**, each isolated
by a tier-5 diagnostic:

| Tier-5 entry | N_REGS | array params | result | failed partitions |
| --- | --- | --- | --- | --- |
| `axi_lite_register_bank_n1` | 1 | as written | FAIL | `regs` (95 proved) |
| `axi_lite_register_bank_n1_constfold` | 1 | constant-folded | **PASS** | — (96 proved) |
| `axi_lite_register_bank_n2` | 2 | as written | FAIL | `regs`, `rdata_q` (126 proved) |
| `apb4_register_bank_n1` | 1 | as written | FAIL | `regs` (46 proved) |
| `apb4_register_bank_n1_constfold` | 1 | constant-folded | **PASS** | — (47 proved) |
| `apb4_register_bank_n2` | 2 | as written | FAIL | `regs`, `prdata` (77 proved) |

### Cause A — unpacked-array **port** flattening order (the `rdata_q`/`prdata` failure)

sv2v and Synlig lower an unpacked-array module port to a packed vector in
**opposite element orders**:

```
gate (sv2v)    regs[((N_REGS - 1) - r) * 32 +: 32]      element 0 at the MSB end
gold (Synlig)  regs[r * 32 +: 32]                       element 0 at the LSB end
```

Verified directly by dumping both elaborations: gold's `hw_wen_i[0]` gates
`hw_wdata_i[31:0] → regs[31:0]`, gate's `hw_wen_i[0]` gates
`hw_wdata_i[511:480] → regs[511:480]`. (For arrays of *scalars* the two agree
— both emit `[0:N-1]` — so the disagreement is specific to arrays of vectors,
which makes Synlig internally inconsistent between the two shapes.)

The `_n1` / `_n2` pair proves this is the cause of the read-path failure:
at `N_REGS=1` the reversal `(N_REGS-1)-r` **is the identity**, and the
`rdata_q`/`prdata` partition proves; at `N_REGS=2` the reversal becomes a
swap — the smallest non-identity permutation — and it fails again.

### Cause B — unpacked-array **parameter** elaboration (the `regs` failure)

`regs` fails even at `N_REGS=1`, where cause A cannot apply. Synlig/Surelog
silently mis-elaborates unpacked-array-**typed** parameters. In
`apb4_register_bank`, `WMASK[]` reads back as `32'hxxxxxxxx` and `RESET_VAL[]`
as `32'b0000000000000000000000000000000x` — against gate's correct
`32'hffffffff` / `32'h00000000`. Minimal repro:

```systemverilog
parameter logic [31:0] PEXPL [2] = '{32'hAAAA_AAAA, 32'hBBBB_BBBB}  // → 32'b...0001x
parameter logic [31:0] PFILL [2] = '{default: '1}                    // → 32'b...0001x
parameter logic [31:0] PSCALAR   = 32'hCCCC_CCCC                     // → 32'hCCCCCCCC  ✓
```

Both array forms come back as the same garbage; the scalar is fine. The
`_n1_constfold` entries prove this is the whole of the residual failure: they
replace the two reads of `RESET_VAL[]`/`WMASK[]` with the exact default
constants those parameters carry — a semantic no-op at default parameters —
and both banks then **PASS**, with the failed partition count going to zero
and the proved count rising by exactly one (95→96, 46→47).

This is the silent member of the same family as the two crashing members
already in `blocked_modules`: **Yosys RTLIL cannot represent non-scalar
parameter types**, so Synlig's UHDM lowering either asserts (string parameters
— see `boot_rom.sv`'s own header comment; packed-2D-array parameters — see
`axi4_crossbar`) or, here, silently emits garbage.

### The deleted `synlig_array_fill_workaround`

An earlier (uncommitted) revision of `run_eqy.py` carried an
`apply_array_fill_workaround()` that rewrote `'{default: 'X}` parameter
defaults into an explicit positional literal, on the theory that only the
*fill-literal form* tripped Surelog. **That theory is false and the function
was a proven no-op.** Elaborating `rtl/soc/apb4_register_bank.sv` through
Synlig with and without the rewrite produces **byte-identical**
`write_verilog` output, and the synthetic repro above shows the explicit
positional literal corrupts exactly as badly as the fill. It has been deleted
rather than left in place creating the impression that the X corruption had
been handled; the constant-fold diagnostic (which actually works, by removing
the array parameter *read* rather than restyling its *default*) replaces it.

### Why this is not an sv2v defect

sv2v's reversal is applied consistently to the module, its parameters, and
every instantiation. In the converted `pll_apb_regs`:

```
localparam [95:0] WMASK     = 96'h000003f0_00000000_00000000;   // element 0 at bits [95:64]
localparam [95:0] RESET_VAL = 96'h00000001_00000000_00000000;   // element 0 at bits [95:64]
assign hw_wdata[64+:32]  = ...;                                  // element 0
assign pll_enable_o      = regs_out[64];                         // == RTL regs_out[0][0]
assign feedback_div_o    = regs_out[71-:4];                      // == RTL regs_out[0][7:4]
```

— which matches `rtl/soc/pll/pll_apb_regs.sv` element for element. The packed
encoding of an unpacked array port is not defined by the LRM; it only has to
be self-consistent across the whole conversion, and sv2v's is. **No sv2v
conversion bug is implied by these FAILs.**

### Consequence

The two register banks are **not provable at module scope with this
sv2v + Synlig pairing**, for tool reasons on the gold side. Their `regs` and
read-data partitions are unverified; the other ~1 100 partitions across the
two modules did prove. `dma_engine` inherits cause A through its `u_regbank`
instance (N_REGS=8, driven through `regs_o`/`hw_wen_i`/`hw_wdata_i`).

## `dma_engine`

The 2026-08-15 `read_gate` ERROR was a **harness extraction gap, not a
mismatch**, exactly as suspected: `gate_modules` pulled only `dma_engine` out
of the flat netlist and left its `u_regbank` submodule behind, so gate had a
dangling reference. That is fixed here the way Tier 3's hierarchical entry
already did it — the submodule is named in `gate_modules` and its RTL added to
`gold_files`. `dma_engine` is still **not provable**, but for successively
different reasons, all recorded verbatim in `modules.json`:

| after fixing | new error |
| --- | --- |
| — (original) | `read_gate: Module \axi_lite_register_bank referenced in module \dma_engine in cell \u_regbank is not part of the design.` |
| submodule pulled in | `partition: ERROR: Can't find cell q_mem in gold circuit.` — the `desc_t q_mem[QDEPTH]` packed-struct queue is inferred as a `$mem` by the gate side but not by Synlig |
| `post_prep_both: ["memory_map"]` (applied **identically** to both sides) | `partition: ERROR: conflicting matches for gold bit \hw_wen_i [3]: \hw_wen_i [3] vs 1'1` — the `u_regbank` unpacked-array port boundary again |

Matched points went 0 → 128 → 382 across those three, so each fix was real
progress; the residual is the same register-bank port family documented above.
`expected_status` is `ERROR`, recorded as a known limitation — not skipped, and
not reported as a design defect.

## Yosys 0.46's native `-sv` frontend: a real, confirmed limitation

**Yosys 0.46's built-in `read_verilog -sv` cannot parse two constructs used
throughout `rtl/soc/*.sv`**, confirmed with isolated repros (not just observed
as a side effect on the real files):

1. **`import pkg::*;` (wildcard package import), in any position** —
   `unexpected TOK_PACKAGESEP, expecting '(' or '['`. Scope resolution without
   import (`pkg::CONST`) works fine, which is why Tier 3's `async_axi_fifo`
   was checkable at all.
2. **Unpacked-array parameters** (`parameter logic [31:0] NAME [N]`) and
   **packed 2-D array parameters** (`parameter logic [N-1:0][31:0] NAME`) both
   fail to parse (`unexpected '['...`). It also cannot parse unpacked-array
   *ports* in an ANSI header at all (`output logic [31:0] o [0:2]` →
   `syntax error, unexpected '['`).

**Synlig removes blocker 1 entirely and blocker 2's parse**, which is what
unblocked tier 4. It does not remove blocker 2's *semantics* — see cause B
above.

## Blocked-module status (all originally-blocked modules re-tested 2026-08-15)

| module | original blocker | Synlig parses? | current status |
| --- | --- | --- | --- |
| `axil_to_apb` | in-body `import axi_pkg::*` | ✅ yes | **PASS** (tier 4) |
| `boot_rom` | 2 package imports | ✅ yes | **PASS** (tier 4) |
| `dma_engine` | `import axi_pkg::*` in ANSI-header position | ✅ yes | **ERROR** — extraction gap fixed; now blocked by `$mem` inference + the `u_regbank` port boundary (see above) |
| `axi_lite_register_bank` | unpacked-array params | ✅ parses | **FAIL** — causes A+B above; not provable at module scope |
| `apb4_register_bank` | unpacked-array params | ✅ parses | **FAIL** — causes A+B above; not provable at module scope |
| `axi4_crossbar` | packed-2D-array params + `import` | parses (Surelog: 0 errors) but UHDM→RTLIL **crashes** | **STILL BLOCKED** — `ERROR: Assert `!wire->name.empty()' failed in kernel/rtlil.cc:2150` |

`axi4_crossbar` remains blocked with no workaround: the crash is triggered by
the packed-2D-array parameter *type declaration* itself, and there is no
source-level rewrite that avoids declaring `SLV_BASE`/`SLV_LIMIT` that way
without changing what they mean to the routing logic. The register banks turn
out to be the *silent* member of the same family rather than a different bug
— Surelog does not corrupt the fill *expression*, it mis-lowers the
unpacked-array parameter *type*, and an explicit positional literal is
corrupted identically.

Modules never attempted, and still not attempted (no frontend blocker known,
just not in scope for this bead): `axi_lite_interconnect`, `axi4_to_axilite`,
`axilite_to_axi4`, `apb_interconnect`, `soc_bus`, `sram_controller`,
`uart_controller`, `spi_controller`, `timer`, `interrupt_controller`, `pmu`,
`pll_*`, `soc_top`.

## Scope limits that survive this round

- **eqy's default `sat` strategy has a demonstrated false-PASS class** — see
  "A false PASS that eqy's default strategy does not catch" above. This
  subsumes the reset-value caveat previously recorded here (a corrupted
  async-reset constant `1'sb0` → `1'sb1` was not caught) and extends it to at
  least one non-reset case (an inverted D input on a feedback-free flop).
  Compensation, unchanged and still only partial: sv2v is a lexical/structural
  lowering, not an optimising synthesis, and reset literals were confirmed
  unchanged by direct textual diff between gold and gate for every module run
  (see each module's extracted `gate_*.v`).
- Each module is checked at its **default parameterisation** only.
- Blackboxed cells (`ICGx1_ASAP7_75t_R`) are name-matched only, not checked:
  Tier 1 shows eqy generates no proof obligation at all for a module whose
  only content is a blackbox instance.
- CPU and GPU internals are out of scope: `SOC_SV_FILES` stubs them
  (`rv32i_cpu_top_stub.sv` / `gpu_top_stub.sv`) for this SoC-level conversion.

## Known environmental blocker

The root filesystem filled to 100% during the first round of this bead's work.
All scratch is now directed to `/nobackup` via `--workdir-root`; the tier-3
re-run recorded above was done on a healthy filesystem and reproduces the
original numbers exactly.

## sv2v conversion bugs found

**None.** Every FAIL in this harness has been root-caused to a gold-side
frontend artifact (Synlig's unpacked-array parameter lowering and its
unpacked-array port flattening order), not to sv2v. sv2v's output was checked
for self-consistency at an instantiation boundary and is correct.

## Recommendation on bead `claude_verilog_test-q7n`

**Stays open**, and the case for keeping it open got *stronger*, not weaker.
Two modules were genuinely added (`axil_to_apb`, `boot_rom`, both via the new
Synlig frontend, both `__pnr__`-affected files that previously had only a
by-eye check), the harness is now shown to fail on both frontends, and the two
register-bank FAILs are fully root-caused with reproducible diagnostics. But
one previously-claimed proof was **withdrawn** — `rv32i_clock_gate`'s PASS was
vacuous (zero partitions) — so the real count of modules with a non-empty
proof went 3 → 4 (`cdc_2ff_sync`, the `async_axi_fifo` CDC hierarchy,
`axil_to_apb`, `boot_rom`), and every one of those four is qualified by the
false-PASS class documented above. But the majority of `SOC_SV_FILES` — the whole bus
fabric (`axi4_crossbar`, `axi_lite_interconnect`, `soc_bus`, ...), all the
peripherals, `sram_controller`, `pmu` — is still unchecked, and two modules
(`axi_lite_register_bank`, `apb4_register_bank`) plus `axi4_crossbar` are
demonstrably *unprovable* with the tools in this devshell. Closing q7n now
would overstate what has been shown.

Concrete next steps, in order of expected value:
0. **Close the false-PASS class first.** Until eqy's miter stops exempting
   gold-side `x` (a custom strategy with `ASSUME_DEFINED_INPUTS`, or
   `formalff` applied symmetrically), every PASS in this harness is weaker
   than it reads, and adding more modules just adds more weak PASSes.
1. Run the never-attempted modules (`axi_lite_interconnect`, `soc_bus`,
   `sram_controller`, the four peripherals). No frontend blocker is known for
   them; they are the cheapest remaining coverage.
2. Report the two Synlig defects upstream (unpacked-array parameter garbage;
   unpacked-array port flattening order vs sv2v) — both have minimal repros in
   this README. Fixing the first would unblock the two register banks
   outright.
3. `axi4_crossbar` needs the `rtlil.cc:2150` assert fixed upstream, or a newer
   Yosys/Synlig; there is no local workaround.
