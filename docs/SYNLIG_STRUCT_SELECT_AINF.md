# Synlig struct-member part-select defect: rule, site table, equivalence (bead `ainf`)

Date 2026-10-10. Scope: does the Synlig frontend silently mis-elaborate the struct-member part-selects that PR #259
(`dud4`) did not rewrite? Everything below is MEASURED unless marked INFERRED. Tools: yosys 0.46 + Synlig plugin
(`/nix/store/7vsbsrhbj6kx5lfdc8qs9wlccxfb8f7h-yosys-synlig-sv`, Surelog 1.82) vs sv2v 0.0.13.1 + yosys; comparison =
miter + `sat -verify -prove-asserts -seq 4 -set-init-zero` (flow from PR #264's `tools/verif/synth_gate/equiv_probe.sh`,
re-implemented in `tools/verif/struct_select/run_probes.sh`; every job under `systemd-run ... MemoryMax=4G`).

## Step 1: the defect rule (probe evidence: `tools/verif/struct_select/results/round1..7.txt`, 370 probes)

Two independent Synlig defects. Neither is triggered by plain reads of a member of an ordinary struct.

### D1 (read side): a packed/unpacked struct with EXACTLY TWO members declared with a packed range

"Ranged member" = declared `logic [n:0] m;` (a `[0:0]` range counts; a scalar `logic m;`, a struct-typed member and an
enum-typed member do NOT count). If a struct type has exactly two ranged members, then for ANY member `m` of it

    s.m[hi:lo]   (or s.m[i], constant or runtime)   is evaluated by Synlig as   s[ hi*W + (hi-lo) : hi*W ]

where `W` is the width of the LAST-declared (LSB-most) ranged member. `lo` and the member's own offset are ignored;
the select behaves like "element `hi` of an array of W-bit elements", truncated to the select width.

* `if_id_reg_t` = `{pc[31:0], instruction[31:0], valid}` has two ranged members (valid is a scalar) and W = 32:
  `instruction[19:15]` -> `[19*32+4 : 19*32] = [612:608]` (the logged `[639:608]` is the whole 32-bit element, which is
  then truncated); `[24:20]` -> `[768+4:768]`. This reproduces the dud4 numbers exactly.
* `n_t = {pad[7:0], in(struct), tail[4:0]}` (two ranged members, W = 5): `n.tail[3:2]` -> `[3*5+1:3*5] = [16:15]`,
  `n.pad[7:4]` -> `[7*5+3:7*5] = [38:35]` (both measured, in bounds, no warning, wrong).
* Fits all 27 failing two-ranged-member probes of round 3 (random widths 1..32) without exception.
* Counter-evidence that this is not "number of members": a 3-member struct with one scalar (2 ranged) fails, a 3-member
  struct with `logic [0:0]` instead of the scalar (3 ranged) is correct (`s01` vs `s02`, round 5); 1, 3, 4, 5 ranged
  members are correct in all 120+ probes (rounds 2, 3, 6, 7).

Outcome classes (a) correct: `hi == 0` and the member is the LSB member and `lo == 0`; (b) `hi*W + width > struct width`:
warning `Range select [..] out of bounds on signal ...` and `x` (this is dud4); (c) in bounds but wrong, NO warning, NO
`x`: possible whenever `hi*W + (hi-lo) < total width`; measured instances: round 7 `X2_rhs_hi1` (`s.b[1:0]` read from
`s[33:32]` instead of `s[1:0]`), `X2_rhs_bit`, `X2_rhs_concat`, `X2_rhs_reg`, `X2_rhs_local`, `i03`, `i04`, round 5 `s*`.
(c) IS possible, and for small `hi` it is the normal case, not the exception. Split by `tools/verif/struct_select/classify.py`
(round 3, 27 failing of 150: 17 warn+x, 2 warn+wrong, **8 fully silent**; round 7: 21 fully silent, 17 warn+wrong, 5
warn+x). "warn+wrong" = the `Range select ... out of bounds` warning IS printed (the 32-bit "element" overruns the
struct) but the surviving bits are wrong data, not `x`; the PR #264 warning scanner sees those. "Fully silent" = the
element fits inside the struct: no warning, no `x`, wrong bits (e.g. `s.m[0]` of a non-LSB member of a two-ranged
struct, or `s.b[1:0]` with W large); only a miter / simulation sees them. D2 is always fully silent.

