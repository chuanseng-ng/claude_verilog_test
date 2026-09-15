# RVB — SRAM Write-Decode / GPU Read-Data Fan-out: Root Cause & RTL Fix Proposal

**Status: STUDY / PROPOSAL ONLY. No RTL was modified to produce this document.**
Any RTL change described below requires explicit human architecture approval per
`CLAUDE.md` ("RTL architecture changes need human approval") before an
`rtl-design-orchestrator` session may apply it.

- Bead under study: `claude_verilog_test-rvb`
- Physical-design investigation this builds on: `claude_verilog_test-w3a` (all
  quoted PD numbers below are w3a's, not re-derived here)
- RTL as of branch `feat/pd-w3a-bpp-86a-cleanup`, current HEAD at time of writing
- Target flow: ASAP7 SoC, `deferred_flatten` synthesis, `sys_clk` 1750 ps /
  `cpu_clk` 780 ps (`pnr/constraints/phase5_soc_multiclock.sdc`)

## 0. Two independent problems, one shared shape

w3a found **two** structurally similar but functionally distinct fan-out
problems on the ASAP7 `deferred_flatten` SoC netlist:

| | Path A (post-CTS setup) | Path B (post-GRT setup) |
|---|---|---|
| Worst endpoint | `u_sram._244155_/D` (one of ~32 768 behavioral-array bit-flops) | `u_bus.u_periph_bridge._18xx_/D` |
| Source | `u_gpu/m_axi_wvalid` (GPU AXI4 write-valid) | `u_gpu`'s AXI-Lite `s_axil_rdata[5]`/`[30]` |
| Reported symptom | baseline MET at +192.9 ps; resizer's own repair actions on *other* endpoints sharing the buffer tree degrade it and the repair oscillates without converging (deferred_flatten only — flat synthesis converges on the identical RTL) | honest post-GRT WNS ≈ −2078 ps / TNS ≈ −16.7 M ps / ~41.9k violators; post-GRT resizer repair gives no measurable gain |
| Mechanism class | **wide combinational fan-out** — one valid bit gates the write-enable of ~18.5k flop endpoints | **long, unregistered, high-capacitance point-to-point net** — a macro-boundary combinational mux feeding a far-away register with no pipeline stage in between |

Both are genuine single-cycle, functional combinational paths (w3a's own
conclusion, restated here): **neither is an SDC-exception ("multicycle" or
`false_path`) candidate.** This project already has a real precedent for a
*legitimate* multicycle exception — the CPU/GPU APB macro boundaries, where the
protocol itself stretches `PREADY` over multiple cycles
(`pnr/constraints/phase5_soc_multiclock.sdc:386-440`, `docs/design/SDC_TIMING_SPEC.md:404-408`
GPU register-file access). Neither Path A nor Path B has that protocol-level
justification: `s_wvalid`/`s_wready` and the AXI-Lite `RVALID`/`RDATA` handshake
in this design are both intended to be one AXI beat = one clock, and hiding
either path behind an SDC exception would misrepresent a real timing failure as
a false one. **SDC-only fixes are excluded from the shortlist below for this
reason**, per the explicit instruction not to recommend hiding a real
single-cycle path.

## A. Root-cause analysis

### A.1 Path A — `u_gpu/m_axi_wvalid` → `sram_controller` write-enable fan-out

**Full logical cone (file:line):**

1. `rtl/gpu/memory_coalescer.sv:134` — `m_wvalid_o = (state_q == S_W);`
   `m_wvalid_o` is a combinational one-term decode of the coalescer's FSM
   state register `state_q`; from a timing/fan-out standpoint it behaves as a
   registered source (one gate of decode off a flop), matching w3a's
   description of it as "the GPU macro's AXI write-valid output register."
   It is wired straight through `gpu_memory_unit.sv:96` and
   `rtl/gpu/gpu_top.sv:80,483` (`output logic m_axi_wvalid` /
   `.m_wvalid_o (m_axi_wvalid)`) to the GPU macro's `m_axi_wvalid` output pin
   with **no register added at the macro boundary**.

2. `rtl/soc/axi4_crossbar.sv:308-346` (`always_comb`, per-slave write engine),
   specifically:
   ```
   334   W_DATA: begin
   335       _s_wdata  [s] = m_wdata [wsel[s]];
   336       _s_wstrb  [s] = m_wstrb [wsel[s]];
   337       _s_wlast  [s] = m_wlast [wsel[s]];
   338       _s_wvalid [s] = m_wvalid[wsel[s]];
   339   end
   ```
   and `axi4_crossbar.sv:629` — `assign s_wvalid = _s_wvalid;`. `wsel[s]` is
   the per-slave grant register (set by the sequential grant FSM,
   `axi4_crossbar.sv:348+`), so this is a **combinational master-select mux**:
   for the SRAM slave slot, `m_wvalid[wsel[s]]` passes `m_axi_wvalid`
   straight through to `s_wvalid` (`bus_mem_wvalid` in `soc_top.sv`) with only
   mux/select logic in between — no register. w3a's OpenSTA trace of the real
   post-CTS netlist confirms this abstractly as "AOI31/NOR3/AND5" arbitration
   gates on this exact path.

3. `rtl/soc/sram_controller.sv:128` — `logic [DW-1:0] mem [0:MEM_WORDS-1];`
   (`MEM_WORDS=1024`, instantiated with this value from `soc_top.sv`'s
   `SRAM_MEM_WORDS` parameter) — a flat, unpacked array of 32-bit words. The
   module's own header (`sram_controller.sv:6-8`) already documents that this
   "synthesizes to ~32K flip-flops plus a huge combinational 1024:1 read mux";
   this bead extends that documented characteristic to the **write side**.

4. `rtl/soc/sram_controller.sv:188-206` (`W_DATA` state of the write FSM):
   ```
   188   W_DATA: begin
   189       if (s_wvalid) begin
   190   `ifndef SRAM_SKY130
   191           if (!w_err) begin
   192               for (int b = 0; b < SW; b++) begin
   193                   if (s_wstrb[b]) begin
   194                       mem[w_idx][b*8 +: 8] <= s_wdata[b*8 +: 8];
   195                   end
   196               end
   197           end
   198   `endif
   ```
   An indexed non-blocking assignment to an unpacked array inside a clocked
   `always_ff`, gated by `s_wvalid` (and `!w_err`, `s_wstrb[b]`), synthesizes
   to, per word `i` and byte `b`:
   `mem[i][b] <= (w_idx == i) && s_wvalid && s_wstrb[b] ? s_wdata[b] : mem[i][b]`
   i.e. a **per-bit load-enable mux** at every one of the 1024×32 = 32768
   storage bits, each of whose select term is a function of `s_wvalid`. Even
   with the best-case synthesis sharing (one `(w_idx==i)` decode term reused
   across a word's 4 byte lanes / 32 bits, so `s_wvalid` need only combine
   with 1024 word-level AND terms, not 32768 independently), `s_wvalid` is
   still, structurally, the single qualifying signal for *every* storage bit
   in the array — there is no register stage between "AXI master says write
   is happening this cycle" and "every one of 32768 flops decides whether to
   update." That structural property, not a coding mistake, is what produces
   the reported ≈18 584-endpoint fan-out cone once physical buffering
   (`repair_design`/resizer) legalizes it into a real tree.

**Why the fan-out size specifically, and why it stalls repair (not re-derived,
citing w3a):** the buffer tree built to legalize this fan-out is *shared*
across many of the 32768 sinks; the setup-repair algorithm's own buffer/clone
actions on *other* sibling endpoints on that shared tree collaterally degrade
`u_sram._244155_/D`'s slack, and repair oscillates trying to re-fix it without
escaping — confirmed non-terminating specifically on the `deferred_flatten`
netlist, though the identical fan-out structure exists in the `flatten`
netlist too (which converges). The `deferred_flatten`-vs-`flatten` difference
governs whether the *resizer's* algorithm can converge on this fan-out, not
whether the fan-out itself exists — it exists in the RTL regardless of
hierarchy mode.

### A.2 Path B — `u_gpu` AXI-Lite `s_axil_rdata` → `u_bus.u_periph_bridge` register

**Full logical cone (file:line):**

1. `rtl/gpu/gpu_top.sv:298-321` (`always_comb`, read-data mux):
   ```
   298   always_comb begin
   299       s_axil_rdata = 32'h0;
   300       case (ar_addr_q)
   301           12'h000: s_axil_rdata = {29'h0, r_irq_en_q, 2'b00};
   302           12'h004: s_axil_rdata = {29'h0, ...};
   ...
   319           12'h040: s_axil_rdata = perf_cnt_q[4];
   320           12'h044: s_axil_rdata = perf_cnt_q[5];
   ```
   `s_axil_rdata` is a **purely combinational, ~15-arm case-mux** over GPU
   internal registers (control/status regs, kernel launch params, 6 perf
   counters) with **no output register** — it is driven straight to the GPU
   macro's `s_axil_rdata` output port (`gpu_top.sv:47`).

2. `rtl/soc/soc_bus.sv:1262` connects the GPU's `s_axil_rdata` into
   `axi_lite_interconnect`'s ring-slave input (`bus_axil_gpu_rdata`), which is
   consumed by `rtl/soc/axi_lite_interconnect.sv:237,254`
   (`always_comb`, `m_axil_rdata = s_axil_rdata[rsel]`) — a second
   combinational mux, this time over the ring's 3 slaves (GPU, APB bridge,
   DMA), selected by a registered `rsel`.

