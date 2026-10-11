# Synthesis undef-elaboration gate (bead `gc0y`)

Origin: bead `dud4` (`docs/SKY130_CPU_SYNLIG_DUD4.md`) and `ma7` (`docs/ASAP7_CPU_SYNLIG_MA7.md`). The Synlig/UHDM frontend
elaborated `.if_id_rs1_addr(if_id_reg.instruction[19:15])` as `5'x` and logged only
`Warning: Range select [639:608] out of bounds on signal \if_id_reg: Setting all 32 result bits to undef.`
Synthesis deleted the forwarding-select flops; lint, `Checker.YosysSynthChecks`, LVS and P&R all passed.

## Components

| Piece | Path |
| :--- | :--- |
| Scanner + structural check | `tools/verif/check_synth_undef.py` (tests `tb/tests/test_check_synth_undef.py`, real-log fixtures `tb/tests/fixtures/synth_undef/`) |
| Allowlist (justified) | `tools/verif/synth_undef_allowlist.txt` |
| Flow hook | `pnr/plugins/librelane_plugin_cvt_synthgate`, activated by `SYNTH_GATE_ENV` in `pnr/Makefile` (all `librelane-*` targets) |

## Pattern list (evidence: probe designs through yosys 0.46 + Synlig plugin and through sv2v + `read_verilog`; `strings` of yosys 0.46/0.62 and `synlig-sv.so`)

