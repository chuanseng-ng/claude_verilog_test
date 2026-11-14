# Truth review: PMU, clock gate and SoC power integration chapters

Scope: working tree on `docs/pmu-chapters`. I read in full `rtl/soc/pmu.sv`, `rtl/mem/rv32i_clock_gate.sv`,
`rtl/soc/apb4_register_bank.sv`, `rtl/soc/cdc/cdc_sync.sv`, `rtl/soc/cdc/cdc_reset_sync.sv`, the PMU, clamp, reset-tree,
bridge and clock-gate parts of `rtl/soc/soc_top.sv`, `tb/cocotb/soc/tb_pmu.sv`, `test_pmu.py`, `test_soc_pmu_iso_ack.py`,
`test_soc_pmu_multiclock.py`, `test_clock_gate_scan.py`, `tb_clock_gate_scan.sv`, `tools/verif/mutate_pmu_iso_ack.py`,
`tb/tests/test_pmu_registered_outputs.py`, the two DFT-scan tests, `test_soc_gpu_isolation_via_pmu` with its firmware
(`integ_fw/gen_integ_hex.py::build_gpu_iso`), the header of `pmu_cycle_fw/gen_pmu_cycle_hex.py`, the MBIST force test,
the SCAN-claim part of `check_upf.py`, the four chapter files and `power.yaml`. I ran nothing: no simulation, no make, no
LaTeX, no mutation run. Every cycle count below is derived by hand from the RTL at the defaults
(`SYNC_STAGES_TO_CPU = SYNC_STAGES_FROM_CPU = 2`, `cdc_reset_sync STAGES = 2`). Edge names follow the TM: E0 is the edge at
which the CTRL write completes.

Count check: the DS chapter has 43 requirements (001-006, 020-029, 060-067, 100-109, 150-153, 180-184). All
`\cref`/`\reqref` targets used by the three chapters exist exactly once in the books.

## Findings (most harmful first)

### 1. WRONG: DS-PMU-100 "Clamp before reset and clock stop" is false outside the tested window
- **Where:** DS `power.tex`, DS-PMU-100 body and its `verify=`.
- **Current statement:** "While the clamp control in the CPU domain (`pmu_cpu_iso_en_sync`) is low, the PMU reset in the CPU domain (`pmu_cpu_rst_n_cpu_sync`) must be high and the enable of the CPU clock gate (`cpu_gated_clk_en`) must be high."
- **What the code shows:** `u_cpu_iso_en_sync` has `.rst_n_i (cpu_core_rst_n)`, so `cdc_sync` holds `pmu_cpu_iso_en_sync` at 0 while `cpu_core_rst_n` is low. `u_cpu_pmu_rst_sync` is a `cdc_reset_sync` whose only reset is `pmu_cpu_rst_n`; it asserts asynchronously with no clock. So in `test_dead_cpu_clock_does_not_hang_pmu` (CPU PLL reset held, PMU walks to `DOM_OFF` by the timeout) the code has `pmu_cpu_rst_n_cpu_sync = 0`, `pmu_cpu_iso_en_sync = 0` and `cpu_gated_clk_en = ~pmu_cpu_clk_dis_sync & pmu_cpu_rst_n_cpu_sync = 0`: both halves of the rule are broken. The test starts `IsoMonitor` only after the revival, and `_cpu_off_on_cycle` starts it after the synchroniser fill, so no test sees this. The same holds for any wait that ends by the timeout (the clamp has not been seen). The rule as written claims an invariant at all times.
- **Also:** the `verify=` cites `mutation:...::s04_ack_not_synchronised`. That mutant clocks the return synchroniser on `cpu_core_clk`; it does not break the order. By reading, it is killed only by INV4 ("ack changed off a core_clk edge") in `test_iso_before_reset_cpu_faster`, where 3 ns edges fall off the 7 ns grid. It belongs to DS-PMU-101 only.
- **Proposed rule:** "After the reset of the SoC has ended and the synchronisers of the CPU domain have filled, and while `cpu_core_rst_n` is high, the PMU reset in the CPU domain (`pmu_cpu_rst_n_cpu_sync`) must be low only while the clamp control in the CPU domain (`pmu_cpu_iso_en_sync`) is high, and the enable of the CPU clock gate (`cpu_gated_clk_en`) must be low only while `pmu_cpu_iso_en_sync` is high. The rule does not apply to a power-down in which a wait ended by the timeout."
- **Proposed verify:** drop `mutation:tools/verif/mutate_pmu_iso_ack.py::s04_ack_not_synchronised`; keep the rest.
- **Add to the Information note:** "While `cpu_core_rst_n` is low, `pmu_cpu_iso_en_sync` is held at 0, and the PMU reset can still assert in the CPU domain. The clamp is then off while the domain is in reset. The CPU domain is in reset by `cpu_core_rst_n` at the same time. No test runs the monitor in this state."

### 2. WRONG: DS-PMU-067 "No stale acknowledge" does not hold after a power-up that timed out
- **Where:** DS-PMU-067 body (second sentence); TM "Isolation handshake" paragraph, last sentence.
- **Current statement:** "The acknowledge must be low when the sequencer enters the isolation step."
- **What the code shows:** `pmu.sv`, `g_dom_seq` next-state: `DOM_PU_ISO: (!iso_ack_w[d] || wait_hit[d]) ? DOM_ON`. When the power-up wait ends by `wait_hit`, the acknowledge is still 1. In `g_ack_cpu` the flag clears when `dom_state_q[d] == DOM_ON && !dom_target_on[d]` (the start of the next power-down), and `DOM_PD_ISO: (iso_ack_w[d] || wait_hit[d]) ? DOM_PD_GATE` leaves the isolation step in one cycle on that stale acknowledge. `wait_active` is 0 because the ack is high, so `wait_hit` never fires and the flag is not set again. Result: after a timed-out power-up, the next power-down skips the handshake and STATUS bit 3 reads 0 at its end. The tests cover only the healthy RZ case (`test_pmu_back_to_back_no_stale_ack` with `ack_lat_i = 10`; the SoC test with live clocks).
- **Proposed rule:** "A power-down that starts directly after a power-up must not use the acknowledge of the earlier power-up. When the wait of the power-up ended with the release of the acknowledge, the acknowledge must be low when the sequencer enters the isolation step."
- **Proposed Information note (after the rule):** "When the wait of a power-up ends by the timeout, the acknowledge can still be high. The next power-down then leaves `DOM_PD_ISO` after one cycle without a new handshake. The flag `cpu_iso_ack_timeout` clears when that power-down starts and is not set again, so `STATUS` bit 3 does not show that the order of \reqref{DS-PMU-100} is not guaranteed. This is derived from the RTL. No test covers it."
- **TM, Isolation handshake paragraph, add at the end:** "After a power-up whose wait ended by the timeout, the acknowledge can still be high, and the next power-down does not wait (\reqref{DS-PMU-067})."