3. `rtl/soc/axi4_to_axilite.sv:239,251,262,282` — the periph bridge
   (`u_bus.u_periph_bridge`, instantiated at `soc_bus.sv:497`) captures the
   ring's `m_axil_rdata` directly into a flop:
   ```
   239   logic [DW-1:0]   rdata_q;
   251   assign s_rdata  = rdata_q;
   ...
   282                       rdata_q <= m_axil_rdata;
   ```

So the full combinational cone from the GPU's internal registers to
`u_periph_bridge`'s `rdata_q` D pin is: **register → 15-arm case mux (GPU) →
3-way ring mux (interconnect) → register (periph bridge)**, with **zero
pipeline stages** across two muxes and (per w3a's physical trace) a long,
macro-to-fabric physical distance in between. w3a's live path trace (already
performed, not re-derived here) found 4–6 chained buffers per bit at
**686–1430 fF**, vs 10–50 fF typical elsewhere in the design — i.e. this is
dominated by **wire/physical distance and the resulting buffer-chain depth**,
not sheer logical fan-out count (each `rdata` bit ultimately drives exactly
one downstream flop). The failure mode w3a diagnosed is specific to
`repair_timing`'s own default buffer-removal optimization (`-skip_buffer_removal`
not passed) acting on this long chain under GRT's more accurate parasitics:
removing a few interior buffers on a chain this heavily loaded dumps their
capacitance onto the survivors and collapses delay across every bit/instance
sharing the physical route (this is why many different `_1819_/_1827_/_1844_`
periph-bridge bit instances trade off being "worst" over the run, not one
fixed net).

