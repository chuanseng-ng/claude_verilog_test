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