### 3. MISSING: the CPU clock runs while the CPU clamp is active, at the start of a power-down and at the end of a power-up
- **Where:** TM "What the suites do not prove" (third bullet); DS-PMU-182 Information; DS decision "Acknowledge from the CPU domain" (consequence paragraph); UM CPU procedure step 1.
- **Current statement (TM bullet 3):** only the case "A clamp that is released one edge early then exposes the held values on a clock that is still stopped."
- **What the code shows (derived at 1:1, equal phase):** power-down: `pmu_cpu_iso_en_sync` rises after E4; `cpu_gated_clk_en` falls after E8 (the async reset term, see finding 15). `cpu_gated_clk` therefore has edges E5, E6, E7 and E8 with the clamp active. Power-up: `pmu_cpu_rst_n_cpu_sync` rises after E3, `pmu_cpu_clk_dis_sync` falls after E4, so `cpu_gated_clk_en` rises after E4 and the first gated edge is E5; `pmu_cpu_iso_en_sync` falls after E6. Edges E5 and E6 run with the clamp active. The clamps in `soc_top` act only on the outputs of `u_cpu` (`cpu_bridge_s_{aw,w,ar}valid`, `_bready`, `_rready`). The inputs of `u_cpu` from `u_cpu_axi_cdc` (`*ready`, `bvalid`, `rvalid`) are not clamped. In these edges `u_cpu` can complete a handshake (for example `axi_arvalid_o` and `cpu_bridge_s_arready` both 1) that the bridge never sees, or take an R beat that the bridge does not pop because it sees `rready = 0`. With a faster CPU clock the window has more edges.
- **Proposed TM bullet (replace bullet 3):** "In a power-up the clock of the CPU domain starts before the clamp releases there. The derived waveform at 1:1 has two edges of `cpu_gated_clk` (E5 and E6) while `pmu_cpu_iso_en_sync` is still high. In a power-down the clamp is active for four edges (E5 to E8) before the clock stops. In these edges `u_cpu` sees the ready and valid inputs from `u_cpu_axi_cdc`, but the bridge sees the clamped valid and ready outputs of `u_cpu` as 0. A handshake that `u_cpu` completes in such an edge does not reach the bridge, so a request can be lost and a response can be taken twice. No test checks these edges. This is derived from the RTL. The other order, a clamp that releases before the clock starts, is harmless by the design argument: the held lines are sampled only by `cpu_gated_clk`, which cannot run before the reset release is seen in the CPU domain."
- **Proposed DS Information after DS-PMU-182:** "The clamp is active in the CPU domain for some edges of `cpu_gated_clk` before the clock stops, and again after the clock starts in a power-up. A bus handshake of the CPU in these edges does not reach the fabric. This is derived from the RTL."
- **DS decision "Acknowledge from the CPU domain", replace the last two sentences of the consequence with:** "A power-up needs no acknowledge for the order of the clamp release and the reset release. The design argument is that the lines that the clamp holds are sampled by `cpu_gated_clk`, which cannot run before the PMU reset is released in the CPU domain. This argument is not a test result. In the nominal order the clock runs for some edges while the clamp is still active (\cref{tm:mod:pmu})."

### 4. WEAK-VERIFY: DS-PMU-102 "Clock stop in reset" has no test that can fail
- **Where:** DS-PMU-102 `verify=` and Information.
- **Current:** `verify={test:...test_soc_pmu_multiclock.py::test_pmu_live_power_cycle; review}`; note "The live test checks that a counter that the CPU firmware keeps in SRAM does not move while the domain is off."
- **What the code shows:** remove the `pmu_cpu_rst_n_cpu_sync` term from `cpu_gated_clk_en` and derive the live test (CPU 3 ns, fabric 7 ns): `pmu_cpu_clk_en` falls one `clk_i` cycle (7 ns) before `pmu_cpu_rst_n` falls; the disable crosses two 3 ns ranks (at most 6 ns), so the clock is already stopped when the reset asserts. The test cannot fail. The counter reaches SRAM only by a D-cache write-back (AXI write), and the clamp forces `cpu_bridge_s_awvalid`/`_wvalid` to 0 while off, so a frozen SRAM counter does not show a stopped clock. The `soc_pmu_iso_ack` tests have the reset term case at 3x and 8x slower (one gated edge in reset without the term, derived), but their monitor does not look at clock edges and their CPU runs an all-zero ROM, so no state check fails either.
- **Proposed verify:** `[verify={review}]`
- **Proposed rule:** "With `dft_test_en`, `mbist_force` and `cpu_mbist_busy` low, `cpu_gated_clk` must have no rising edge while `pmu_cpu_rst_n_cpu_sync` is low." (The old wording "no MBIST run" is unclear, see finding 9: `mbist_force` can be high while no run can start.)
- **Proposed Information:** "The enable of `u_cpu_cg` contains `pmu_cpu_rst_n_cpu_sync`, so the rule holds by construction. No test fails when this term is removed. At the clock ratio of the live test the clock disable reaches the CPU domain before the PMU reset, so the clock stops without the term. The counter of the live test reaches SRAM only by a bus write, which the clamp blocks, so a frozen counter does not show a stopped clock. At 1:1 the derived waveform has the reset term stop the clock one edge before the clock disable arrives (\cref{fig:tm:mod:pmu:power-down}). \Reqref{DS-PMU-108} gives the MBIST and test-mode exceptions."

### 5. WRONG: TM "What a PMU power cycle does to the bridges" and UM CPU step 2: a debug access does not just wait
- **Where:** TM `power.tex`, paragraph "What a PMU power cycle does to the bridges"; UM `um:ch:power-integration:cpu` step 2.
- **Current statement:** TM: "A debug access that is in flight when the clock stops waits, because the bridge has no timeout." UM: "Make sure that no debug access into the CPU domain is in flight. The bridge `u_apb_dbg_cdc` has no timeout."
- **What the code shows:** `u_apb_dbg_cdc.m_rst_n_i = cpu_domain_rst_n`, which contains `pmu_cpu_rst_n_cpu_sync`. The PMU asserts `cpu_rst_n_o` one `clk_i` cycle after `cpu_clk_en_o` falls (`DOM_PD_GATE` lasts one cycle), and in the CPU domain the reset is asynchronous, so it can arrive even before the clock stop. `apb_cdc_bridge` S_REQ exits on `!m_rst_n_s` and sets `resp_pslverr_q <= 1'b1` (DS-CDC-103); a new request while `m_rst_n_s = 0` gets `req_fwd_q <= m_rst_n_s = 0` and an error (DS-CDC-102). So in a PMU power-down the access waits at most until the reset asserts, then ends with SLVERR, and while off every debug access ends with SLVERR. Per the CDC review, an access that completed at the destination just before the reset can still return an error.
- **Proposed TM text (replace the first four sentences of the paragraph):** "The PMU stops `cpu_gated_clk` and asserts `cpu_domain_rst_n`. In the CPU domain the reset arrives at most about one cycle of `clk_i` after the clock stops, and it can arrive first. The `m_*` face of `u_apb_dbg_cdc` runs on `cpu_gated_clk` and resets from `cpu_domain_rst_n`. A debug access in flight at a power-down waits while the clock is stopped and the reset is not yet asserted. When the reset asserts, the bridge ends the access with an error response (\reqref{DS-CDC-103}). The access can have completed in the CPU domain although the response is an error. While the domain is off, each new debug access ends with an error response (\reqref{DS-CDC-102})." Keep the sentences about `u_cpu_axi_cdc`.
- **Proposed UM step 2:** "Make sure that no debug access into the CPU domain is in flight. An access in flight at the power-down ends with an error response, and it can have completed in the CPU domain. While the CPU domain is off, each debug access ends with an error response."

### 6. WRONG: UM GPU step 3 gives a wrong reason; a GPU register access while off is lost
- **Where:** UM `um:ch:power-integration:gpu`, step 3.
- **Current statement:** "Do not read or write a GPU register while the GPU domain is off. The clamp holds the request of the GPU instruction fetch low, and a read does not complete."
- **What the code shows:** the clamp on `gif_axil_arvalid` acts on the GPU as a master (its instruction fetch). A CPU access to a GPU register goes to the GPU control slave (`gpu_top` `s_axil_*`, ring slot `AXIL_GPU`), which is not clamped. In `gpu_top`: `assign s_axil_awready = ~aw_cap_q;`, `assign s_axil_arready = ~ar_cap_q;`, `assign s_axil_rvalid = ar_cap_q;`, with `always_ff @(posedge clk or negedge rst_n)`. While the PMU holds `gpu_domain_rst_n` low, `ar_cap_q = 0`, so the slave shows `arready = 1` (it takes the address) and `rvalid = 0` forever. The address is not captured, so it is lost also after the power-up. (I did not check whether the ring has a timeout.)
- **Proposed UM step 3:** "Do not read or write a GPU register while the GPU domain is off. The control port of the GPU is held in reset with its clock stopped. It takes the address of an access but never returns a response, so the access does not complete and the bus master waits. The access is lost, also after the power-up."
- **Proposed new DS rule (optional, owner to approve, next free ID):**
  `\begin{requirement}{DS-PMU-185}{No GPU access while the GPU is off}` `[verify={review}]` "Software must not access a register of the GPU while the GPU domain is not on." with Information: "The control port of the GPU accepts an address while it is held in reset and never answers it. This is derived from the RTL."