**Key structural point for the RTL fix:** unlike Path A (fan-out breadth),
Path B is a **missing pipeline register at (or near) a macro boundary on a
long, physically-distant net**. The fix shape is different: Path A needs the
fan-out *source* broken into narrower, independently-timed branches; Path B
needs a *register inserted somewhere along the single long branch* so no one
combinational segment has to cover the full macro-to-fabric distance in one
cycle.

## B. Candidate fixes

### B.1 Path A — SRAM write-enable/index-decode fan-out

| # | Option | RTL sketch (NOT applied) | Functional / verification impact | Expected timing effect | Area/power | Risk | Locked-decision conflict |
|---|---|---|---|---|---|---|---|
| A1 | **Register the write commit one cycle deep** (pipeline `w_idx`/`s_wdata`/`s_wstrb` into a `W_COMMIT` stage before touching `mem[]`) | Add `wcommit_valid_q/wdata_q/wstrb_q/widx_q` captured in `W_DATA` on `s_wvalid`; move the `mem[w_idx][...] <= ...` loop to fire off the *_q registers one cycle later; `s_wready` still asserts every cycle in `W_DATA` (no extra backpressure) since the FSM just delays the *effect*, not the AXI acceptance — `s_bvalid` must wait one extra cycle after `s_wlast` is captured | +1 cycle write commit-to-visible latency (a read immediately following a write to the same address must now either stall or bypass — **needs a genuine read-after-write hazard check against `sram_controller`'s existing read FSM**, which currently reads `mem[r_idx]` combinationally with 0 extra latency); AXI4 protocol itself is unaffected (WVALID/WREADY/BVALID timing relationship is a controller-internal choice, not visibly broken to the crossbar) provided BRESP is delayed to match; **verification**: `tb/cocotb/soc/test_sram_controller.py` (all write-then-read-back tests), `soc_all` end-to-end (any firmware relying on same-cycle-visible SRAM writes), crossbar write-channel tests | Breaks `s_wvalid`'s combinational reach at the sram_controller boundary — the fan-out tree now roots at a *local* register inside `sram_controller`, not at the far-away GPU macro's `m_axi_wvalid`; does not by itself reduce endpoint count (still ~32768 flops), only shortens/re-roots the tree so CTS/resizer see it as an ordinary intra-module fan-out, closer to where it's consumed | +1 FF per write-data/addr bit (~64 FF), negligible power | Medium — a same-address RAW hazard bug is easy to introduce silently; must be proven by directed cocotb test, not just regression pass | **None** — keeps the flat behavioral array; fully consistent with Phase 5 M6's locked "behavioral SRAM for Phase 5" decision |
| A2 | **Pre-decoded, registered one-hot word-select** (decode `w_idx` into a registered 1024-bit one-hot vector *ahead* of `s_wvalid`, reuse per-word) | At `W_IDLE→W_DATA` transition (when `w_idx` is captured from `s_awaddr`), also register `word_sel_q[1024]` as a one-hot decode of `w_idx`; in `W_DATA`, compute `word_we[i] = word_sel_q[i] & s_wvalid & !w_err` (1024 AND2 gates) and gate all 32 bits of `mem[i]` from the single `word_we[i]`, reusing it across the 4 byte lanes instead of recomputing `(w_idx==i)` per bit | Zero added AXI latency (index decode happens during the address phase, which already exists a cycle ahead of data); same RAW semantics as today (write is still visible the cycle `s_wvalid` fires) — **lower functional risk than A1**; verification: same suites as A1 but no new latency-dependent test vectors needed, mainly a resynthesis/lint check that `word_we[i]` is correctly shared | Reduces `s_wvalid`'s *direct* fan-out from (worst case) 32768 to 1024 — a ≥16–32× reduction at the AND-gate level, and gives CTS/resizer 1024 independently-timed downstream branches instead of one shared tree; total flop count unchanged | +1024 FF (one-hot register) + 1024 AND2 gates; more area than A1 (a full one-hot register vs ~64 latched bits), but avoids sequencing complexity | Low-medium — requires care that `word_sel_q` is correctly re-decoded/held for burst writes (`w_idx` increments mid-burst under `w_incr`, so `word_sel_q` must track it, effectively becoming a shift/increment of the one-hot register — non-trivial for INCR bursts) | **None** — same behavioral-array model |
| A3 | **Real SRAM macro for ASAP7 (extend the existing `SRAM_SKY130` pattern)** | Add an `ASAP7`-side `ifdef`/parameter arm mirroring `sram_controller.sv:110-243`'s existing `SRAM_SKY130` structure, backed by `sram_1rw_256x32_asap7` (already qualified and used by the CPU/GPU caches, per `docs/design/PHASE5_SOC_INTEGRATION_PLAN.md` and `pnr/asap7/{cpu,gpu}/config.json`) or a small bank of them (1024×32 needs 4× the 256-deep macro, banked) | The macro model already has its own read-latency contract (2-cycle negedge-launched read per `sram_controller.sv:304-344`'s `SRAM_SKY130` arm) — write-side latency for a real 1RW SRAM macro is typically single-cycle-committed (no visible extra latency), so functional/AXI impact is likely *smaller* than A1/A2 for writes, but this needs an ASAP7-specific read-latency contract to be designed (may or may not match Sky130's 2-cycle quirk); verification: full new `test_sram_controller.py` macro-mode matrix (mirroring the existing `SRAM_SKY130` cocotb coverage), `soc_all`, crossbar tests, plus a genuinely new PD macro-integration/characterization pass (LEF/LIB, macro placement, PDN) | Eliminates the ~32768-flop write-decode and the 1024:1 read-mux **entirely** — replaces both with the macro's own internal decode (opaque to synthesis, characterized once via Liberty), which is the most robust structural fix for both Path A and (indirectly) SRAM read timing | Most robust; but adds real macro area/power (own Liberty numbers) instead of ~32K DFF + combinational logic — direction of area/power delta depends on macro efficiency vs standard-cell flop array (likely net area win, since a real SRAM macro is far denser than 32K DFF) | **Highest effort** — needs macro selection/banking for 1024 words (macro is 256 deep), new LEF/LIB views, PDN/macro-placement work (bead `86a`'s own experience with macro power/timing view generation is directly relevant), and is the largest RTL delta of the five options | **Tension with the locked decision**: `CLAUDE.md` / `docs/PHASE5_SOC_INTEGRATION_PLAN.md` M6 explicitly locked "behavioral SRAM for Phase 5" (real DRAM/macro deferred to Phase 6+). This option does not touch DRAM, but it *does* replace the flat behavioral array with a hard macro for ASAP7 — a real architecture-decision reopening, not a Phase-5-scope tweak |
| A4 | **`$mem`-inferable memory instead of per-bit flops** (restructure the array so yosys infers a `$mem`/RTL memory object PD can map to a memory-compiler macro or a fully synthesized single-port RAM, rather than 32K discrete DFFs) | Likely requires removing the per-byte-strobe partial-write pattern (`mem[w_idx][b*8+:8] <= ...` inside a loop) in favor of a single full-word masked write yosys's memory inference recognizes, and possibly restructuring the reset behavior (yosys `$mem` inference is sensitive to whether the array is ever reset — this array is *not* reset today, which is actually favorable for inference) | Functionally equivalent if done correctly; verification: identical suites to A1/A3, plus a **synthesis-level check** (yosys `memory_collect`/`memory_dff` passes, or a `stat` dump) that inference actually happens — this option's benefit is entirely contingent on confirming inference occurs, which was flagged in this task as needing verification and was not empirically confirmed in this session (see §E) | *If* `$mem` inference succeeds and LibreLane/Yosys maps it to a real RAM primitive or SRAM-compiler macro, this fully removes the fan-out (same end-state as A3 via a synthesis-flow lever instead of an RTL macro instantiation); *if* it only produces a synthesized (flip-flop-based) memory the tool can't map to a macro, there is **no timing benefit at all** over today's RTL — ASAP7 has no synthesizable-memory-compiler path in this flow today | Unknown until confirmed working — potentially the best area/power outcome (dense RAM primitive) or no improvement at all | **High** — behavior is toolchain/PDK-dependent and unconfirmed for ASAP7 in this flow; do not rely on this without a synthesis experiment proving inference occurs (this proposal recommends investigating it, not adopting it blind) | **None outright** (still a "behavioral" description in RTL), but if it resolves to a real SRAM-compiler macro it has the same tension as A3 |
| A5 | **SDC `set_max_fanout`/multicycle exception targeted at this net class** | e.g. a tighter `set_max_fanout` on `s_wvalid`-derived nets, or a multicycle on the crossbar→SRAM write path | None to RTL; but per w3a's own conclusion this is a genuine single-cycle `s_wvalid`-gates-a-real-write-commit path — a multicycle exception would be **functionally incorrect** (the write really does commit in one cycle per AXI4) | The existing global `MAX_FANOUT_CONSTRAINT=16` is already respected at every individual buffer stage (w3a: "the problem is tree depth/breadth in aggregate, not any single illegal-fanout node") — a net-specific fanout cap would only force *more* buffer stages into the same shared tree, which is the mechanism already causing the oscillation, not a cure for it | N/A | **Not recommended** — explicitly excluded per task instruction not to hide a real single-cycle path | N/A (SDC-only, but the wrong kind of SDC-only) |

### B.2 Path B — GPU AXI-Lite read-data fan-out into `u_periph_bridge`

| # | Option | RTL sketch (NOT applied) | Functional / verification impact | Expected timing effect | Area/power | Risk | Locked-decision conflict |
|---|---|---|---|---|---|---|---|
| B1 | **Register `s_axil_rdata` inside `gpu_top` (macro-boundary register)** | Add a flop capturing the `always_comb` case-mux output (`gpu_top.sv:298-321`) on the cycle the AR address is accepted, so `s_axil_rdata`/`s_axil_rvalid` present one cycle after `ar_cap_q` today's combinational cycle — i.e. add a genuine extra AXI-Lite read latency (`RVALID` one cycle later than `ARVALID`&`ARREADY`) | AXI-Lite protocol is fully compliant with an extra latency cycle (AXI4-Lite has no fixed-latency requirement, only VALID/READY handshake rules) — but this is a **GPU macro boundary change**: the macro must be re-hardened (re-run GPU-block synthesis/PD, re-characterize timing) since its I/O timing contract changes; verification: GPU AXI-Lite register-access cocotb tests (any GPU ctrl-register read test with a fixed expected-latency assumption), `soc_all` (periph read paths through the ring), `test_axi_lite_interconnect`/`test_axi4_to_axilite` if they assume the old latency | Moves the register from `u_periph_bridge` (far side) to inside the GPU macro (near side) — this shortens the *unregistered* combinational span from "two muxes across the whole macro-to-fabric distance" to "one clean 3-way ring mux only," and gives CTS a real register boundary at the macro pin instead of a raw comb output, letting the buffer-chain-heavy segment be split at the actual clock edge instead of purely as an optimization artifact | +32 FF inside GPU macro; negligible | **Medium-high** — this is a macro re-harden, not a leaf-module edit; per the GPU's own PD history (`docs/PHASE5_RUN_HISTORY.md` GPU macro boundary caveats, bead `cyb`/`g0o` class of finding) touching a macro's registered I/O contract has previously had ripple effects on macro pin ordering/timing views that needed dedicated fixing | None — GPU behavioral semantics unchanged, purely a macro-boundary pipeline register |
| B2 | **Register `m_axil_rdata` inside `axi_lite_interconnect` (ring-level register, not macro-internal)** | Add a flop after the `rsel`-based mux (`axi_lite_interconnect.sv:254`) so `m_axil_rdata` is registered before leaving the interconnect, rather than mux'd combinationally straight through | Adds one cycle of read latency on the ring→periph-bridge leg only (GPU/DMA/APB-bridge internal timing unaffected); **no macro re-harden needed** (interconnect is ordinary flat RTL, not a macro) — cleanest scope of the three register options; verification: `test_axi_lite_interconnect` (latency-sensitive assertions), `test_axi4_to_axilite`, `soc_all` periph-read regression | Same effect as B1 on the downstream (`u_periph_bridge`) side — the combinational span from GPU's comb mux output to the fabric register is unchanged in length (still crosses the physical macro-to-fabric distance combinationally) **unless** the new register is physically placed close to the GPU macro's output; if placed near the ring interconnect's own location (likely far from the GPU macro, near the rest of the fabric) it does **not** shorten the long, high-capacitance segment w3a measured — it only adds a register *after* it, which does still break the specific "unregistered all the way from GPU regs to periph_bridge's D pin" property, converting one long combinational hop into two, each roughly half the distance (better, though less clean structurally than B1) | +32 FF, negligible | Low — purely a leaf-RTL change in a non-macro module | None |
| B3 | **Register `s_rdata`/`m_axil_rdata` input at the periph bridge (add a stage *before* `rdata_q`, i.e. a 2-deep pipeline)** | In `axi4_to_axilite.sv`, add an extra flop ahead of the existing `rdata_q <= m_axil_rdata` (`axi4_to_axilite.sv:282`), i.e. `rdata_stage_q <= m_axil_rdata; rdata_q <= rdata_stage_q;` | Same AXI-Lite latency-cycle impact as B1/B2 but adds it at the consuming end instead of the source; simplest possible code change (one new register in an existing module, no macro boundary, no interconnect logic change) — verification identical scope to B2 | **Does not address the root cause**: the long, high-capacitance, unregistered span is *before* this point (GPU comb mux → ring comb mux); adding a register after both muxes only means `u_periph_bridge`'s *own* input register now samples the same over-loaded combinational net one cycle later — it does not shorten or re-root the segment w3a measured at 686–1430 fF, so timing benefit is doubtful | +32 FF, negligible | Low implementation risk, but **high risk of not fixing the actual timing problem** — listed for completeness, not recommended | None |
| B4 | **AXI-Lite skid/register slice on the ring's GPU-facing port** (a generic 1-deep skid buffer module inserted between GPU's `s_axil_*` and the ring, on both AR/R directions) | Instantiate a small skid-buffer wrapper around the GPU's AXI-Lite slave ports at the `soc_bus.sv` boundary (structurally similar to B1 but implemented as a *separate, reusable* module rather than a change inside `gpu_top`) | Functionally equivalent to B1 (extra read latency, AXI-Lite compliant) but **avoids editing/re-hardening the GPU macro itself** — the skid buffer lives in `soc_bus.sv`/fabric RTL, outside the macro boundary; this is the best of B1's timing benefit and B2/B3's "no macro re-harden" property, at the cost of an extra small module; verification: new skid-buffer unit test + same `soc_all`/ring-suite regression as B1/B2 | If the skid buffer is placed physically adjacent to the GPU macro's pins (achievable via macro placement / `pnr/asap7/soc/macro_placement.cfg` proximity, not an RTL concern), this gets the same "break the long span near its source" benefit as B1 without touching the macro's own synthesized boundary | +32-64 FF (skid buffer control + data), negligible | Medium — new shared module needs its own verification and correct READY/VALID skid semantics (get this wrong and it's a functional bug, not just a timing fix) but avoids the macro-re-harden risk of B1 | None |
| B5 | **SDC-only (multicycle on the GPU AXI-Lite read path)** | `set_multicycle_path -setup 2 -to [get_pins u_bus.u_periph_bridge.rdata_q*/D]` style exception | None to RTL | Would hide a real single-cycle AXI-Lite `RVALID`/`RDATA` timing requirement — **not functionally legitimate** unless the RTL is *first* changed (B1/B2/B4) to genuinely take 2 cycles, at which point the SDC exception would document a real 2-cycle contract rather than paper over a 1-cycle violation. As a standalone fix with no RTL change, this is excluded for the same reason as A5. | N/A | Not recommended standalone | N/A |