| Rule | Class | Wording | Evidence |
| :--- | :--- | :--- | :--- |
| `undef-range-select` | FAIL | `Range select [a:b] out of bounds on signal X: Setting all N result bits to undef`; `Range [a:b] select out of bounds ... Setting N MSB/LSB bits to undef`; `Range select out of bounds ... Setting result bit to undef` | probes p01 p02 p03 p10 p11 p17; yosys AST frontend (both frontends) and Synlig |
| `undef-substitution` | FAIL | any `Warning: ... setting/replacing/substituting ... undef` | catch-all for sibling wording |
| `no-driver` | FAIL | `Wire X is used but has no driver` | p05, p07 (a typo'd identifier shows up this way) |
| `multi-driver` | FAIL | `multiple conflicting drivers for` | p06 |
| `port-resize` | FAIL | `Resizing cell port .. from 8 bits to 4 bits` | p08 |
| `implicit-decl` | FAIL | `Identifier X is implicitly declared` | dud4 logs; allowlisted only for the dead `_unused_*` sinks |
| `tool-error` | FAIL | `ERROR:` | p13, p16, p19 |
| `post-increment` | WARN | `Post-incrementation operations are handled as pre-incrementation` | see below |
| `removed-module` | WARN, cross-checked | `Removing unelaborated module: \M` | FAIL (`removed-module-missing`) unless the header JSON holds `M` or `$paramod...\M` |
| `mem2reg`, `assigned-in-block`, `setundef-count` | INFO | | benign by construction, printed with `-v` |
| `x-driven-instance-input` | FAIL (structural) | instance input port wired to constant `x` in `<design>.h.json` | dud4 Synlig: exactly 2 hits (`u_hazard` `if_id_rs1_addr`/`if_id_rs2_addr`); sv2v arm and workaround arm: 0 |
| `x-driven-net` | FAIL (structural) | a user-named net with a constant-`x` bit | catches the **silent** forms below |

Silent forms (no distinct message at all): a constant out-of-range array index (`m[6]` on a 4-entry array, p04) yields
`connect y 8'x` in BOTH frontends with only the benign `Replacing memory` line; only `x-driven-net` sees it.
`struct.member[hi:lo]` part-selects are mis-offset by Synlig in ANY expression (p10, plain `assign`), not only in port connections.

## sv2v function temporaries on the SoC (bead `j1b7`)

The gate was designed and validated on the CPU macro. On the Sky130 SoC (sv2v frontend) the structural `x-driven-net` rule reported
**509** hits, all of them wires named `<func>$func$<file>:<line>$<n>.<variable>` (functions `decode`, `sbox`, `xtime`, `mix_col`,
`key_step`, `strb_expand`, SHA `small_sigma*`, `sv2v_cast_*`, ...), 0 `x-driven-instance-input`, 0 `undef-range-select`. The SoC flow aborted
at step 3 and needed `CVT_SYNTH_GATE=warn`. The warn escape hatch is **not** part of any recipe, doc or CI step any more; the gate runs blocking.

### Mechanism (read from the RTLIL, `tb/tests/fixtures/synth_undef/functemp_*`)

yosys inlines each function call. Per call it creates two sets of wires: the call-site `$result` (really driven) and the function body's own
argument, local and `$result` wires. The `always`-style process that implements the call carries `sync always / update <body wire> 4'x` for
every body wire: the body wires are *declared storage* whose default value is x, and the real value travels through proc temporaries
(`$0\<wire>$n` / `$1\<wire>$n`) into the call-site result. After `proc`, `connect \<body wire> 4'x` remains, so the JSON header shows a named net
that is entirely constant x. A **read** of such a wire (a path that never assigned the variable) is a different object: proc resolves it into a
literal `x` on a `$mux` data input. A function whose result is unassigned on some path therefore produces the same x-named net *plus* a
reader, which is the case a pure name skip would hide.

### The rule `func-temp-dead-init`

A net `<func>$func$...` that is entirely x is **exempt** only if all hold, judged on the PRE-`proc` RTLIL of the same elaboration
(`write_rtlil` after `hierarchy`, passed as `--pre-rtlil`):

1. every x-initialised wire of the group (module base name, function, `file:line`, variable) has only full-width `update/assign <wire> <const x>`;
2. no other driver (no non-x update/assign, no module-level `connect <wire> ...`);
3. **no reader**: the wire appears in no cell connection, process right-hand side, `switch`, `sync` or `connect` right-hand side;
4. the group size in the proof equals the number of such nets in the JSON header (a proof from another elaboration exempts nothing).

Anything else keeps `x-driven-net` FAIL and the text says why (`function temporary is READ before it is assigned: <RTLIL line>`, `no pre-proc
RTLIL proof supplied`, `group not found`, ...). No `--pre-rtlil` means no exemption (fail closed). Partially-x nets, instance inputs tied to x,
log-level undef warnings and every other rule are untouched. Matching is by names that do not depend on yosys' autoidx or on directories, so the
flow's JSON (absolute paths) and the proof run agree.

Why not "check later in the yosys script": after `opt_clean -purge` the dead wires disappear without any name rule, but so does every
unread-by-then named x net, and a function read of x becomes an anonymous `$mux` input that is indistinguishable from an intentional
`default: y = 'x`. The pre-proc read test is the narrowest point at which the two cases still differ.

### Report

`check_synth_undef.py` always prints one line per run, and the LibreLane report `synth_undef_gate.rpt` carries the same line:

```
EXEMPT  [func-temp-dead-init] <N> net(s) in <M> function(s) (constant-x update proven unread in the pre-proc RTLIL): decode=188 sbox=40 ...
```

`-v` lists every exempted net. `--json` has `exempt_by_function` and `exempt_total`. A **new function** shows up as a new `name=count` entry; a function
whose temporaries get read shows up as `x-driven-net` FAIL instead. Nothing needs to be added anywhere to introduce a function: if its temporaries
are never read it is exempt automatically; if they are read, fix the RTL (assign the result on every path).

### Measured (yosys 0.46, sv2v 0.0.13.1; `tools/verif/synth_gate/elab_gate.sh`)

@@MEASURED@@

### Controls (all in blocking mode, run by `ci_smoke.sh`)

@@CONTROLS@@

### Flow wiring

The LibreLane plugin writes the proof lazily: only if the JSON header contains x-driven nets that look like function temporaries and the frontend is
not Synlig, it re-elaborates the step's own sources (same config, defines and top) with plain yosys up to `hierarchy` and dumps
`func_temp_proof.pre.il` into the JsonHeader step directory (one extra elaboration, see Measured). If that fails the step fails ("never a pass").

## `Post-incrementation operations are handled as pre-incrementation`

The "30" warnings in the dud4 logs are 15 source sites, each reported by both the JSON-header and synthesis logs:
`rv32i_regfile.sv:46`, `rv32i_dcache.sv:250,253,499,510,547,952`, `rv32i_icache.sv:203,206,412,423,453,517,605`,
`soc_addr_map_pkg.sv:72`. **All 15 are `for (...; i++)` loop steps whose value is unused.** Probe results (miter + SAT,
Synlig vs sv2v elaboration of the same source): loop-step `i++` (p14, p20) proven equivalent. When the value IS used
(`z[j++] = ..`, `y = j++`; p13, p19) Synlig does not miscompile silently: it stops with
`ERROR: Don't know how to detect sign and width for AST_ASSIGN_EQ node!`. So the class cannot produce a second silent
miscompile in this repo as it stands, and no bead was filed. The rule stays WARN and is not allowlisted. The same miter
flow flags p01 and p10 as NOT equivalent (negative control of the harness).

## Allowlist

`tools/verif/synth_undef_allowlist.txt`: format `rule | regex | justification (>= 20 chars)`. Current entries: the
`implicit-decl` warnings for the initialisers of the dead `_unused_csr_wr_en` / `_unused_csr_illegal` / `_unused_*` lint sinks
(read by nothing). `post-increment`, `removed-module`, `mem2reg` need no entry (not FAIL). Stale entries are reported with `-v`.

## What the gate does not cover

Messages the tools never print; defects that leave no `x` at the elaboration boundary (for example a mis-elaborated
runtime mux, the `OPT_MUXTREE` class of beads gcd/b0t); defects introduced after elaboration (ABC, resizer); anything in a flow
that does not go through `pnr/Makefile`. It is a tripwire for the undef-substitution class, not a proof of frontend correctness;
the gate-vs-RTL differential (`tools/verif/gls/`) remains the functional proof.

## CI job (`.github/workflows/synth-undef-gate.yml`, `tools/verif/synth_gate/ci_smoke.sh`)

Path-filtered on `rtl/**`, `pnr/**`, `tools/verif/**`, the gate tests and fixtures. Uses the pinned oss-cad-suite yosys + sv2v of the CDC job (same cache
key) and the pinned nix Verilator. `ci_smoke.sh` drives `tools/verif/synth_gate/elab_gate.sh` (source list and defines from `make -C pnr
<target>-sv2v-inputs`, never a generated file; sv2v/yosys errors are printed). Steps: (1) **positive controls, blocking mode**: Sky130 CPU macro,
Sky130 SoC and ASAP7 SoC must PASS; (2) **negative controls**, each must FAIL for the stated reason: CPU `u_hazard` out-of-range select (the dud4
lines themselves cannot be the control, sv2v elaborates them correctly, which is why the PD flow uses sv2v), and in SoC scope an out-of-range
struct-member select, an instance port tied to `'x`, and a function result left unassigned on a path (injected into a scratch copy of `timer.sv`,
reaching `irq_o`; snippets in `tools/verif/synth_gate/inject/`); (3) `synth -flatten` + `techmap` + `abc -g` to yosys generic gates (no PDK) and a
Verilator gate-vs-RTL differential on `trivial`, `ma7_straight`, `ma7_branch` (commit stream, APB debug reads, AXI writes must be identical).
Runtime and peak RSS: @@CI@@

Does NOT cover: the Synlig frontend (oss-cad-suite has no Synlig plugin; the Synlig arm is protected only by the PD-time plugin); GPU macros;
PDK cell models and ABC mapping with the real liberty; timing. The differential's own negative control was not
re-run for this job (it was exercised in dud4 with the Synlig netlist, which diverges). First CI run on GitHub is pending.

## Netlist census tripwire (`tools/verif/check_cpu_netlist_census.py`)

After a Sky130 `rv32i_cpu_top` synthesis the plugin requires the `fwd_b_sel_r`, `fwd_b_ex1c_r`, `fwd_b_ex1b2_r` nets and 4800-4950 flops.
Measured on the dud4 netlists: sv2v main 4868 flops + all three nets (PASS); Synlig main 4863 flops, nets missing (FIRES); pinned Synlig
4829 flops, nets missing (FIRES). It is a tripwire for this one known casualty, not a proof. ASAP7 netlists do not keep these net names.