### 7. WRONG: DS-PMU-106 includes a synchroniser that does not use `cpu_core_rst_n`
- **Where:** DS-PMU-106 body.
- **Current statement:** "The synchronisers that carry the PMU controls into the CPU domain must use `cpu_core_clk` and `cpu_core_rst_n`."
- **What the code shows:** three PMU controls cross into the CPU domain. `u_cpu_clk_dis_sync` and `u_cpu_iso_en_sync` use `cpu_core_clk`/`cpu_core_rst_n`. `u_cpu_pmu_rst_sync` (`cdc_reset_sync`) uses `.clk_i (cpu_core_clk)` and `.rst_n_i (pmu_cpu_rst_n)`; it has no `cpu_core_rst_n` input (the `soc_top` comment says so on purpose).
- **Proposed rule:** "The synchronisers `u_cpu_clk_dis_sync` and `u_cpu_iso_en_sync` must use `cpu_core_clk` and `cpu_core_rst_n`. The reset synchroniser `u_cpu_pmu_rst_sync` must use `cpu_core_clk`, with `pmu_cpu_rst_n` as its source reset. These three synchronisers must not use `cpu_gated_clk`. The clock-enable crossing must carry the inverted enable, so that its reset value lets the clock run."

### 8. WRONG: "the GPU flops have an asynchronous reset" / "nothing survives" ignores the vector register file
- **Where:** DS-PMU-180 Information ("The flops of the GPU have an asynchronous reset."); TM "Known limits" second paragraph ("The GPU flops have an asynchronous reset, so the domain reset clears them although the clock is gated."); TM "State of the domains" ("The GPU domain has an asynchronous reset. The domain reset clears its flops although its clock is gated."); UM GPU step 5.
- **What the code shows:** `rtl/gpu/vector_register_file.sv` stores `rf` in `always_ff @(posedge clk)` with no reset (`rst_n` is marked unused, "reserved for tb reset"). Every other `always_ff` in `rtl/gpu` has `posedge clk or negedge rst_n`. `shared_memory.sv` uses SRAM bank macros. So the vector registers (8 warps x 32 registers x 8 lanes) keep their content across a GPU power cycle in the model; the cited test reads only `GPU_CTRL.irq_enable` and `GPU_STATUS.done`.
- **Proposed DS-PMU-180 rule:** "Software must set up the GPU again after each GPU power-up. Software must not rely on any state of the GPU after a GPU power cycle."
- **Proposed DS-PMU-180 Information:** "The control flops of the GPU have an asynchronous reset, so the domain reset clears them although the clock is stopped. The test shows that `GPU_CTRL.irq_enable` and `GPU_STATUS.done` read 0 after the cycle, and that a second kernel runs. The vector register file has no reset, and the shared memory is made of SRAM banks that the domain reset does not reach. In the model both keep their content. The test does not read them."
- **Proposed TM sentence (both places):** "The control flops of the GPU have an asynchronous reset. The domain reset clears them although the clock is gated. The vector register file of the GPU has no reset, and the SRAM banks of the shared memory have no connection to the domain reset."
- **Proposed UM step 5:** "Set up the GPU again. The control registers of the GPU do not keep their values, for example `GPU_CTRL.irq_enable`. Do not rely on the vector registers or the shared memory either. The domain reset does not clear them, and no test shows their content."

### 9. MISSING: what an MBIST force does while the PMU holds the CPU domain off
- **Where:** DS-PMU-108 Information; DS-PMU-181 Information; TM "Clock enable of the CPU domain" last sentence.
- **Current statement:** DS: "A MBIST run opens the CPU clock gate. The PMU does not know about the run. No test covers the open gate while the PMU holds the CPU domain off." TM: "An MBIST run or a test mode therefore runs `cpu_gated_clk` while the PMU holds the CPU domain off."
- **What the code shows:** `cpu_cg_en = cpu_gated_clk_en | (MBIST_CPU ? mbist_force : 1'b0) | cpu_mbist_busy`. In `rv32i_cpu_top`: `assign mb_run_w = mbist_run_i & rst_n_i;`. While the PMU holds the CPU domain off, `cpu_domain_rst_n = 0`, so the CPU MBIST cannot start (and `cpu_mbist_busy` stays 0), but `mbist_force` still opens the gate. The CPU flops (`always_ff @(posedge clk_i)` with `if (!rst_n_i)`) then see clock edges with the reset low and reset: the state that the model otherwise keeps is lost, and no test is done. `test_mbist_cpu_macro.py::test_mbist_force_opens_the_closed_clock_gate` does show the force opening a closed gate, in a bench that mirrors `u_cpu_cg` with the PMU clock enable only (no PMU reset).
- **Proposed DS-PMU-108 Information (replace its first four sentences):** "The enable of `u_cpu_cg` also contains the MBIST terms `mbist_force` and `cpu_mbist_busy`, and the PMU does not know about them. While the PMU holds the CPU domain off, `mbist_force` opens the CPU clock gate although `cpu_domain_rst_n` is low. The CPU MBIST cannot start then, because `rv32i_cpu_top` gates `mbist_run_i` with its reset. The forced clock edges reach the CPU flops while their reset is low, so the CPU loses the state that the model otherwise keeps (\reqref{DS-PMU-181}). The test `test_mbist_force_opens_the_closed_clock_gate` shows that `mbist_force` opens a closed gate, in a bench that mirrors `u_cpu_cg` without the PMU reset. No SoC test covers an MBIST request while the PMU holds the CPU domain off." Keep the scan sentences.
- **Proposed DS-PMU-181 Information, add:** "The exception is a CPU clock gate that `dft_test_en` or `mbist_force` opens while the PMU reset is asserted (\reqref{DS-PMU-108}). The CPU flops are then reset."
- **Proposed TM last sentence:** "An MBIST force or a test mode therefore runs `cpu_gated_clk` while the PMU holds the CPU domain off. The CPU flops then see clock edges while `cpu_domain_rst_n` is low, and they reset. The CPU MBIST cannot start in this state, because `rv32i_cpu_top` gates `mbist_run_i` with its reset."

### 10. UNCLEAR: polling for the whole STATUS value never ends when bit 3 is set
- **Where:** DS-PMU-184 rule and Information; UM GPU steps 2 and 4; UM checklist line 4.
- **Current statement:** DS: "software must poll `STATUS` for the value that shows the target". UM: "Read `STATUS` until it equals 0x1", "read `STATUS` until it equals 0x3".
- **What the code shows:** `hw_wdata[1] = {28'b0, cpu_iso_ack_to_q, pmu_busy, gpu_domain_on, cpu_domain_on}`; bit 3 is sticky until the next CPU power-down. After any timed-out CPU wait, STATUS reads 0x9 or 0xB in these states, and `gen_integ_hex.py::poll(..., extra_eq=...)` compares the whole word (`BEQ`), so it would end in FAIL.
- **Proposed DS-PMU-184 rule:** "After a write to `CTRL`, software must poll `STATUS` until bits 2 to 0 show the target, and must not poll for `busy` alone."
- **Proposed DS-PMU-184 Information, add:** "Bit 3 is the sticky flag of the CPU domain. A poll that compares all of `STATUS` never ends while bit 3 is 1. The firmware of the integration test compares all of `STATUS`, which works only because no wait timed out before it."
- **Proposed UM step 2:** "Read `STATUS` until bits 2 to 0 equal 0b001. This value shows the CPU domain on, the GPU domain off and `busy` low. Bit 3 can be 1 from an earlier CPU power cycle, so mask it. Do not poll for `busy` alone. ..." (keep the lag sentence). **Step 4:** "... and read `STATUS` until bits 2 to 0 equal 0b011." **Checklist:** "Firmware polls bits 2 to 0 of `STATUS` for the settled value after a write to `CTRL`."