## C. Recommendation

### C.1 Ranked shortlist

| Path | Rank 1 (minimal risk) | Rank 2 | Rank 3+ |
|---|---|---|---|
| A (SRAM write fan-out) | **A2** (registered one-hot word-select) — zero added AXI latency, contained to `sram_controller.sv`, keeps the locked behavioral-SRAM decision fully intact | **A1** (pipelined write commit) — simplest code change, but the RAW-hazard-vs-latency question needs a directed test before trusting it | A4 (`$mem` inference) as a **parallel investigation**, not a committed fix, since its payoff is unconfirmed; A3 (real macro) only if Phase 5's locked decision is deliberately reopened for a Phase 6+-style effort |
| B (GPU rdata fan-out) | **B2** (register inside `axi_lite_interconnect`) — no macro re-harden, contained to non-macro fabric RTL, directly shortens the reported long span | **B4** (skid buffer at the ring boundary) — better physical outcome than B2 if macro-adjacent placement is confirmed feasible, at the cost of a new module | B1 (register inside the GPU macro) only if B2/B4 turn out insufficient once re-measured, given its macro-re-harden cost |

Both A2 and B2 share the property the task asked to prioritize: they are the
smallest RTL deltas that address the *actual* mechanism (fan-out breadth for
A2; missing pipeline register on a long span for B2), stay inside
already-flat (non-macro) RTL, and require no PD macro-characterization work.