Where D1 shows: port-typed struct, local wire/reg struct, concatenation operands, `case` selectors, bit selects,
runtime bit select `s.m[i]`, port-connection expressions, unpacked structs with two ranged members. Where it does NOT
show: `s.m[b +: n]` / `s.m[b -: n]` (indexed part-select, correct), selects of a full-width wire copy (`w = s.m; w[7:4]`),
an array-of-struct element base (`arr[1].m[1:0]` was correct in the one probe, `X2_rhs_arr`; not proven in general).
It does not depend on the base signal being a port, local, register or array element beyond that.

### D2 (write side): part-select of a struct member on the LEFT-HAND side

`y.m[hi:lo] = v` with `hi != lo` is elaborated as the WHOLE-member assignment `y.m = v` (zero-extended); the bits of
`m` outside the select are lost and the select position is ignored. No warning, no `x`. Independent of the number of
ranged members (measured R = 2, 3, 4: `lhs_copy`, `lhs_zero`, `lhs_ff`, `lhs_assign` all NOT equivalent).
The single-bit LHS `y.m[i] = v` is correct for R >= 3 and wrong for R = 2 (`X3_lhs_bit`, `X4_lhs_bit` equivalent;
`X2_lhs_bit` not).

## Step 1 reading for this repo

The rule is a function of the struct TYPE (count of ranged members), not of the member position, so every site can be
predicted from its struct definition (step 2).

## Step 2a: mechanical site table (`tools/verif/struct_select/sitetable.py`, output `results/sitetable.txt`)

Struct types in `rtl/` (R = members declared with a packed range, i.e. the D1 trigger when R == 2):

| type | R | where | note |
| :--- | :-: | :--- | :--- |
| `if_id_reg_t` | **2** | rv32i_pipeline_pkg | D1 HOT (`pc`, `instruction` ranged; `valid` scalar). The dud4 type. |
| `warp_state_t` | **2** | gpu_pkg | D1 HOT, but no member select exists on it |
| `div_entry_t` | **2** | gpu_pkg | D1 HOT, but no member select exists on it |
| `desc_t` | 3 | dma_engine | one member-removal from R=2; no member select |
| `mem_wb_reg_t` 7, `ex_mem_reg_t` 12, `ex1_ex2_reg_t` 12, `id_ex_reg_t` 14, `ex1a_ex1b_t` 19 | >= 7 | pipeline pkg | far from 2 |
| `if_id_t` 4, `id_ex_t` 9, `ex_wb_t` 6 (gpu_compute_unit), `kernel_desc_t` 8, `gpu_[rib]_instr_t` 5-6 | >= 4 | gpu | |