### 11. INCONSISTENT: UM CPU procedure steps 3 and 4, and DS-PMU-183 Information, mix up the power-down request and the wake-up
- **Where:** UM `um:ch:power-integration:cpu` steps 1, 3, 4 and the sentence after the procedure; DS-PMU-183 Information.
- **Current statement:** step 3 "Arrange the wake-up before the power-down. Program another master, for example the DMA engine, to write `CTRL`. The reference firmware programs the DMA engine to write the mode CPU\_OFF." Step 4 "Write the mode." DS Information: "The reference firmware programs the DMA engine to write `CTRL` before the power-down."
- **What the code shows:** `gen_pmu_cycle_hex.py` header: the DMA write *is* the power-down request ("It programs the DMA engine ... to write MODE_CPU_OFF into PMU CTRL"), and "The CPU does not write PMU CTRL (0x2000_8000) itself: the write could land as the CPU clock is about to be gated." The firmware programs no wake-up; the test wakes the CPU by a deposit into `u_pmu.u_regbank.regs[0]`. The firmware also does not stop its traffic: its loop flushes the D-cache in each pass, and the test comment says a response was still in the bridge at the power-down. So step 4 "Write the mode" (by the CPU) is the untested path, and step 3 presents the power-down request as the wake-up.
- **Proposed UM procedure:**
  1. "Stop the AXI traffic of the CPU and flush the data cache. The PMU has no drain step. While the clamp is active and the clock still runs, a bus handshake of the CPU does not reach the fabric."
  2. (finding 5 text)
  3. "Arrange the wake-up before the power-down. Program another master, for example the DMA engine, to write the mode NORMAL into `CTRL` after the power-down. Without a wake-up write, only a reset of `rst_n_i` and `cpu_rst_n_i` together returns the CPU domain. No test wakes the CPU domain by a bus write."
  4. "Request the mode CPU\_OFF. The reference firmware \src{tb/cocotb/soc/pmu_cycle_fw/gen_pmu_cycle_hex.py} does not store to `CTRL` itself. It programs the DMA engine to copy the mode CPU\_OFF into `CTRL`, so that its own store is not in flight when its clock stops. A store of the CPU to `CTRL` is not tested."
  5. "After the wake-up, read `STATUS` bit 3. A value of 1 means that a wait for the clamp timed out, and the order of the clamp and the reset is not guaranteed for that power cycle."
  - After the procedure: "The reference firmware is a test of the model. It does not stop its traffic: its loop flushes the data cache in each pass. The tests wake the CPU domain by a deposit into the storage flop of `CTRL`."
- **Proposed DS-PMU-183 Information:** "Nothing inside the CPU domain can request a power-up. The reference firmware uses the DMA engine to write the mode CPU\_OFF, not to wake the domain. The tests wake the domain by a deposit into the register. No test wakes the CPU domain by a bus write."

### 12. UNCLEAR: DS-PMU-183 "only a chip reset returns the domain" - which reset?
- **Where:** DS-PMU-183 rule; TM Known limits ("A chip reset also returns the domain."); UM checklist line 6.
- **What the code shows:** the SoC has two reset pins. `rst_n_i` gives `core_rst_n` (PMU, fabric); `cpu_rst_n_i` gives `cpu_core_rst_n`. A reset of `rst_n_i` alone resets the PMU to NORMAL (all outputs to the `DOM_ON` values at one edge), but `cpu_domain_rst_n = cpu_core_rst_n & pmu_cpu_rst_n_cpu_sync & wdt_cpu_rst_n_cpu_sync` never drops with a running clock (the gate opens only after `pmu_cpu_rst_n_cpu_sync` is high), so `u_cpu` is not reset. `u_cpu_axi_cdc` has `m_rst_n_i = core_rst_n` and `async_axi_fifo` feeds both faces from `rst_both_n = s_rst_n_i & m_rst_n_i`, so the bridge is flushed. The CPU then resumes with held state against a flushed bridge.
- **Proposed DS-PMU-183 rule:** "Before it enters the mode CPU\_OFF or IDLE, software must arrange that another master writes `CTRL` to wake the CPU domain. Without such a write, only a reset of both `rst_n_i` and `cpu_rst_n_i` returns the domain."
- **Proposed Information, add:** "A reset of `rst_n_i` alone resets the PMU to NORMAL and flushes `u_cpu_axi_cdc`, but it does not reset `u_cpu`. The CPU then restarts its clock without a reset, while the bridge has lost the transfers that the CPU can wait for. This is derived from the RTL."
- **TM Known limits / UM checklist:** replace "chip reset" with "a reset of `rst_n_i` and `cpu_rst_n_i` together".

### 13. MISSING: a PMU reset in DOM_OFF releases all controls at one edge (no power-up order)
- **Where:** DS-PMU-029 Information; TM "Corner cases".
- **Current statement (DS-PMU-029 info):** "The test applies the reset during a wait of the CPU domain. It does not apply a reset in each state."
- **What the code shows:** the reset branch loads `clk_en_q <= 1`, `iso_en_q <= 0`, `rst_n_q <= 1` together. From `DOM_OFF` the clock enable, the clamp release and the reset release start at the same edge; the order of DS-PMU-022 does not apply. `test_pmu_reset_during_iso_wait` leg 1 does reset the PMU in `DOM_OFF` (after `_wait_state(dut, DOM_OFF, ...)`), leg 2 in `DOM_PD_ISO`.
- **Proposed DS-PMU-029 Information:** "The test applies the reset while the CPU domain is in `DOM_OFF` and during a wait in `DOM_PD_ISO`. It does not apply a reset in each state. The rule holds for the other states by the structure of the reset branch. A reset does not walk the power-up order: all outputs take the values of `DOM_ON` at the same edge."
- **Proposed TM corner case, add:** "A reset of the PMU in `DOM_OFF` sets the clock enable, the isolation control and the reset of the domain to their `DOM_ON` values at one edge. The power-up order of \reqref{DS-PMU-022} does not apply. In the CPU domain the clamp release and the clock enable then cross synchronisers of the same depth and arrive at about the same edge. This is derived from the RTL."

### 14. UNCLEAR: DS-PMU-021/022 order is the order at the PMU outputs, not in the CPU domain
- **Where:** DS-PMU-021 and DS-PMU-022 bodies.
- **What the code shows:** at the PMU outputs the order is exact (clock disable at E7, reset at E8 at 1:1). In the CPU domain, the reset asserts through the asynchronous clear of `u_cpu_pmu_rst_sync` (after E8) while the clock disable crosses two ranks (`pmu_cpu_clk_dis_sync` after E9). The clock actually stops because of the reset term of `cpu_gated_clk_en`, and the reset arrives first. For a CPU clock that is slower than `clk_i`, this is always so.
- **Proposed DS-PMU-021 first sentence:** "At the outputs of the PMU, a power-down of a domain must do these actions in this order: ..." **DS-PMU-022:** "At the outputs of the PMU, a power-up of a domain must do these actions in this order: ..."
- **Proposed Information after DS-PMU-021:** "In the CPU domain the reset asserts through the asynchronous clear of `u_cpu_pmu_rst_sync`, and the clock disable crosses two synchroniser ranks. The reset can therefore arrive first, and the reset term in the enable of `u_cpu_cg` then stops the clock (\cref{fig:tm:mod:pmu:power-down}). \Reqref{DS-PMU-100} states the order that holds in the CPU domain."