### C.2 Approval required

**All of A1–A4 and B1–B4 are RTL architecture changes and need explicit human
approval before any `rtl-design-orchestrator` session implements them**, per
this task's constraint and the project's standing rule. Within that:

- A2, A1, B2, B3, B4 are **functional-behavior-preserving, non-macro** RTL
  edits — the smallest category of approval (protocol timing changes only:
  +1 cycle write-commit visibility for A1, +1 cycle AXI-Lite read latency for
  B2/B3/B4). A2 does not even add latency.
- A3 additionally requires reopening the **locked Phase 5 architecture
  decision** ("behavioral SRAM for Phase 5", `CLAUDE.md` / M6 in
  `docs/PHASE5_SOC_INTEGRATION_PLAN.md`) — this needs a distinct,
  explicit sign-off beyond ordinary RTL review, since it contradicts a
  decision the project record treats as closed for this phase.
- A4 needs a **synthesis-behavior investigation** (does yosys actually infer
  `$mem` for this array under the current LibreLane ASAP7 flow?) before it is
  even a fix candidate, not just an approval.
- B1 additionally implies **GPU macro re-hardening** (re-synthesis, re-PD,
  re-characterization of the GPU block) — a materially larger PD effort than
  B2/B3/B4, comparable in kind (though smaller in scope) to A3's macro work.
