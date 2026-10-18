# Vivado `report_cdc` triage, Nexys Video with-GPU build (bead hlrm.3)

Input: the routed with-GPU build of PR #304 (`nv7`, Vivado 2026.1, `report_cdc -details`): **1380 Critical**
(CDC-1 x1064, CDC-4 x2, CDC-10 x10, CDC-13 x304). Every Critical row was classified by source and destination object against the
RTL CDC structures (`rtl/soc/cdc/`, `rtl/soc/async_axi_fifo.sv`, `rtl/soc/apb_cdc_bridge.sv`, `rtl/soc/soc_top.sv`,
`rtl/soc/pmu.sv`). No RTL was edited.

Result: **1377 are explained and waived with a stated reason, 3 are a real RTL finding that is deliberately not waived.**
No finding turned out to be a missing `ASYNC_REG` or a missing constraint (every Critical row already carried
`Max Delay Datapath Only` or `False Path`; the 57 + 11 + 9 recognised synchroniser structures all have `ASYNC_REG`).

| Disposition | Rows | Where it is handled |
|---|---:|---|
| Waived, structural by design (W1 `mem_q`) | 1260 | `nexys_video_cdc_waivers.tcl` |
| Waived, debug observation only (W2 ILA) | 110 | `nexys_video_cdc_waivers.tcl` |
| Waived, reset-path AND of two registered resets (W3) | 4 | `nexys_video_cdc_waivers.tcl` |
| Waived, accepted risk: level-held IRQ / lock status (W4) | 3 | `nexys_video_cdc_waivers.tcl` |
| **Real RTL finding, NOT waived (PMU decode)** | **3** | **RTL orchestrator, see "RTL findings"** |
| Missing `ASYNC_REG` / constraint | 0 | (hardening added anyway: `set_bus_skew`) |

Before / after (same routed design family; the "after" numbers are from build `nv8`, section "Result of this change"):
Critical 1380 before, 3 unwaived after (all RTL-owned). `tools/fpga/cdc_gate.py` fails the build report on any other Critical
row and fails on all of them with `--strict`.

## Per-ID disposition

| ID | Rows | Group | Class | Waiver |
|---|---:|---|---|---|
| CDC-1 | 1042 | `u_cpu_axi_cdc/u_*_fifo/mem_q` read -> CPU/fabric logic | by design (W1) | W1 |
| CDC-1 | 22 | system-domain nets and `uart_tx_in` -> ILA probes | debug only (W2) | W2 |
| CDC-4 | 2 | `u_dbg` APB `wdata` / `prdata` (multi-bit) -> ILA trigger match | debug only (W2) | W2 |
| CDC-13 | 218 | `mem_q` read -> D-cache tag/data BRAM, SRAM BRAM, I/D-cache buffers | by design (W1) | W1 |
| CDC-13 | 86 | system-domain nets and `uart_tx_in` -> ILA capture memory | debug only (W2) | W2 |
| CDC-10 | 4 | `sys_rst_q`/`cpu_rst_q` AND -> `cdc_reset_sync` CLR (3 + 1) | reset path (W3) | W3 |
| CDC-10 | 3 | `ext_irq`, `timer_irq`, `~locked` -> 2-FF synchroniser | accepted risk (W4) | W4 |
| CDC-10 | 3 | PMU `dom_state_q` decode -> `cpu_clk_dis_sync`, `cpu_iso_en_sync`, `cpu_pmu_rst_sync` | **real RTL defect** | none |

Non-Critical rows of the same report, for completeness: CDC-3 x57 and CDC-9 x9 (recognised 1-bit / async-reset synchronisers with
`ASYNC_REG`: the `cdc_sync`, `cdc_reset_sync`, board reset chains and the Xilinx debug hub), CDC-6 x11 (multi-bit with `ASYNC_REG`: the ten
gray pointers of the five `async_axi_fifo` channels plus one inside the JTAG-AXI IP; gray code, bus skew now constrained),
CDC-15 x675 (clock-enable-controlled capture: the `apb_cdc_bridge` `cmd_*_cap_q` / `resp_*_q` payload registers and FIFO read data
into enable-gated registers; correct recognition of the 4-phase handshake), CDC-26 x32 (LUTRAM read/write collision on the same
`mem_q`, see W1). None needs action.

## Waivers (each is a `create_waiver -type CDC` with its reason in `nexys_video_cdc_waivers.tcl`)

**W1, `mem_q` storage read (1260 rows).** `cdc_gray_fifo` keeps its payload in `mem_q` written by the write clock and read
combinationally (`assign rd_data_o = mem_q[rd_bin_q]`), so Vivado sees a LUTRAM/BRAM-output-to-flop path across clocks with no
synchroniser. This is the textbook Cummings style-1 FIFO and it is safe by the pointer protocol, not by the data path:
1. An entry is written one write-clock edge before the *registered* gray write pointer that publishes it; that pointer crosses
   through one 2-FF `cdc_sync`; `rd_valid_o = !empty_q`. The data is stable for at least two read-clock edges before it can be consumed.