### 15. FIGURE: power-down timing is right but omits the CPU-domain side that matters
- **Where:** `fig:tm:mod:pmu:power-down`.
- **Checked:** every existing edge matches the RTL (derived, 1:1, equal phase): `pmu_mode_req` at E0 (0.5), SAVE at E1, PD_ISO from E2 to E7 (5 cycles), `cpu_iso_en_o` E2, `pmu_cpu_iso_en_sync` E4, `cpu_iso_ack_i` E6, `cpu_clk_en_o` E7, `cpu_rst_n_o` E8. Row widths sum to 10 units each.
- **Missing:** the three CPU-domain nets that show finding 14 and finding 3.
- **Proposed rows, after `cpu_rst_n_o`:**
  ```
  \texttt{pmu\_cpu\_rst\_n\_cpu\_sync} & 8.5H 1.5L \\
  \texttt{pmu\_cpu\_clk\_dis\_sync} & 9.5L 0.5H \\
  \texttt{cpu\_gated\_clk\_en} & 8.5H 1.5L \\
  ```
  (`pmu_cpu_rst_n_cpu_sync` falls without a clock edge right after E8; `u_cpu_clk_dis_sync` samples the fall of `cpu_clk_en_o` at E8 and E9.)
- **Proposed caption addition:** "In the CPU domain the PMU reset arrives right after E8 through the asynchronous clear of `u_cpu_pmu_rst_sync`, and it closes the clock gate. The clock disable arrives one edge later, at E9. `cpu_gated_clk` has its last edge at E8. Its edges E5 to E8 occur while the clamp is active."

### 16. FIGURE: power-up timing is right but does not show when the CPU clock starts
- **Where:** `fig:tm:mod:pmu:power-up`.
- **Checked:** OFF to E1, RST E1, CLK E2, REST E3, PU_ISO E4 to E9 (5 cycles), `cpu_rst_n_o` E1, `cpu_clk_en_o` E2, `cpu_ret_restore_o` E3-E4, `cpu_iso_en_o` E4, `pmu_cpu_iso_en_sync` E6, `cpu_iso_ack_i` E8, ON at E9. Row widths sum to 11 units.
- **Proposed rows, after `cpu_iso_ack_i`:**
  ```
  \texttt{pmu\_cpu\_rst\_n\_cpu\_sync} & 3.5L 7.5H \\
  \texttt{pmu\_cpu\_clk\_dis\_sync} & 4.5H 6.5L \\
  \texttt{cpu\_gated\_clk\_en} & 4.5L 6.5H \\
  ```
- **Proposed caption addition:** "In the CPU domain the PMU reset releases at E3 and the clock disable falls at E4, so the first edge of `cpu_gated_clk` is E5. The clamp releases after E6, so the edges E5 and E6 occur while the clamp is still active."

### 17. FIGURE: structure figure caption misplaces the synchronisers and the CPU reset tree is not drawn
- **Where:** `fig:tm:ch:mod-power-management:soc`.
- **Current caption:** "The three synchronisers in the top left run on `cpu_core_clk`."
- **What the figure and code show:** the synchronisers are in the middle column (x = 5.4), and four are drawn; `u_cpu_iso_ack_sync` runs on `core_clk`. The GPU reset AND is drawn, the CPU one is not: `cpu_domain_rst_n = cpu_core_rst_n & pmu_cpu_rst_n_cpu_sync & wdt_cpu_rst_n_cpu_sync` resets `u_cpu` and the `m_*` face of `u_apb_dbg_cdc`. `cpu_gated_clk` also clocks the `s_*` face of `u_cpu_axi_cdc` and the `m_*` face of `u_apb_dbg_cdc`.
- **Proposed caption sentence:** "The synchronisers `u_cpu_pmu_rst_sync`, `u_cpu_clk_dis_sync` and `u_cpu_iso_en_sync` run on `cpu_core_clk`. `u_cpu_iso_ack_sync` runs on `core_clk`." and "The reset AND above `u_cpu_cg` makes `cpu_domain_rst_n` from `cpu_core_rst_n`, `pmu_cpu_rst_n_cpu_sync` and the synchronised watchdog reset. `cpu_gated_clk` also clocks the `s_*` face of `u_cpu_axi_cdc` and the `m_*` face of `u_apb_dbg_cdc`."
- **Proposed TikZ (not rendered by me):**
  ```
  \node[cvtblock, minimum width=26mm] (crand) at (10.8,6.2) {reset AND};
  \draw[cvtsig] (rst.east) -- ++(0.8,0) |- (crand.west);
  \draw[cvtsig] (crand.east) -| (cpu.north);
  ```