- A5 and B5 (SDC-only) are **not recommended at all** and are listed only to
  document why they were rejected, per the task's explicit instruction.

### C.3 Verification plan (once an option is approved and implemented)

1. `chip-design-rtl:rtl-design-orchestrator` lint/CDC pass on the modified
   file(s) (`sram_controller.sv` for A-options; `axi_lite_interconnect.sv` /
   `axi4_to_axilite.sv` / `gpu_top.sv` for B-options).
2. Directed cocotb: `tb/cocotb/soc/test_sram_controller.py` (write-then-read,
   burst writes crossing the new pipeline stage, byte-strobe partial writes)
   for A-options; the periph-ring read suites
   (`test_axi_lite_interconnect`, `test_axi4_to_axilite`) plus GPU ctrl/perf
   register reads for B-options.
3. Full `soc_all` regression (currently 183/183 per `CLAUDE.md`) — the
   authoritative check that added latency does not break any firmware/test
   sequencing assumption.
4. `chip-design-verification:verification-orchestrator` for any suite that
   encodes a fixed-latency assumption on SRAM writes or GPU AXI-Lite reads
   (these are the tests most likely to need updating, not just re-running).
5. Only after (1)-(4) are green: hand back to
   `chip-design-pd:physical-design-orchestrator` for a fresh
   synthesis→CTS→post-CTS/post-GRT resizer run on the current
   `deferred_flatten` ASAP7 SoC config, to confirm the specific endpoints
   (`u_sram.*`/`u_bus.u_periph_bridge.*`) actually move.

