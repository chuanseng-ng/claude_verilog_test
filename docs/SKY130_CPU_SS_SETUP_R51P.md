# Sky130 CPU macro: ss reg-to-reg setup failure (bead r51p) - path analysis

Status: cache-side RTL fix landed on `fix/icache-ss-setup-r51p` (PR #318, stacked on #313). User decision 2026-10-19: no cycle-count change and no pipeline restructuring; the remaining ss residual stays open in r51p and is measured at the batched CPU re-harden.
Source data: `pnr/sky130/cpu/runs/RUN_2026-10-11_06-00-12/57-openroad-stapostpnr/max_ss_100C_1v60/max.rpt`
(top 1000 setup paths, 75 MHz = 13.333 ns, uncertainty 0.5 ns). Measured, not inferred, unless marked.

## 1. The premise in the bead is not what the reports show

The bead and the user decision describe the worst paths as "into the icache tag SRAM's negedge-sampled inputs
(half-cycle paths)". The reports say otherwise.

* **The SRAM input arcs are full-cycle.** In `pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib`
  every input pin (`csb0`, `web0`, `addr0`, `din0`, `wmask0`) has `timing_type : setup_rising`
  against `clk0`. The worst path's required time is `13.333 (rise edge) + clk0 arrival - 0.5 uncertainty - 0.103 setup`:
  a capture at the next rising edge, one full period. STA prints the endpoint as
  "falling edge-triggered flip-flop" only because the macro also has a `falling_edge` arc on `dout0`.
* **The half-cycle paths are on the SRAM outputs** (`dout0` launches on the falling edge). They are already cut by the
  `CS_SRAM_LATCH` register stage (`tag_dout_r` / `data_dout_r`). None of the 1000 reported worst paths starts at an SRAM.
* **The SRAM endpoints are 5 to 50 of 1000, not the population.** 947 of the 1000 reported endpoints are ordinary flops.
  The worst SRAM endpoint (`u_tag_sram/csb0`, -3.704 ns) is 0.02 ns worse than the worst flop endpoint
  (`pc_if_from_core`, -3.684 ns). Retiming only the SRAM input pins cannot move WNS.

## 2. What the failing cone is (measured, from the run's own netlist `54-openroad-fillinsertion/rv32i_cpu_top.nl.v`)

Start points of the 1000 paths (flop Q-net name): `u_core.u_dcache.state_q` 407 (worst -3.704), `u_core.ex_mem_reg` 329
(-3.363), `u_core.ex1b_ex2_reg_q` 116 (-2.907), plus a few others. End points: `u_icache.refill_buf_q` 128,
`u_dcache.wb_buf_q` 82, `u_csr.mcycle_q`/`minstret_q` 74, `if_id_reg` 33, `ic_addr_q` 32, `pc_if_from_core` 30,
debug-register write data `dbg_*` ~230, SRAM csb0 5.

Three combinational cells (`_22517_` o21ai, `_22618_` a21oi, `wire1348`) lie on 58 % of all 1000 paths. Their fan-in cone
(netlist traversal) is exactly: 8 bits of `ex_mem_reg`, 5 bits of `u_dcache.state_q`, `u_dcache.hit_bank_q`,
`mem_trap_entry_r`, `ex_pc_redirect_r`, `ex1c_ex1b_reg_q`. That is the **global stall / redirect network**:

```
dcache.state_q, ex_mem_reg  ->  dc_stall_o -> mem_cache_stall (rv32i_pipeline_mem.sv:151)
                            ->  hazard-unit priority chain (rv32i_hazard_unit.sv:362-427: mem_cache_stall beats ex_pc_redirect)
                            ->  pc_redirect / jal_redirect -> ic_valid_o (rv32i_pipeline_if.sv:116)
                            ->  icache: addr_mismatch / hit / ic_stall_o / SRAM csb0 / refill_buf_q enable
                            ->  if_cache_stall -> stall_pc -> pc_q, if_id_reg, ic_addr_q enables
```

Further down the same cone (cell `_22767_` onward) sit `mem_wb_reg` (72 leaves) and `dbg_bp0_addr` / `dbg_bp1_addr`
(59 / 57 leaves): the combinational breakpoint compare `bp0_hit = ctrl[0] && (commit_pc_o == dbg_bp0_addr) && commit_valid_o`
(`rv32i_cpu_top.sv:794-797`) feeds `dbg_halt_req` (line 696), which gates `ic_valid_o`. It is in the cone but is not the
latest-arriving input: it launches from flops and settles before the stall network does.

## 3. Where the time goes (worst path, `u_dcache.state_q[3]` -> `u_icache.u_tag_sram/csb0`, 15.84 ns data path)

| segment | ns |
|---|---|
| clk-to-Q 0.64 + 4 fanout buffers (state_q[3] fans out to ~65 sinks) | 2.0 |
| `dc_stall_o` state decode: and4bb + a31o + a211o (4-bit binary state, 3 levels) | 2.5 |
| trunk: o21ai + a21oi + buffer (`mem_cache_stall` and its priority gating) | 1.6 |
| gating into `tag_csb0`: a2111oi (1.59 ns, slew 1.5 ns) + 11 repeater buffers over a long route (~3.1 ns) + and4 + 4 buffers + a21oi + 4 buffers | ~9.7 |

Pre-PNR (no wires, ideal clocks) the same netlist already gives nom_ss WNS -1.78 ns / TNS -79 ns
(`12-openroad-staprepnr/nom_ss_100C_1v60/wns.max.rpt`). So roughly half of the post-route -3.2 (nom_ss) is logic depth
and half is wire/buffer/skew. The cure for the logic half is RTL; the wire half is the PD agent's.

For flop endpoints starting at `ex_mem_reg[0]` (-3.363): Q 1.21 + buffers 1.1 + `need_mem_access` o211ai/nor2/o21ai (3 levels,
3 repeaters) reach the trunk at ~7.1 ns after launch, then a 14-gate tail (hazard priority, `ic_valid_o`, the icache
`valid_array[latch_index]` 256:1 read tree, `addr_mismatch`, `ic_stall_o`, enable muxes) reaches the flop at 22.8 ns.

## 4. Consequences for the fix

* The user-prescribed change (retime icache tag-SRAM inputs for a full cycle) is a no-op in STA terms: they already get one.
* What can be done in RTL, cycle-exactly, and attacks the measured cone:
  1. (landed) Cache FSM state encoding: put every unconditionally-stalling state in the `1xxx` half so `dc_stall_o` /
     `ic_stall_o` need `state_q[3]` instead of a 4-bit decode (removes ~2 of the 2.5 ns decode segment). Pure encoding.
  2. (landed, Sky130 arm only) Remove `ic_valid_i` (and thereby the whole redirect/halt/stall cone) from `tag_csb0` / `data_csb0`: a read issued in
     `CS_IDLE` with `ic_valid_i = 0` is never consumed (dout is sampled only in `CS_SRAM_LATCH`, entered only with
     `ic_valid_i = 1`), so the SRAM enable can depend on `state_q == CS_IDLE` alone. This is the legitimate form of the
     user's intent for the five SRAM pins.
* Not expected to close ss at 75 MHz on its own. Remaining violators after 1 and 2 are the `ex_mem_reg` -> `need_mem_access`
  entrance and the 14-gate tail; both need pipeline-structure changes, which the user ruled out for this PR (section 6).
* Context for a human decision (not acted on): the SoC runs this macro at 40 MHz (25 ns); the 75 MHz standalone ss
  failure does not affect SoC closure. The user decision for r51p is: RTL fix, do not relax the period, do not use SDC.

## 5. What changed (RTL) and why it is cycle-exact

* `rtl/mem/rv32i_cache_pkg.sv`: new `cache_state_t` encoding. `state_q[3] = 1` for LATCH, HIT_PENDING, REFILL, WRITEBACK,
  UNCACHED_RD/WR, FLUSH_SCAN, INVAL_SCAN; IDLE (0000, reset), TAG_CHECK, DONE have it clear. All arms share the package.
* `rv32i_dcache.sv` / `rv32i_icache.sv`: `dc_stall_o` / `ic_stall_o` = `state_q[3] || (IDLE && valid) || (TAG_CHECK && !hit)`.
  Same truth table over the reachable states (icache never enters the D$-only states).
* `rv32i_icache.sv`, Sky130 arm only (`ifdef SRAM_SKY130`): `idle_read_en = 1` so tag/data `csb0` in `CS_IDLE` do not depend on
  `ic_valid_i` / `ic_invalidate_i`. Why only Sky130: on ASAP7 `csb0` feeds the SRAM clock gate (extra enabled cycles are extra
  dynamic power on a flow that was signed off as-is), and the FreePDK45 / FPGA arms have no timing problem here. Why it is safe:
  `tag_dout_r` / `data_dout_r` capture `dout0` only in `CS_SRAM_LATCH`, which is entered only from a `CS_IDLE` cycle with
  `ic_valid_i = 1` and `ic_invalidate_i = 0`; a read in any other IDLE cycle is never consumed and has no side effect.
  Writes (`tag_we_q` / `data_we_q`) still override.
* No `ma7` / `ainf` exposure: no struct-member selects, no runtime-indexed muxes added (`check_struct_member_select.py` exit 0).

Verification (all on this branch, measured):

| gate | result |
|---|---|
| `tb/tests/test_cache_stall_encoding.py` (new; RED before RTL, 3 failed / 2 passed) | 5/5 |
| icache / dcache / cache_integration, Sky130 arm | 9/9, 8/8, 5/5 |
| icache / dcache / cache_integration, default arm | 9/9, 8/8, 5/5 |
| `make -C sim rollup` (34 suites) | 265 tests, 0 fail |
| `test_mbist_cpu_macro` (collars still work) | 7/7 |
| RTL-vs-RTL differential, base (#313) vs this branch, six `tools/verif/gls/sky130` programs | 6/6 IDENTICAL, same total cycles (466/566/966/4666/4666/4666) |
| Verilator lint `lint`, `lint_soc`, `lint_soc_sky130` | 0 errors; only existing warning classes (UNUSEDPARAM, DECLFILENAME, MODDUP, PINCONNECTEMPTY on `dout1`) |
| `dft-scan-check`, `-asap7`, `-cpu-macro`, `-cpu-macro-asap7` | 0 violations each |
| `soc_all_ci` plain and `FPGA=1` | left to PR CI (PD flow occupies the host) |
| mutation campaign, 15 mutants on the changed logic | 13 killed, 2 survived (both provably equivalent, below) |

Mutants: dcache/icache stall (bit 3 dropped, idle ungated, hit inverted) x6, encoding bit-3 or collision x4, idle read never
(Sky130 / tag / data) x3 all KILLED (by the structural test or by `icache` / `dcache`). Survivors: M14 `idle_read_en = !ic_invalidate_i`
and M15 (functional arm drops `ic_valid_i`): both only add reads that are never consumed, so they are equivalent mutants by the
argument above (M15 sits in code not compiled in the Sky130-arm suites). `PASS_FLOOR` unchanged: no cocotb test was added or removed.

## 6. PD handoff: expected versus residual (for the batched CPU re-harden)

Expected effect (INFERRED from the RUN_2026-10-11 path structure; not measured, no LibreLane run was done):

| path class (RUN_2026-10-11, max_ss) | paths | worst before | expected after |
|---|---|---|---|
| launched at `u_dcache.state_q` (decode head of the cone) | 407 | -3.704 | roughly +1.3 to +2.0 ns: and4bb+a31o+a211o (2.46 ns) replaced by one OR level |
| SRAM `csb0` endpoints (tag + 4 data) | 5 | -3.704 .. -2.3 | cone is now icache `state_q` + `tag_we_q` only: expected to clear |
| launched at `ex_mem_reg` (via `need_mem_access`) | 329 | -3.363 | UNCHANGED |
| launched at `ex1b_ex2_reg_q` (load-use) | 116 | -2.907 | UNCHANGED |
| other (`mem_wb_reg`, `last_commit_insn_q`, ...) | ~140 | -2.98 .. -0.4 | unchanged |

So the expected residual WNS is about -3.4 ns, set by `ex_mem_reg` and `ex1b_ex2_reg_q` entrances, not by the state decode.
TNS should improve; WNS barely. Pre-PNR (no wires) the same netlist was already -1.78 ns at nom_ss, so about half of the residual is
logic depth (RTL) and half is wire/buffer/skew (placement; the `csb0` path alone carried an 11-repeater, 3.1 ns chain).

Re-check after the re-harden:
1. `max_ss` and `nom_ss` WNS/TNS/violator count versus -3.704 / -1677.6 / 996 (RUN_2026-10-11). Expect WNS about -3.4, startpoint class `ex_mem_reg` / `ex1b_ex2_reg_q`.
2. Re-run `classify.py`-style startpoint/endpoint grouping: `u_dcache.state_q` should have dropped out of the top paths; SRAM `csb0` endpoints should be positive. The collars from #313 add a `mem_collar` mux in series with each pin (about one gate); that is on the full-cycle input arc and is not expected to bind.
3. Check the icache/dcache SRAM `csb0` activity did not raise the Sky130 power/IR figures noticeably (Sky130 arm now reads in every IDLE cycle).
4. Hold: no new input-to-flop paths were added; the usual boundary-port hold set is unchanged in structure.
5. `check_cpu_netlist_census` / gate-vs-RTL (`run_netlist_proof.sh`) on the new netlist as for any re-harden.

Not done in this PR (user decision: no pipeline restructuring; remains open in r51p): registering `need_mem_access` / `mem_misaligned` as precomputed flags in `rv32i_pipeline_ex2` (D-side is a pure function of `ex1b_ex2_reg_q`, shallow), the `ic_valid_o` / `dbg_halt_req` breakpoint-compare coupling (`rv32i_cpu_top.sv:794-797`), and the load-use priority chain behind `ex1b_ex2_reg_q`. SoC context unchanged: the SoC runs this macro at 40 MHz and closes all 9 corners.