### 18. WEAK-VERIFY: every `mutation:` reference rests on a campaign that was never recorded
- **Where:** DS-PMU-002, 025, 060-064, 100, 101, 104 `verify=`; DS map intro; TM verification table row "Mutation script"; UM "Verify".
- **What the code and repo show:** no result of `mutate_pmu_iso_ack.py` exists in the repository (no CR record; the only "KILLED" in `docs/manual/cr` is an unrelated cache campaign). The TM row says "The result of a campaign is a record in the Changes record", which implies a record exists. By reading each mutant against the cited tests:

  | Mutant | Rule cited | Predicted killer (by reading, not run) | Honest to cite? |
  |---|---|---|---|
  | p01 | 060 | `test_pmu_cpu_power_down_waits_for_ack` (lat 1..10 needs `lat+1` cycles) | yes |
  | p02 | 060 | ordering tests: with `ack_lat_i = 0` the ack is high, `wait_active = 0`, the state never leaves `DOM_PD_ISO` | yes |
  | t12 | 060 | same: `ack && wait_hit` is never true, the PMU hangs | yes |
  | p04 | 061 | `test_pmu_cpu_power_up_waits_for_ack_release` | yes |
  | p05 | 061 | ordering tests: hangs in `DOM_PU_ISO` (no timeout because `wait_active = 0`) | yes |
  | t01, t02 | 062 | the two timeout tests (hang) | yes |
  | t03, t04 | 062 | exact length 16 asserted. Note: with `ISO_ACK_TIMEOUT = 16`, `CW = 4`, so t04's `CW'(16)` is 0 and gives a 1-cycle timeout, not "one long" | yes (killed, but its description is wrong) |
  | t07, t08 | 062 | `STATUS == 0b1010` / healthy-down `0b0010` and "healthy power-down must not flag" | yes |
  | t09, t10 | 063 | final `STATUS == 0b0010`; leg 1 `STATUS == 0x3` after reset | yes |
  | t05 | 064 | second dead-ack wait must be 16 | yes |
  | t11 | 002 | `STATUS == 0b1010` | yes |
  | g01, g02 | 025 | `test_pmu_gpu_ignores_cpu_ack` (GPU hangs in `DOM_PD_ISO`) | yes |
  | s01, s02 | 100 | INV1 at 3x and 8x slower; s02 also the stale-ack check | yes |
  | s04 | 100, 101 | INV4 in `test_iso_before_reset_cpu_faster` only | 101 yes, 100 no (finding 1) |
  | s03 | 101 | revival leg of `test_dead_cpu_clock_does_not_hang_pmu` (`STATUS[3]` must be 0) | yes |
  | c01, c02 | 104 | `test_gpu_isolation_clamps_follow_pmu_iso_en` | yes |
- **Proposed DS map intro (add after the existing sentence):** "A reference with the word **mutation** names a mutant of `mutate_pmu_iso_ack.py` that breaks the rule. No result of a campaign is recorded in the repository. That the cited tests kill each mutant is predicted by reading the tests and is not measured."
- **Proposed TM table row, last two sentences:** "No workflow runs the script. It is run by hand in the simulation shell. No result of a campaign is recorded in the repository or in the Changes record."

### 19. WEAK-VERIFY: DS-PMU-103 - the live test does not show the clamp acting
- **Where:** DS-PMU-103 Information.
- **What the code shows:** `test_pmu_live_power_cycle` asserts `cpu_bridge_s_{aw,w,ar}valid == 0` and `commit_valid_o == 0` while off, but never checks that the raw outputs (`cpu_axi_*valid_raw`) are 1 at that time (it only logs a snapshot), so the clamp may never act in the window. The structural proof is `check_upf.py` (U05: control net, clamp value and the clamped set equal the RTL).
- **Proposed Information:** "The live test checks that the three valid signals and `commit_valid_o` are 0 while the domain is off. It does not check that the raw outputs of `u_cpu` are high at that time, so it does not show the clamp acting, and it does not check the two ready signals. The checker `check_upf.py` proves that the clamped nets, the control net and the clamp value in the RTL equal the isolation strategy of the power intent. This structural check is the proof of the rule."

### 20. WEAK-VERIFY: DS-PMU-153 cites a `check:` that checks nothing
- **Where:** DS-PMU-153 `verify=`.
- **What the code shows:** `pnr/sky130/soc/config.json` is a configuration file. No tool in `tools/` or `tb/` reads `u_root_buf` from it or fails on a renamed or replaced cell (Grep found only `test_cvt_maxcap_waiver.py`, which lists other instances). The DS note admits "The check named in the rule only proves that the file exists."
- **Proposed verify:** `[verify={review}]`. **Proposed Information, last sentence:** "No check fails when the name or the cell changes."

### 21. WEAK-VERIFY: DS-PMU-027 coverage limit not stated
- **What the code shows:** `test_pmu_busy_semantics` reads `busy` once while the CPU domain is in `DOM_PD_ISO` and once in each settled state. It never reads `busy` during a power-up or a GPU sequence.
- **Proposed Information after DS-PMU-027:** "The test reads `busy` once while the CPU domain is in `DOM_PD_ISO`, and once in each settled state. It does not read `busy` during a power-up or during a sequence of the GPU domain."

### 22. WRONG (minor): DS-PMU-005 "offset above 0x08"
- **What the code shows:** `apb4_register_bank` uses `addr_word = paddr[ADDR_W-1:2]` and ignores `paddr[1:0]`, so byte offsets 0x09 to 0x0B address `DOMAIN_EN` (and 0x01-0x03 `CTRL`, 0x05-0x07 `STATUS`). Only word offsets from 0x0C read 0 and drop a write. `walk_unmapped` probes from word 3.
- **Proposed rule:** "Every APB access must end without an error response. An access to a word at offset 0x0C or above in the slot must read 0 and must drop a write." **Information, add:** "The bank ignores `paddr[1:0]`. The byte offsets 0x01 to 0x03 address `CTRL`, 0x05 to 0x07 `STATUS` and 0x09 to 0x0B `DOMAIN_EN`."

### 23. WRONG: TM clock-gate verification "No simulation runs the arms of `BUFGCE`"
- **Where:** TM `tm:mod:rv32i-clock-gate`, Verification, second paragraph.
- **What the code shows:** `tb/cocotb/soc/Makefile`, `ifeq ($(FPGA),1)`: `COMPILE_ARGS += +define+FPGA_BUFGCE -y $(PROJ_ROOT)/rtl/fpga/sim`. `make FPGA=1 ...` simulates the BUFGCE arm against `rtl/fpga/sim/BUFGCE.v`, a stub that copies the behavioural latch and AND.
- **Proposed text:** "The suite runs the behavioural arm only. A build with `FPGA=1` runs the `BUFGCE` arm against the stub `rtl/fpga/sim/BUFGCE.v`, which copies the behavioural arm. No simulation runs the ASAP7 cell or the Sky130 cells. The test of `en` covers a rising `en` while `clk` is high and not a falling one."

### 24. MISSING: only the value of CTRL at ON or OFF counts; intermediate writes are lost
- **Where:** TM "Corner cases".
- **What the code shows:** `dom_target_on` is read only in `DOM_ON` and `DOM_OFF`; `pmu_mode_req` is `regs_out[0][1:0]`, a level. A value written and replaced while a sequence runs has no effect.
- **Proposed TM sentence (after "A write of a new mode during a sequence takes effect after the sequence ends."):** "Only the value of `CTRL` at an edge where the sequencer is in `DOM_ON` or `DOM_OFF` has an effect. A value that software writes and then replaces during a sequence has no effect. For example, CPU\_OFF written and then NORMAL written while the CPU domain powers up leaves the domain on."

### 25. MISSING: `soc_top` does not expose `ISO_ACK_TIMEOUT`
- **Where:** UM "Clocks and resets", last paragraph; DS-PMU-066 Information.
- **What the code shows:** `u_pmu` is instantiated with `#(.ADDR_W (12))` only; `soc_top` has no parameter for the timeout.
- **Proposed UM sentence (append):** "`soc_top` does not set `ISO_ACK_TIMEOUT`, so `u_pmu` has the default. To change it, add it to the parameter list of `u_pmu` in `soc_top`."

### 26. MISSING: TM "Watchdog reset" omits the effect in CPU_OFF and on the debug bridge
- **Where:** TM paragraph "Watchdog reset."
- **What the code shows:** the watchdog term is in `cpu_domain_rst_n`; the CPU flops have a synchronous reset; `cpu_gated_clk` has no watchdog term in its enable. While the PMU holds the domain off the clock is stopped, so a bite has no effect on the CPU and does not wake it. `cpu_domain_rst_n` also resets the `m_*` face of `u_apb_dbg_cdc` (async-assert reset synchroniser), so a bite ends a debug access with an error.
- **Proposed sentences (append):** "While the PMU holds the CPU domain off, the CPU clock is stopped, so a watchdog reset has no effect on the CPU flops and does not wake the domain. The watchdog reset also resets the `m_*` face of `u_apb_dbg_cdc`, so it ends a debug access in flight with an error response."

### 27. UNCLEAR: TM "Clock enable of the CPU domain" - the enable is not purely same-clock
- **Current statement:** "The enable is an AND of two synchroniser outputs on the same clock, and the comment in `soc_top` calls it glitch-free."
- **What the code shows:** `pmu_cpu_rst_n_cpu_sync` is the output of `cdc_reset_sync`, which falls asynchronously when `pmu_cpu_rst_n` falls and rises at an edge of `cpu_core_clk`. The gate is still safe because the latch of `rv32i_clock_gate` is closed while `clk` is high.
- **Proposed text:** "Both terms are synchroniser outputs on `cpu_core_clk`. `pmu_cpu_rst_n_cpu_sync` falls without a clock edge when the PMU asserts the reset, and it rises at an edge of `cpu_core_clk`. The latch of `u_cpu_cg` is closed while `cpu_core_clk` is high, so a fall of the enable cannot cut a pulse of `cpu_gated_clk`."

### 28. STYLE: DS-PMU-028 ambiguous quantifier; DS-PMU-029 and DS-PMU-062 state several things
- **DS-PMU-028 current:** "No output of the PMU must gate the clock of the PMU or reset it." **Proposed:** "The PMU must run on `core_clk` and `core_rst_n`. The outputs of the PMU must not gate the clock of the PMU and must not reset the PMU."
- **DS-PMU-029:** "The reset is synchronous." is a design fact, not a requirement of the reset effect. **Proposed:** move it to the Information note ("The reset is synchronous, so it takes effect at an edge of `clk_i`.").
- **DS-PMU-062:** three rules in one. Acceptable if the owner wants it; otherwise split the "exactly `ISO_ACK_TIMEOUT` cycles" sentence into its own rule.