READ selects `x.m[..]` in the whole `rtl/` tree: 23 (24 incl. the two on one gpu_top line), all on types with R >= 7,
so **all predicted correct**: rv32i_pipeline_ex:109 (`id_ex_reg_t.csr_op[2]`), rv32i_pipeline_mem:103,104,111,112
(`ex_mem_reg_t.alu_result[0]`, `[1:0]`), rv32i_pipeline_wb:75 (`mem_wb_reg_t.trap_cause[3:0]`),
rv32i_pipeline_ex1c:122-150,197 (`ex1a_ex1b_t.alu_result[1:0]/[1]/[31:1]`, `.fwd_store[7:0]/[15:0]`),
gpu_top:253 (`kernel_desc_t.block_x[9:3]`, `[2:0]`; the line was :250 in the dud4 sweep),
gpu_compute_unit:377,378,386,388 (`id_ex_t.rs1_data[l]`, `.rs2_data[l]`, `.imm[11]`). None of these is on an R == 2 type,
so D1 does not apply. **No select at all exists on any of the three R == 2 types** (`if_id_reg_t`'s two were removed by PR #259).
Not covered by probes: `id_ex_t.rs1_data[l]`, a member that is itself a 2-D packed array `[N_LANES-1:0][31:0]` selected by a
loop variable -- predicted correct by the type rule but verified separately in step 2b.

WRITE (LHS) selects `y.m[hi:lo] = ..` / `y.m[i] = ..` (D2): **none** in `rtl/` (regex over single-line statements, plain,
`assign`, and concatenation-LHS forms; 0 hits). D2 is therefore not triggered anywhere today.

## Step 2b: Synlig-vs-sv2v equivalence on the real modules (`modeq.sh`, `run_modeq.sh`, `mkcone.py`)

Method: elaborate the module with Synlig and with sv2v+yosys, `flatten`, expose flops (`expose -evert-dff`, so the
check is combinational with matched state), miter + `sat -verify -prove-asserts`. Memory cap `systemd-run -p
MemoryMax=4G -p MemorySwapMax=0`, timeout 900 s. Negative control: sv2v arm fed a copy of `rv32i_pipeline_wb.sv` with
`trap_cause[3:0]` changed to `[4:1]` -> NOT-EQUIV (model found), as required. SAT sizes are non-trivial (e.g. 10 884
variables / 29 627 clauses for `rv32i_pipeline_ex`).

| module / cone | sites | prediction | result |
| :--- | :--- | :--- | :--- |
| `rv32i_pipeline_wb` | wb:75 | correct | **EQUIV** |
| `rv32i_pipeline_ex1c` | ex1c:122-150,197 (byte/half store lanes) | correct | **EQUIV** |
| `rv32i_pipeline_mem` | mem:103,104,111,112 (misalign) | correct | **EQUIV** |
| `rv32i_pipeline_ex` (with alu, branch_comp) | ex:109 | correct | **EQUIV** |
| `gpu_top` cone (`n_warps_raw`, text extracted verbatim) | gpu_top:253 | correct | **EQUIV** |
| `gpu_compute_unit` cone (always_comb at :370-390 extracted verbatim, `id_ex_t` from the source) | 377,378,386,388 | **correct (type rule)** | **NOT EQUIVALENT -- prediction wrong** |

The three D1/D2 sites classes behave as predicted. The GPU result is a **third, independent defect (D3)** that the
type rule does not cover:

### D3: element select of a struct member that is a multi-dimensional packed array

`id_ex_t` has `logic [N_LANES-1:0][31:0] rs1_data, rs2_data;`. `id_ex_q.rs1_data[l]` (32-bit element `l`) is elaborated
by Synlig as the single BIT `rs1_data[l]` (zero-extended), at the correct member base. Evidence in the cone netlist:
Synlig `mem_addr_o[31:0] = id_ex_q[320] + sext(imm)` versus sv2v `id_ex_q[351:320] + sext(imm)`; lane 1 reads bit
321 instead of `[383:352]`, etc. Probes (round 8, `results/round8_d3.txt`; independent of R, constant/runtime/loop index,
port/local base, always fully silent: `oob=0`): `s.r[2]` -> `s[10]` instead of `s[31:24]`, `s.r[i]`, `s.r[l]` in a loop,
a one-ranged-member struct too. Correct forms: `w = s.r; w[l]`, a plain (non-struct) 2-D vector `r[l]`, and a
select of bits INSIDE an element (`s.r[2][5:2]`, equivalent).

Consequence in `gpu_compute_unit`: the memory address (`mem_addr_o[l]`, `shmem_addr_o[l]`) and store data
(`mem_wdata_o[l]`, `shmem_wdata_o[l]`) of VLD/VST/VLDS/VSTS are computed from ONE bit of the rs1/rs2 vector register
instead of the 32-bit value. Not proven on whole-module level (flop names differ between the frontends after aliasing,
which defeats the name-based flop exposure; the cone is verbatim source text with the same typedef).
No CPU module contains this idiom (`sitetable.txt`: the only multi-dimensional-array-member element selects in `rtl/`
are these four GPU lines).