### C.4 PD re-run scope

A resynthesis is required either way (the fan-out structure is a function of
the netlist, not seedable from an existing checkpoint) — **not** a `--from`
resume of run 8/w3a's existing runs. Expected affected stages: Yosys synthesis
→ floorplan/placement (unchanged shape, but new gate count/structure) → CTS →
`ResizerTimingPostCTS`/`ResizerTimingPostGRT` (the actual stages this bead is
about). Given the current host-RAM constraint that motivated
`SYNTH_HIERARCHY_MODE=deferred_flatten` in the first place (bead `je8`/`2kn`),
re-verify the RTL change does not itself trip the same ABC memory ceiling
before committing to a `deferred_flatten` re-run.

## D. Explicitly out of scope for this study

- No RTL was modified in `rtl/**` or `pnr/**/*.sv`.
- No synthesis or simulation run was launched (per task constraints; a quick
  yosys elaboration check on `sram_controller.sv` alone was considered for
  option A4 but was not run in this session — see A4's own note that its
  benefit is unconfirmed and should be investigated before being adopted).
- This document does not resolve `w3a`'s separate CTS clock-tree finding
  (`DESIGN_REPAIR_REMOVE_BUFFERS` / the `pll_clkgen_stub` boundary-buffer
  issue) — that is a distinct, already-diagnosed-and-fixed PD-side issue
  (confirmed working per w3a's 2026-09-15 18:21/18:26/18:37 comments) and is
  not an RTL fan-out problem.