### 29. STYLE/UNCLEAR: DS-PMU-025 "The GPU sequence must have no wait"
- **What the code shows:** the definition of "Wait" in the chapter applies to the CPU sequencer only, so the sentence is empty. The GPU sequencer stays exactly one cycle in `DOM_PD_ISO` and `DOM_PU_ISO` (`g_ack_none`: `iso_ack_w = iso_en_q`, `wait_hit = 0`); `test_pmu_gpu_ignores_cpu_ack` asserts `(DOM_PD_ISO, 1)` and `(DOM_PU_ISO, 1)`.
- **Proposed rule:** "The GPU sequencer must not depend on `cpu_iso_ack_i` or on the state of the CPU sequencer. It must stay exactly one cycle of `clk_i` in `DOM_PD_ISO` and exactly one cycle in `DOM_PU_ISO`."

### 30. STYLE: DS-PMU-105 second sentence repeats the first
- **Current:** "The PMU output `gpu_rst_n_o` must be low only while `gpu_iso_en_o` is high. The GPU clamp must not release while the GPU reset is asserted." Both say "reset low implies clamp high". **Proposed:** keep the first sentence only.

### 31. UNCLEAR: DS-PMU-003 bit order direction
- **Current:** "The order of the bits is `cpu_clk_en`, ..." **Proposed:** "From bit 0 to bit 9 the bits are `cpu_clk_en`, `gpu_clk_en`, ..." (the list itself matches `hw_wdata[2]`).

### 32. INCONSISTENT: UM clock-gate step 2 and `power.yaml` `test_en` tie-off vs the cache gates
- **Current:** UM: "Tie `test_en` to `1'b0` where no scannable flop sits behind the gate." yaml: "Tie it to 0 where no scannable flop sits behind the gate."
- **What the code shows:** the cache SRAM gates have no scannable flop behind them but take `test_en_i` (`rv32i_icache.sv` comment: the latch "must carry a test term for tools/dft/check_scan_clk_rst.py to accept the clock cone"). The RTL header says "can be tied". The TM integration paragraph has the nuance; the UM and the yaml do not.
- **Proposed UM step 2:** "You can tie `test_en` to `1'b0` where no scannable flop sits behind the gate. A gate in front of an SRAM macro that scan or MBIST must reach takes the test enable of its parent, as the cache gates do. For a gate in the CPU or GPU clock path, use `dft_test_en`." **yaml:** "Test enable. High forces the gate open. Keep it static while `clk` runs. It can be tied to 0 where no scannable flop sits behind the gate."

### 33. MISSING: UM - the registered-output pytest skips silently without the tools
- **What the code shows:** `pytestmark = pytest.mark.skipif(YOSYS is None or SV2V is None, ...)`; only CI turns a skip into a failure.
- **Proposed UM sentence (append to the paragraph):** "Without `yosys` or `sv2v`, pytest skips the tests and reports no failure. A skip means that the check did not run."

### 34. UNCLEAR: TM PMU "Debug, test and DFT" - scan reset needs a clock edge
- **Current:** "In scan mode the reset `core_rst_n` equals the scan reset, so the PMU is reset by the scan reset."
- **What the code shows:** the PMU reset is synchronous; `test_scan_gpu_reset_with_pmu_gpu_off` toggles `scan_clk_i` four times "PMU reset is synchronous: needs test clocks to take effect".
- **Proposed:** "In scan mode the reset `core_rst_n` equals the scan reset. The PMU reset is synchronous, so the scan reset takes effect at the next edge of the test clock."

### 35. UNCLEAR: `power.yaml` `ADDR_W` legal range
- **Current:** `legal: "12 in the SoC"`. That is a use, not a range.
- **What the code shows:** `apb4_register_bank` indexes `addr_word[IDXW-1:0]` with `IDXW = 2` for three registers, so `ADDR_W - 2 >= 2`. No elaboration guard exists.
- **Proposed:** `legal: "4 or more; 12 in the SoC"`.

### 36. MISSING: UM scan rule - mode NORMAL is not enough, the domains must be settled
- **Where:** UM "Clocks and resets" bullet 4; checklist line 8.
- **What the code shows:** a clamp stays high until `DOM_PU_ISO` is left; `CTRL = NORMAL` alone does not drop it.
- **Proposed:** "Before a scan, write the mode NORMAL and wait until bits 2 to 0 of `STATUS` read 0b011, so that no clamp is active during the scan." Checklist: "The PMU is in the mode NORMAL and both domains are on before a scan."

### 37. UNCLEAR: TM Known limits - "someone sets up the transfer before"
- **Proposed replacement for the three sentences from "Another bus master":** "Another bus master, for example the DMA engine, can write `CTRL` and wake the domain. In IDLE the CPU and the GPU are off, so the transfer has to be set up before the power-down. A reset of `rst_n_i` and `cpu_rst_n_i` together also returns the domain. No test wakes the CPU domain by a bus write."

### 38. WEAK-VERIFY: DS decision "Acknowledge from the CPU domain" quotes an unrecorded test result
- **Current:** "The tests of the acknowledge fail without the handshake at a CPU clock that is 3 times and 8 times slower."
- **What the code shows:** this is the docstring claim of `test_soc_pmu_iso_ack.py` ("fails on origin/main"); no run record exists. By derivation it is true: with the ack tied high (mutant s02 shape), `DOM_PD_ISO` lasts one cycle, the reset asserts two `clk_i` cycles after `cpu_iso_en_o`, and at 3x slower the clamp needs two CPU edges (up to six `clk_i` cycles).
- **Proposed:** "Without the handshake, the reset reaches the CPU domain before the clamp at a CPU clock that is 3 times or 8 times slower. This is derived from the synchroniser depths. The test file states that its two slow-clock tests fail without the handshake. No record of that run is in the repository."

## Requirement verdicts (43)

| Rule | Verdict | Rule | Verdict |
|---|---|---|---|
| DS-PMU-001 | OK | DS-PMU-063 | OK; 18 |
| DS-PMU-002 | OK; 18 (t11 predicted killed) | DS-PMU-064 | OK; 18 |
| DS-PMU-003 | OK (lag measured); 31 | DS-PMU-065 | OK (review) |
| DS-PMU-004 | OK | DS-PMU-066 | OK (inferred estimate stated); 25 |
| DS-PMU-005 | 22 | DS-PMU-067 | **2 (WRONG)** |
| DS-PMU-006 | OK (base address measured; the limit is review) | DS-PMU-100 | **1 (WRONG)**; 18 |
| DS-PMU-020 | OK | DS-PMU-101 | OK (review + mutants); 18 |
| DS-PMU-021 | 14 | DS-PMU-102 | **4 (WEAK-VERIFY)**; 9 |
| DS-PMU-022 | 14; 3 | DS-PMU-103 | 19 |
| DS-PMU-023 | OK (full per-cycle tuples) | DS-PMU-104 | OK; 18 |
| DS-PMU-024 | OK; 24 (TM) | DS-PMU-105 | OK; 30 |
| DS-PMU-025 | 29; 18 | DS-PMU-106 | **7 (WRONG)** |
| DS-PMU-026 | OK (structural gate with ten negative controls) | DS-PMU-107 | OK (both directions tested) |
| DS-PMU-027 | 21 | DS-PMU-108 | 9 |
| DS-PMU-028 | 28 (style) | DS-PMU-109 | OK (the test failed before the wiring fix, per its comment) |
| DS-PMU-029 | 13; 28 | DS-PMU-150 | OK; 23 (TM) |
| DS-PMU-060 | OK; 18 | DS-PMU-151 | OK |
| DS-PMU-061 | OK; 18 | DS-PMU-152 | OK (review) |
| DS-PMU-062 | OK (exact length measured at 16); 18; 28 | DS-PMU-153 | 20 |
| | | DS-PMU-180 | **8 (WRONG note)** |
| | | DS-PMU-181 | OK (owner decision kept); 9 |
| | | DS-PMU-182 | OK; 3, 5 |
| | | DS-PMU-183 | 11, 12 |
| | | DS-PMU-184 | 10 |

