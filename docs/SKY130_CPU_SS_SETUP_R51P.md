# Sky130 CPU macro: ss reg-to-reg setup failure (bead r51p) - path analysis

Status: analysis complete, RTL fix in progress on branch `fix/icache-ss-setup-r51p` (stacked on #313).
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
  1. Cache FSM state encoding: put every unconditionally-stalling state in the `1xxx` half so `dc_stall_o` /
     `ic_stall_o` need `state_q[3]` instead of a 4-bit decode (removes ~2 of the 2.5 ns decode segment). Pure encoding.
  2. Remove `ic_valid_i` (and thereby the whole redirect/halt/stall cone) from `tag_csb0` / `data_csb0`: a read issued in
     `CS_IDLE` with `ic_valid_i = 0` is never consumed (dout is sampled only in `CS_SRAM_LATCH`, entered only with
     `ic_valid_i = 1`), so the SRAM enable can depend on `state_q == CS_IDLE` alone. This is the legitimate form of the
     user's intent for the five SRAM pins.
* Not expected to close ss at 75 MHz on its own. Remaining violators after 1 and 2 are the `ex_mem_reg` -> `need_mem_access`
  entrance and the 14-gate tail; both need behaviour or pipeline-structure changes that are outside "preserve cache behaviour
  exactly" and are listed as follow-ups in the PD handoff note (to be added to this file).
* Context for a human decision (not acted on): the SoC runs this macro at 40 MHz (25 ns); the 75 MHz standalone ss
  failure does not affect SoC closure. The user decision for r51p is: RTL fix, do not relax the period, do not use SDC.