2. The writer cannot reuse the entry until the registered gray read pointer has crossed back (`full_q`). The "LUTRAM read/write
   collision" (CDC-26) can only occur at an address the reader is not allowed to use (`empty`), where `rd_en = rd_valid & rd_ready = 0`
   masks any data-dependent ready (the `mem_q` -> `rd_bin_q` / `empty_q` / `rd_gray_q` rows are exactly that: a consumer's ready that
   depends on the head entry).
3. What remains is a delay bound, which is constrained: `set_max_delay -datapath_only 0.9 x destination period` between the two
   clocks (`nexys_video_cdc.xdc`), the same budget as section 10 of `pnr/constraints/phase5_soc_multiclock_check.sdc` (the ASIC SDC
   cannot match `mem_q` by name either and uses the same domain-wide fallback). Timing is met on those paths (below).
The waiver is `-from` the `mem_q` RAM clock pins, `-to *PIN`, for CDC-1 and CDC-13 only. It is deliberately source-scoped: any crossing
that does not start in `mem_q` stays visible. The consumers of the read data honour the ready/valid contract; this is what the
divergent-ratio cocotb suite (`soc_multiclock`, 7 ns / 3 ns) exercises on the real RTL. Not verified here: metastability (not
modelable in simulation; the pointer synchronisers are the only places it can matter and they are recognised with `ASYNC_REG`).

**W2, ILA probes (110 rows).** The single ILA (free-licence limit) runs on the CPU clock and probes system-domain nets: the APB debug
bus, UART, IRQ, lock flags, plus the raw `uart_tx_in` pin. Observation only: nothing consumes the capture except the trace viewer, the
sampled nets change at <= 50 MHz and the APB payloads are held stable by the `apb_cdc_bridge` handshake. A torn sample costs a debug
trace sample, never design behaviour. Waived by destination (`u_dbg/u_ila/*`).

**W3, reset AND (4 rows).** `async_axi_fifo` and `apb_cdc_bridge` drive both `cdc_reset_sync` instances from
`rst_both_n = s_rst_n_i & m_rst_n_i` (RTL-intentional: a one-sided reset would inject fabricated AXI beats). The operands are the
registered board resets `sys_rst_q` / `cpu_rst_q`, asserted by the same event. The only glitch an AND of two registered signals can
make is a short *release* of a clear that is already asserted by the other operand, and the clear re-asserts. The ASIC SDC treats the
same pins as reset paths (`set_false_path`); the XDC already false-paths them. Waived at the CLR/PRE pins of those four chains.

**W4, level-held single bits (3 rows), accepted risk.** `ext_irq` (`|masked` in `interrupt_controller`), `timer_irq`
(`irq_en & irq_pending_q`) and the PLL-lock status (`~(rst & locked)`) are AND/OR functions of flops that are stable for many cycles,
feeding a 2-FF `cdc_sync`. A glitch needs two inputs to move in opposite directions in the same cycle; the cost is one spurious level
interrupt or status bit that software clears. Not a corruption of state, so accepted. Registering the function in the source domain is
optional hardening (owner: RTL).

## RTL findings (3 rows, not waived, STOP-and-report; owner: RTL orchestrator)

**F1 (CDC-10 x3). `pmu.sv` drives the CPU-domain synchronisers from a combinational decode of a multi-bit binary state.**
`clk_en_w`, `iso_en_w` and `rst_n_w` are `unique case (dom_state_q[d])` decodes of the 4-bit sequential-binary `pmu_dom_state_e`
(`DOM_ON=0 .. DOM_PU_ISO=8`) and go straight to `soc_top.sv`: `~pmu_cpu_clk_en` -> `u_cpu_clk_dis_sync.d_i`, `pmu_cpu_iso_en` ->
`u_cpu_iso_en_sync.d_i`, and `pmu_cpu_rst_n` -> the **asynchronous clear** of `u_cpu_pmu_rst_sync`.
Netlist evidence (routed `nv7`): the three driving cells are `LUT4` / `LUT3` / `LUT4` whose inputs are `dom_state_q_reg[0][3:0]` and
nothing else (`u_pmu/sync_q[0][0]_i_1__14`, `u_pmu/regs[2][2]_i_1`, `u_pmu/g_stage[0].g_first.sync_q[0]_i_1__2`). The ASIC SDC comment
that these are "direct RTL passthroughs" is true of `soc_top.sv` but not of the logic behind `pmu.sv`'s outputs.
Hazard: when several state bits change on the same edge, the decode can pass through an intermediate code, because the bits reach the LUT
with different skew. Intermediate codes that decode to a different value while source and destination state agree (enumerated from
the `pmu.sv` case table):