## Confirmed right (checked against code)
- State table (nine states, codes, the five outputs per state) and the three pairs of equal output tuples.
- FSM figure: states, ring order, every arc and arc label, the four self-loops, and the GPU note, against the two `unique case` blocks. (The `default` arms map unused codes to `DOM_ON`; not drawn, harmless.)
- Power-down and power-up figures: every drawn edge, and PD_ISO = PU_ISO = 5 cycles at 1:1 with two-rank synchronisers (derived).
- Clock-gate figure: `en` 2.7/5.7, latch 3.0/6.0, three `gclk` pulses at 3.5, 4.5, 5.5. Latch equation `if (!clk) en_latch = en | test_en`, the four arms and their order, the instance table (enables and test enables).
- Register map, reset values 0x0/0x3/0x33, WMASK, `pready`/`pslverr` tie-offs, STATUS and DOMAIN_EN bit order, the one-cycle read lag and the E0/E1/E2 write chain.
- Timeout: `$clog2(ISO_ACK_TIMEOUT)` counter, `wait_hit` at `ISO_ACK_TIMEOUT-1`, state lasts exactly `ISO_ACK_TIMEOUT` cycles, flag set/clear conditions, guard `< 2`, the 3R+3 and "about 80" arithmetic.
- Clamp sets and controls (6 CPU nets on `pmu_cpu_iso_en_sync`, 8 GPU nets on `pmu_gpu_iso_en`), reset trees, `u_gpu_domain_rm`, `cpu_cg_en` expression, `dft_test_en` on both top gates, `HARD_ROOT(1'b1)` on `u_cpu_cg`, `u_cpu_axi_cdc.s_rst_n_i = cpu_core_rst_n`.
- Test and mutant counts: 20 tests in `test_pmu.py`, 7 in `test_soc_pmu_iso_ack.py`, 4 in `test_clock_gate_scan.py`, 26 mutants with 2 expected survivors (t06, s05) and their reasons; the script's last line format.
- `RSZ_DONT_TOUCH_RX` in both Sky130 configs lists `u_cpu_cg.g_cell.u_root_buf`; the ASAP7 SDC matches `*u_icg/GCLK`.
- Owner decisions: CPU state "not guaranteed" with the model property in TM; wake-up by another master or reset; scan clamps as a known limit; no power, area or timing figures; no AGENTS.md caveat contradicted.
- No "must" outside requirement bodies in TM, UM or DS notes; no dates, tracker IDs, PR/GH numbers, `file:line` or section numbers in the new files. All cross-reference labels exist once.

## RTL, test and tool observations for the owner (read from code, not simulated)
1. **Stale acknowledge after a timed-out power-up** (`pmu.sv`, `g_ack_cpu` and the `DOM_PD_ISO` next-state line): the next CPU power-down leaves `DOM_PD_ISO` in one cycle on the still-high ack, and the flag is cleared when that power-down starts and is not set again. The one case in which STATUS[3] is most needed is the case that hides it.
2. **CPU clock runs while the CPU clamp is active** (derived 1:1: four `cpu_gated_clk` edges E5-E8 at power-down, two edges E5-E6 at power-up). The clamps cover only `u_cpu` outputs; the bridge's ready/valid inputs to `u_cpu` are not clamped, so a CPU-side handshake in those edges is one-sided (lost request, response taken without a pop). The power-up window is outside software control because the CPU resumes from held state. No test watches these edges.
3. **GPU control slave accepts an address while in reset** (`gpu_top`: `s_axil_arready = ~ar_cap_q`, `s_axil_awready = ~aw_cap_q`, async reset): an access during GPU_OFF is lost and the master waits, also after power-up. I did not check the ring for a timeout.
4. **MBIST force during CPU_OFF** (`cpu_cg_en` OR `mbist_force`; `rv32i_cpu_top` `mb_run_w = mbist_run_i & rst_n_i`): the force clocks the CPU while `cpu_domain_rst_n` is low, so the synchronous CPU flops reset, and the CPU MBIST cannot run. The request destroys the state and tests nothing.
5. **DS-PMU-100 invariant broken while `cpu_core_rst_n` is low** (`u_cpu_iso_en_sync` reset by `cpu_core_rst_n`, `u_cpu_pmu_rst_sync` not): harmless because the domain is then in reset, but it contradicts the UPF "isolate first" intent and no monitor runs there.
6. **PMU reset from DOM_OFF** releases clock enable, clamp and reset together (reset branch of `g_dom_seq`).
7. **`rst_n_i` alone vs `cpu_rst_n_i`**: a fabric-only reset flushes `u_cpu_axi_cdc` (`rst_both_n`) and returns the PMU to NORMAL but never resets `u_cpu`; the CPU resumes against a flushed bridge.
8. **No test can fail if the reset term is removed from `cpu_gated_clk_en`** (DS-PMU-102). A 1:1 SoC test that asserts "no `cpu_gated_clk` rising edge while `pmu_cpu_rst_n_cpu_sync` is 0", or a mutant that drops the term, would close it.
9. **No mutation campaign record** for `mutate_pmu_iso_ack.py`. t04's description ("one cycle late") is wrong at `ISO_ACK_TIMEOUT = 16` (`CW'(16)` truncates to 0, a 1-cycle timeout). s04 is killed only by INV4 at the 7:3 ratio.
10. **Stale comments**: `rv32i_clock_gate.sv` header says `config*.json` lists `u_icg` and `u_root_buf` in `RSZ_DONT_TOUCH_RX`; the configs list only `u_root_buf` (the config note says the ICG was removed). `gen_integ_hex.py` "nothing survives a PMU power cycle" and the `test_soc_gpu_isolation_via_pmu` docstring "state survives" both misstate the GPU (vector register file and shared memory keep content; control flops reset). `soc_top` comment "A PMU power cycle must keep the bridge state, as it keeps u_cpu" states as intent what the owner decided is not guaranteed (Q2).
11. **Reference firmware vs the documented rule**: `pmu_cycle_fw` keeps flushing the D-cache in its loop, so the only live CPU power cycle runs with traffic in flight; it passes because the bridge keeps state.
12. **`ADDR_W`** of `pmu` has no lower-bound guard (needs 4 or more).

## Not checked
- No simulation, mutation run, LaTeX build or TikZ rendering. I assumed the tikz-timing convention of the CDC chapter (lowercase `c` is half a period, the clock starts low, rising edge at k+0.5) and did not render the figures; the TikZ snippet in finding 17 is unrendered.
- `soc_clocks.start_soc_clocks` phase alignment (affects which ratios can expose s04 through INV4).
- The AXI ring/crossbar between a master and the GPU control slave (timeout or not), and the crossbar wedge claim.
- Whether `core_clk` runs while the PLL is unlocked (the PMU reset is synchronous and needs edges while `core_rst_n` is low).
- `check_upf.py` beyond the SCAN claim and its docstring (U05 clamp extraction details), `phase5_soc_rtl_facts.json`, `test_check_upf.py`.
- `dft_ctrl`/`soc_mbist` logic that drives `mbist_force`, and the meaning of `mb_cpu_status[1:0]`.
- Gate-level and FPGA-board behaviour of the clock-gate arms; the ASAP7 ICG cell function.
- Whether the cocotb CI workflow includes every cited target in its shards (the work order says `SOC_CI_SUITES` does).
- The relocated source archive (`06-source-archive.tex`), `labels.tsv`, the glossary and `requirement_ids.tsv` edits.
- `tb_soc_top` wrapper wiring and `test_soc_multiclock_pll2.py` firmware body (only the test function was read).