| Transition | bits flipped | glitchable output | wrong intermediate states |
|---|---:|---|---|
| `PD_SAVE -> PD_ISO` (1 -> 2) | 2 | `clk_en` low | 3 |
| `PD_GATE -> OFF` (3 -> 4) | 3 | `clk_en` low, `iso_en` low | 0,1,2,6,7 / 0,1 |
| `PU_RST -> PU_CLK` (5 -> 6) | 2 | **`rst_n` low** | 4 |
| `PU_RESTORE -> PU_ISO` (7 -> 8) | 4 | `clk_en` low, **`rst_n` low** | 3,4,5 / 4 |

The `rst_n` cases land on an asynchronous clear (a runt pulse resets the CPU domain after it was released, mid power-up), the `clk_en` cases
gate the CPU clock for a cycle, the `iso_en` case clamps the CPU->fabric AXI handshake for a cycle (a dropped `valid`). These need a PMU power
cycle to occur, which only a firmware-initiated `MODE_CPU_OFF`/`MODE_NORMAL` does (bead 2k8: live power-cycling is untested). The
structure is proven in the netlist; a glitch is not demonstrated (zero-delay simulation cannot show it and there is no board). The
identical RTL is in the ASIC, so this also applies to the Sky130/ASAP7 flows, where it is invisible to the SDC exceptions.
Fix request (RTL, not done here): register `clk_en_w` / `iso_en_w` / `rst_n_w` in the PMU's own clock domain (or encode `dom_state_q`
one-hot / gray so every transition flips one bit and the decode of an unchanging output is hazard-free), keeping the UPF-mandated
sequence order unchanged; the cdc_sync stages are already there. A registered output delays each action by one cycle, which the
`pmu` and `soc_top` ordering tests must re-check. When fixed, `cdc_gate.py --strict` must pass and `RTL_OPEN` in `tools/fpga/cdc_gate.py`
is emptied.
`NV_CDC_WAIVE_RTL_OPEN=1` (for `build.tcl`) applies a clearly labelled TEMPORARY waiver for these three rows, only to demonstrate the
"everything else closed" state; the default build does not.

## Constraints: what mirrors the ASIC SDC

| ASIC SDC (`phase5_soc_multiclock_check.sdc`) | `nexys_video_cdc.xdc` |
|---|---|
| sec 10: domain-wide `set_max_delay 0.9 x dst period` each way | same, `-datapath_only` (Vivado requires `-from`) |
| sec 11: 10 gray-pointer crossings, 0.5 x dst | same, first-stage D pins; **new:** `set_bus_skew` 0.5 x dst on the same 10 buses |
| sec 12/12a: `req_q`/`ack_q` level crossings, 1 x dst | same (`u_apb_pll2_cdc`, `u_apb_dbg_cdc`) |
| sec 13: `cpu_clk_dis_sync` 1 x dst; `iso_en`, `ext_irq`, `timer_irq` 1 x dst; `pmu_cpu_rst_n` false path | `cpu_clk_dis_sync` 1 x dst; the others are covered by the (tighter) 0.9 x domain bound; reset-sync CLR/PRE false paths |
| `set_clock_groups -asynchronous` | **not used**: it outranks `set_max_delay` in Vivado and would remove every crossing check |
| false paths on DFT / scan / `rst_n_i` ports | DFT tied off at the board top |

Both clocks are outputs of one MMCM today, so Vivado times them as related clocks: the setup side is replaced by the `-datapath_only`
budgets and the hold side between related clocks is still analysed (that is covered by WHS below). When the Si5351A makes them truly
independent, `set_max_delay -datapath_only` on unrelated primary clocks is the form AMD recommends and needs no change; the
`report_cdc` structure classification does not depend on the clocks being related ("No Common Primary Clock" is already what it
reports for the debug hub), so this triage carries over. Only a real second oscillator can exercise it.

## Result of this change

TBD-RESULT

## Reproduce

```bash
fpga/nexys_video/build.sh /nobackup/<out> all <tag>        # writes <tag>/cdc.rpt (waived), cdc_raw.rpt (no waivers), cdc_waived.rpt, waivers.rpt, bus_skew.rpt
python3 tools/fpga/cdc_gate.py /nobackup/<out>/<tag>/cdc.rpt            # PASS with the 3 RTL-owned rows listed
python3 tools/fpga/cdc_gate.py /nobackup/<out>/<tag>/cdc.rpt --strict   # fails until the PMU is fixed
```

Waivers can be re-checked on an existing checkpoint without a rebuild: `open_checkpoint routed.dcp; source nexys_video_cdc_waivers.tcl;
nv_cdc_waivers; report_cdc -details -file cdc.rpt` (the `-from *PIN` / `-to *PIN` wildcards make Vivado warn "list has >10000 objects"; harmless).
