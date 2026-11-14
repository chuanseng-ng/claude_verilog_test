# Truth review: CDC chapters (DS, TM, UM, cdc.yaml)

Scope: working tree on `docs/pilot-p2-cdc-chapters`. I read the five RTL files in full, the three chapters and `cdc.yaml` in full, and the tests, testbench parts, Makefile targets, constraint files, scripts and `soc_top` instances named below. I ran nothing: no simulation, no make, no LaTeX. Every verdict below comes from reading the code. Where I computed a cycle count, I counted flops and edges at the default parameters.

Note on the count: the Design Specification has **53** requirements, not 54. `requirement_ids.tsv` lists 53, and no DS-CDC-004 exists. The numbering has a gap.

## Findings (most harmful first)

### 1. WRONG: DS-CDC-157 "No combinational path between the faces", and its Information note
- **Current statement:** "The outputs of the `s_*` face that depend on the data and handshake inputs of the `m_*` face must not change without an edge of `s_clk_i`." The note says the dependence of ready on reset "is a path inside one domain. It is not a crossing."
- **What the code shows:** `cdc_gray_fifo`: `assign rd_data_o = mem_q[rd_bin_q[ADDR_W-1:0]];` and `mem_q` is written on `wr_clk_i`. In `u_b_fifo` and `u_r_fifo` the write clock is `m_clk_i`. When the B or R FIFO is empty, `rd_bin_q` points at the slot that the next write fills. A write on an `m_clk_i` edge therefore changes `s_bresp_o`, `s_rdata_o`, `s_rresp_o` and `s_rlast_o` with no `s_clk_i` edge. The cited test `test_no_combinational_crossing` avoids this case on purpose. Its comment says: "with the fifo EMPTY, s_rdata_o/s_bresp_o are documented don't-cares that legitimately advance". The test leaves one valid entry in B and R before it freezes `s_clk`. The note is wrong too. In `async_axi_fifo`, `wr_ready_o = wr_rst_n_i && !full_q` uses `s_rst_sync_n`, and that reset is cleared asynchronously from `rst_both_n = s_rst_n_i & m_rst_n_i`. So `m_rst_n_i` drops `s_awready_o` with no `s_clk_i` edge. That is a reset crossing, not "a path inside one domain".
- **Proposed rule:** "The valid and ready outputs of the `s_*` face must not change without an edge of `s_clk_i`, except when a reset asserts. While `s_bvalid_o` or `s_rvalid_o` is high, the payload outputs of that channel must not change without an edge of `s_clk_i`." **Proposed note:** "While a channel is empty, its payload outputs on the `s_*` face can change on an edge of `m_clk_i`. They are valid only while the valid output is high. Either reset input clears both reset synchronisers asynchronously, so the ready outputs of both faces fall without a clock edge when either reset asserts."

### 2. MISSING / UNCLEAR (DS-CDC-103, DS-CDC-106, TM `apb_cdc_bridge` reset results): an error completion does not prove that the destination did nothing
- **Current statement:** DS-CDC-103: "...when the destination enters reset before it answers. No transfer must complete on the `m_*` face for this request." DS-CDC-106: "Each forwarded request must make exactly one APB transfer on the `m_*` face." The RTL header says "No write is made on the destination for an errored request". The chapters do not repeat that sentence, and they do not correct it either.
- **What the code shows:** `ack_q` is set in `D_ACCESS && m_pready_i`, after the destination access has completed. `m_rst_n_i` clears `ack_q` asynchronously through `rst_both_n -> u_m_rst_sync`. The source clears `req_q` and takes the error branch in `S_REQ` when `!m_rst_n_s` while `ack_s` is still 0 (`else if (!req_fwd_q || !m_rst_n_s) ... resp_pslverr_q <= 1'b1`). Take a destination reset that starts less than about one `s_clk_i` period after `ack_q` rises. `u_ack_sync` can miss the `ack_q` pulse, so `ack_s` never rises. `m_in_rst_s` then rises and the source returns SLVERR, but the write already took place at the destination. DS-CDC-106 also conflicts with DS-CDC-103 and with the false-status window: a forwarded request that a destination reset aborts makes zero transfers.
- **Proposed text:** DS-CDC-103: "When the destination enters reset before `m_pready_i` completes the access, a forwarded request must complete with `s_pready_o` and `s_pslverr_o` high within `SYNC_STAGES_TO_S`+3 rising edges of `s_clk_i` after `m_rst_n_i` falls." Add an Information note: "When the destination resets after `m_pready_i` and before the acknowledge reaches the source, the access can be complete at the destination while the source reports an error. Software must treat an error from the bridge during a destination reset as 'access state unknown'." DS-CDC-106: "Each forwarded request that no reset aborts must make exactly one APB transfer..." Both bounds are inferred from the RTL. No test measures them.

### 3. MISSING (DS and TM `apb_cdc_bridge`): a stopped `m_clk_i` hangs the transfer, and the bridge has no timeout
- **What the code shows:** `S_REQ` exits only on `ack_s`, `!req_fwd_q` or `!m_rst_n_s`. In `soc_top`, `u_apb_dbg_cdc` has `.m_clk_i (cpu_gated_clk)`, and the PMU gates that clock through `u_cpu_cg`. A debug access during clock gating with no reset waits until the clock restarts, and `s_pready_o` stays low for that time. That stalls the APB master upstream. `soc_top` also documents a related gap for `u_cpu_axi_cdc`: "a mid-burst CPU transaction at clock gating can still wedge a crossbar slave engine. No drain step exists." Neither chapter mentions either case.
- **Proposed TM Known-limits text:** "The bridge has no timeout. When `m_clk_i` stops and `m_rst_n_i` stays high, a transfer waits until the clock runs again, and the APB master upstream waits with it. In `soc_top` the clock of the `m_*` face of `u_apb_dbg_cdc` is `cpu_gated_clk`, which the PMU can stop." Add a User Manual step: "Do not stop `m_clk_i` while a transfer can be in flight, or assert `m_rst_n_i` before you stop it."

### 4. MISSING / UNCLEAR (TM "Timing constraints and CDC checks"): `u_apb_pll_cdc` is a real crossing that neither check sees
- **Current statement:** "The check file has no part for `u_apb_pll_cdc`, because its two faces are in the clock domain of `clk_i` in the constraint files..."
- **What the code shows:** `u_apb_pll_cdc` has `s_clk_i = core_clk` (the PLL output) and `m_clk_i = pll_ref_clk` (the raw reference). The constraint files put both on `sys_clk`, and `cdc_config.yml` has `domain_aliases: core_clk: clk_i`. So the timing check and the CDC gate both treat the crossing as same-domain logic. With a real PLL (not the stub), the two clocks have different frequencies. The bridge exists for exactly that reason. The TM sentence is accurate about what the files declare, but it reads as if the crossing were safe.
- **Proposed text:** "`u_apb_pll_cdc` crosses between `core_clk` and the reference clock of `u_pll_sub`. The constraint files and the CDC configuration put both clocks in the domain of `clk_i`, because they declare no generated clock for the PLL output. So no budget and no CDC check covers this bridge. It is safe by design (four-phase handshake), but no tool checks it."

### 5. WEAK-VERIFY: DS-CDC-001 "Crossings use the primitives"
- **Cited:** `check:tools/cdc/cdc_config.yml`, `test_cdc_gate.py::test_main_fails_on_unwaived_crossing`, `::test_main_fails_on_stale_waiver`.
- **What the code shows:** The two pytest tests feed synthetic reports to the gate script. They prove the gate logic, not the design. The design check is `make -C sim cdc CDC_STRICT=1`, and its default `CDC_STRICT ?= 0` is informational. That check is not cited. `cdc_config.yml` also says the gate is blind to a raw sample of a single-source asynchronous signal: "A raw sample of a lone asynchronous pin is classified OKX, which never fails the gate". Only the entries in `required_synchronisers` (I2C, UART, iso-ack, DFT switch) close that gap.
- **Proposed fix:** Cite `make -C sim cdc CDC_STRICT=1` as the design check. Add to the TM CDC-tool paragraph: "The gate does not fail on a crossing from one foreign domain that has no synchroniser (class OKX). Only the list of required synchronisers catches a deleted synchroniser. A review must find the rest."

### 6. WRONG (TM `cdc_gray_fifo` Introduction): "The two bridges use it"
- **What the code shows:** `apb_cdc_bridge` instantiates only `cdc_sync` and `cdc_reset_sync`. Only `async_axi_fifo` (five instances) and `mbist_xing` use `cdc_gray_fifo`.
- **Proposed text:** "`async_axi_fifo` uses it for its five channels, and `mbist_xing` uses it with a depth of 2."

### 7. WRONG (TM `cdc_gray_fifo` Verification): "The depths 8 and 16 are linted ... but no simulation runs them."
- **What the code shows:** In `async_axi_fifo`, `W_DEPTH = 8` and `R_DEPTH = 8`, and `test_async_axi_fifo` runs at the defaults (for example `test_exact_depth_full` checks `count_w == w_depth`). Depth 8 is simulated inside that suite. Depth 16 is not simulated anywhere.
- **Proposed text:** "This suite runs the depths 2 and 4. The suite of `async_axi_fifo` runs the depths 4 and 8. No simulation runs the depth 16. The lint step and the equivalence script cover it."

### 8. WRONG: DS-CDC-159 "Valid is not withdrawn"
- **Current statement:** "...unless a reset of its own domain asserts."
- **What the code shows:** Both `cdc_reset_sync` instances take `rst_both_n`. `s_rst_n_i` falling therefore clears `m_rst_sync_n`, which sets `empty_q` and drops `m_awvalid_o`, `m_wvalid_o` and `m_arvalid_o`. The reset of the other face withdraws a valid output.
- **Proposed text:** "...unless `s_rst_n_i` or `m_rst_n_i` asserts."

### 9. WEAK-VERIFY: DS-CDC-115 "No destination select while the destination reset is low"
- **What the code shows:** `test_reset_asym_staggered_m_then_s` releases `m_rst_n` first and then holds `s_rst_n` low. Its `_m_psel_never_pulses` watcher runs while `m_rst_n_i` is **high**, so it does not exercise this rule. Its message, "while m_rst_n_i is held low", is misleading. Only `test_reset_asym_staggered_s_then_m` (with traffic) tests the rule, and `test_reset_mid_transaction_m_side` covers it in part.
- **Fix:** Replace the `m_then_s` reference with `test_reset_mid_transaction_m_side`, or add a check of `m_psel` during `m_rst_n` low to that test.

### 10. WEAK-VERIFY: DS-CDC-103 bound and destination check
- **What the code shows:** In `test_reset_mid_transaction_m_side`, `responder.completed == 0` holds partly because of the testbench. `ApbSlaveResponder` aborts by itself when `rst_n` is low (`if not int(self.psel.value) or not int(self.rst_n.value): aborted = True`). The rule says "a bounded number" but gives no number, and the test checks no bound. It only awaits the task under a 50 us timeout.
- **Fix:** State the bound (finding 2) and check it in the test. Note in the TM that the responder does not complete an access while its reset is low.

### 11. WEAK-VERIFY: DS-CDC-152 "A reset on one face resets both"
- **What the code shows:** `test_cross_flush` checks only the AW FIFO, and only for an `m_rst_n` pulse. `test_reset_while_busy_s_side` and `test_reset_while_busy_m_side` check recovery, not that every FIFO was emptied. No test proves the flush of W, B, AR and R, or the flush after an `s_rst_n` pulse. The rule is true by construction (`rst_both_n` feeds both chains).
- **Fix:** Add `review` to the verification list, or extend `test_cross_flush` to all five FIFOs and to both resets.

### 12. WEAK-VERIFY / UNCLEAR: DS-CDC-153 "Reset is a hard flush"
- **What the code shows:** The cited `test_soc_reset_asym_*` tests check zero acceptance and correct boot after the release. That is DS-CDC-154 territory. They do not check that buffered beats are dropped without a response. The rule also says "the user must reset the attached master and the fabric from the same root". In `soc_top`, `s_rst_n_i = cpu_core_rst_n` comes from the `cpu_rst_n_i` port and `m_rst_n_i = core_rst_n` comes from the `rst_n_i` port, two separate top-level ports. A `core_rst_n`-only reset flushes the bridge while `u_cpu` keeps running.
- **Proposed text:** Keep the first sentence (verified by review). Add: "In `soc_top` the two resets come from two top-level ports. The common root is then an obligation on the board or the reset controller outside the SoC." Mark it `review`.

### 13. WEAK-VERIFY (testable, but cited as review only): DS-CDC-116 "Read data of a forced completion"
- **What the code shows:** `test_availability_never_forwarded` already does `data, ok = await ctx.s_master.read(addr)` and asserts `ok is False`, but never checks `data`. One assertion (`data == 0`) would verify the rule. The TM statement "A test ... does not exist" is true today.
- **Fix:** Add `assert data == 0` and cite the test.

### 14. WEAK-VERIFY (testable, but cited as review only): DS-CDC-045 "Minimum number of ranks" for `cdc_reset_sync`
- **What the code shows:** The guard `if (STAGES < 2) ... $fatal(1, "cdc_reset_sync: STAGES (%0d) must be >= 2"` exists, but no negative target exists. A copy of `cdc_sync_stages1_neg` against `cdc_reset_sync.sv` would test the rule. The TM states the gap correctly.

### 15. WEAK-VERIFY: DS-CDC-003 "Synchroniser flops carry the attribute"
- **What the code shows:** `cdc_config.yml` does not check for the attribute directly. Only the `required_synchronisers` entries depend on it (they need class CDC, and that class needs `magic_cdc`), and they cover 6 instances out of about 25. The attribute is present today on `sync_q` in both modules.
- **Fix:** Name the coverage limit, or add a grep check (for example in `check_pinned_text.py`) that `(* magic_cdc *)` stays on both arrays.

### 16. UNCLEAR: DS-CDC-102 has no bound
- **What the code shows:** With `m_rst_n_s` already 0 at the SETUP edge: `S_IDLE -> S_REQ` at that edge, `S_REQ -> S_DROP` at the next edge (`!req_fwd_q`), `S_DROP -> S_DONE` at the next edge (`ack_s` is 0). `s_pready_o` is high in the cycle after the third edge.
- **Proposed text:** "...must complete with `s_pready_o` and `s_pslverr_o` high in the third cycle after the SETUP edge." This is inferred from the RTL. The test checks `(sync_s + 4) * 10` ns.

### 17. MISSING: caller rules in the RTL headers that the DS does not state
- `async_axi_fifo` header: "Hold each reset low for at least SYNC_STAGES+1 periods of the other clock." The TM repeats it, but the DS has no rule for it.
- `apb_cdc_bridge` header: "Hold s_rst_n_i and m_rst_n_i low for at least SYNC_STAGES+1 periods of the other clock." DS-CDC-109 covers `m_rst_n_i` only.
- `cdc_gray_fifo`: `SYNC_STAGES` of 2 or more (enforced through the `cdc_sync` guard). There is no DS rule or test reference for it.
- **Fix:** Add review-only rules, or state in an Information note why the DS leaves them out.

### 18. UNCLEAR / UNSUPPORTED: DS-CDC-043 "Reset width" (source disagreement 8)
- **What the code shows:** `cdc_reset_sync` clears every rank asynchronously (`negedge rst_n_async`). Any valid asynchronous-clear pulse clears the chain, and `rst_n_o` stays low for at least `STAGES` edges after the release whatever the input width. The module itself does not need `STAGES`+1 periods. The three headers word the rule three ways: "of `clk_i`" (`cdc_reset_sync`), "of the other clock" (`async_axi_fifo`), and both forms in `apb_cdc_bridge`.
- **Fix:** Either give the reason (for example: so that logic downstream of the source, or the other domain, sees the reset) or reduce the rule to "a pulse that meets the minimum asynchronous-clear width of the flops". Ask the owner which is meant.

### 19. UNCLEAR, cross-book: FIFO latency (source disagreement 6)
- **What the code shows:** In zero-delay simulation the latency is exactly `SYNC_STAGES`+1 receiving edges after the write edge: 2 sync ranks, then `empty_q`. `run_empty_boundary` measures this. DS-CDC-064 states a lower bound only (true). The TM states the exact value (true in simulation). The `async_axi_fifo` header says "about SYNC_STAGES+2", and the TM quotes it without reconciling the two.
- **Proposed TM text:** "In simulation the count is exactly `SYNC_STAGES`+1. In silicon the first rank can resolve one edge later, so the count is `SYNC_STAGES`+1 or `SYNC_STAGES`+2. The header gives the upper figure."

### 20. MISSING (TM `apb_cdc_bridge` Integration): consequence of a short `m_rst_n_i` pulse
- **Current statement:** "A shorter pulse can stay hidden from the `s_clk_i` domain, and then the status never changes."
- **What the code shows:** The destination resets (`ack_q`, `d_state_q` and `u_req_sync` clear). After the release, `u_req_sync` resynchronises `req_q = 1`, `D_IDLE` sees `req_m`, and the destination runs the access **again**. If the first access had completed, this is a duplicated write.
- **Proposed text:** "...the status never changes, and after the release the destination runs the transfer again. A write can then happen twice."

### 21. WRONG (TM `cdc_sync` Integration): "The register names inside the module are not matched by name in the constraint files. The CDC check tool finds the module by its attribute."
- **What the code shows:** `cdc_config.yml` matches register names: `required_synchronisers` uses `'^u_uart\.u_uart_rx_sync\.sync_q\[0\]:D$'` and similar, and the waiver uses `u_[sm]_rst_sync\.sync_q\[\d+\]`. The check SDC section 10a matches `*rst_sync*`, and the Sky130 check SDC matches `u_wr_ptr_to_rd` and `u_rd_ptr_to_wr`.
- **Proposed text:** "The CDC configuration matches the array name `sync_q` and the instance names. The check constraint file sets its false path on registers whose names contain `rst_sync`. Keep `sync_q`, and give each new `cdc_reset_sync` instance a name that contains `rst_sync`." Add the naming rule to the UM checklist.

### 22. WRONG (UM "Constrain the crossings"): "Keep the names `req_q`, `ack_q`, `u_wr_ptr_to_rd` and `u_rd_ptr_to_wr`. The file finds the nets by these names."
- **What the code shows:** The ASAP7 check file matches `u_wr_ptr_to_rd*d_i` and `rd_gray_q`, not `u_rd_ptr_to_wr`. The Sky130 file matches `u_wr_ptr_to_rd` and `u_rd_ptr_to_wr`. Neither list includes `rst_sync` or `sync_q`, which finding 21 shows the files also match.
- **Proposed text:** "Keep `req_q`, `ack_q`, `u_wr_ptr_to_rd`, `u_rd_ptr_to_wr`, `rd_gray_q`, `sync_q`, and the text `rst_sync` in reset-synchroniser instance names. The check files and the CDC configuration match these names."

### 23. WRONG (UM "Verify the crossings", step 4, and "Constrain", step 6): exit codes and marker text
- **What the code shows:** The script `check_cdc_timing.tcl` exits 0, 1 or 2. The make target `check-cdc-timing-asap7-soc` maps every marker, including `CDC-CHECK-SETUP-ERROR`, to `exit 1` in the recipe, and GNU make then exits 2 for any failed recipe. So the make command cannot tell a finding from a setup error by its exit code. The marker lines are `ERROR: CDC-EXCEPTION-MISS: ...`, so they do not start with `CDC-EXCEPTION-MISS`.
- **Proposed text:** "The make target fails on a finding and on a setup error. Read the `marker:` lines to tell them apart. A line that contains `CDC-EXCEPTION-MISS` means..."

### 24. UNCLEAR (`cdc.yaml`, UM "Instantiate a block"): resets of the two bridges described as "already synchronised"
- **What the code shows:** `apb_cdc_bridge` and `async_axi_fifo` pass `s_rst_n_i` and `m_rst_n_i` through their own `cdc_reset_sync` instances, and both resets also feed `rst_both_n`, which crosses into the other domain. The bridges do not need synchronised inputs. `cdc.yaml` gives them domain `s_clk_i` or `m_clk_i` and says "The caller supplies it already synchronised". The UM sentence "Supply each reset already synchronised to the clock of its domain" applies to every block, including the bridges.
- **Proposed text:** In `cdc.yaml`, set domain `async` and write "Active-low reset. The bridge synchronises it internally." Limit the UM sentence to `cdc_sync` and `cdc_gray_fifo`.

### 25. FIGURE: `fig:tm:ch:mod-cdc-primitives:soc` (SoC overview)
- The box "`apb_cdc_bridge` x 3" is fed from "APB debug port, PLL slots" and drawn into "u_cpu debug slave". Only `u_apb_dbg_cdc` ends in the CPU domain, and the caption says the PLL bridges are not drawn. The middle row draws only CPU-bound arrows, but `u_cpu_iso_ack_sync` crosses from `cpu_core_clk` to `core_clk`.
- **Fix:** Label the box "`u_apb_dbg_cdc`" and the source "APB debug port", and add a return arrow "isolation acknowledge" from the CPU domain to the PMU.

### 26. FIGURE: `fig:tm:mod:cdc-gray-fifo:block` readability
- In the render, the two dashed domain boxes overlap in the middle. The label `rd_gray_sync_w` is cut off and runs into the `u_rd_ptr_to_wr` box ("d_gray_sync_r"). The label `mem_q[rd_bin_q]` sits on the domain boundary. The structure is correct: every flop is in the right domain and every arrow points the right way.
- **Fix:** Move `s2` to about x=4.6 and `s1` to about x=11.0, put the small labels below the arrows, and shorten the dashed read label.

### 27. FIGURE: `fig:tm:mod:cdc-gray-fifo:timing` pointer width
- The edges are correct: `wr_gray_q` changes at the write edge, then `sync_q[0]`, `wr_gray_sync_r` and `rd_valid_o` change at the next three rd edges. But the values `00 -> 01` are a 2-bit pointer (DEPTH 2), while the default DEPTH 4 has a 3-bit pointer (`000 -> 001`).
- **Fix:** Add "with DEPTH equal to 2" to the caption, or use 3-bit values.

### 28. FIGURE / UNCLEAR: `fig:tm:mod:apb-cdc-bridge:timing` SETUP cycle
- I checked every edge and all are correct: `req_q` rises at 0.5, `req_m` at 3, `m_psel_o` at 5, `m_penable_o` at 7, `ack_q` at 9, `ack_s` at 10.5, `req_q` falls at 11.5, `req_m` falls at 15, `ack_q` falls at 17, `ack_s` falls at 18.5, and `s_pready_o` is high from 19.5 to 20.5. The only problem is that the SETUP phase (`s_psel_i` high, `s_penable_i` low) lasts only half a unit before the first edge, so the SETUP cycle is hard to see.
- **Fix:** Start `s_psel_i` one full unit earlier.

### 29. STYLE (DS section intros): `\code{cdc\_sync}` renders with a visible backslash
- The render of `ds-03.png` shows "cdc\_sync" and "cdc\_reset\_sync". The same source form is in the intros of `cdc_gray_fifo`, `apb_cdc_bridge` and `async_axi_fifo`. The TM uses `\code{cdc_sync}`.
- **Fix:** Use `\code{cdc_sync}` and so on.

### 30. STYLE (DS-CDC-061, DS-CDC-066, DS-CDC-103): "No other entry must appear", "no old entry must remain visible", "No transfer must complete"
- **Fix:** Use "must not": "An entry that the write side did not hand over must not appear", "An old entry must not be visible", "The `m_*` face must not complete a transfer for this request". DS-CDC-024 and DS-CDC-060 put the verification ("The Makefile target ... is the negative control") in the normative body. Move it to an Information note.

### 31. UNSUPPORTED (DS "FIFO with gray pointers and registered flags", Alternatives): "A flag that is a combinational compare would not close timing, because both operands of the compare are not stable for a whole local clock period."
- **What the code shows:** Both operands (`wr_gray_q` or `rd_gray_q`, and the synchronised pointer) are flops in the local domain. A combinational compare of two local flops is ordinary synchronous logic. The claim comes from the old header, but the code does not support it. What the registered flag really gives is a glitch-free, flop-driven `wr_ready_o` / `rd_valid_o`, with no combinational path from the synchroniser output to a port.
- **Proposed text:** "A combinational flag would drive the ready and valid outputs from compare logic. A registered flag drives them from a flop."

### 32. UNCLEAR: DS-CDC-101 "Only the levels `req_q` and `ack_q` and the reset status ... cross through synchronisers"
- **What the code shows:** `s_rst_n_i` also crosses into the `m_clk_i` domain through `rst_both_n -> u_m_rst_sync`.
- **Fix:** Add "apart from the two reset synchronisers". Verification: the stream test does not test this structural rule. `review` is the real verifier, so list it first.

### 33. UNCLEAR: DS-CDC-114, DS-CDC-115, DS-CDC-154 are true only with `scanmode_i` low
- **What the code shows:** In scan mode, `rst_n_o = scan_rst_ni` and the functional resets have no effect.
- **Fix:** Add "With `scanmode_i` low," to each rule.

### 34. UNCLEAR: DS-CDC-066 "When both resets assert while the FIFO is full"
- **What the code shows:** The test asserts both resets at the same time. Two resets that assert one after the other, without overlapping, act as two one-sided resets (DS-CDC-067).
- **Fix:** "When both resets are asserted together while the FIFO is full..."

### 35. UNCLEAR: DS-CDC-100 "Each transfer must use a return-to-zero handshake"
- A forced completion (`!req_fwd_q`) never raises `req_q`.
- **Fix:** "Each forwarded transfer that the destination answers..."

### 36. UNCLEAR (TM `cdc_sync` Verification): "The target `periph_sync_stages` runs the peripherals that use the module with 3 ranks."
- **What the code shows:** The target runs UART, interrupt controller, SPI and GPIO only, not I2C.
- **Fix:** Name the four peripherals.

### 37. UNCLEAR (UM, last paragraph of "Verify the crossings"; TM `cdc_gray_fifo` Verification): equivalence script
- **What the code shows:** `equiv_cdc_gray_fifo_depth.sh` compares the working tree with `OLD_REF` (default `origin/main`). It proves nothing about a change that is already on `origin/main`. It needs `YOSYS` and `SLANG_PLUGIN` (the defaults are host-specific nix store paths), and it exits 3 when a tool is missing.
- **Fix:** "It compares the working-tree module with the version at `OLD_REF` (default `origin/main`). Set `YOSYS` and `SLANG_PLUGIN` on a new host."

### 38. WEAK-VERIFY (minor): DS-CDC-002 and DS-CDC-062
- **What the code shows:** `test_white_box_gray_pointer_single_bit_change` samples `wr_gray_q` only after each complete write transaction. The stronger check is the per-edge monitor in `tb_cdc_gray_fifo` (`*_gray_viol_o`), which every `run_stream_*` test asserts. Those tests are not cited.
- **Fix:** Cite `test_cdc_gray_fifo.py::run_stream_7_3_random` (monitor) as well.

### 39. UNCLEAR (`cdc.yaml`): parameter legality
- `RAND_CDC_DELAY_PCT`: the legal range is "0 to 100", but the description says "With 100 or more". Pick one. The RTL comment says `[0,100)`, and the code `$urandom_range(0,99) < PCT` makes 100 mean "always".
- `DW` "a multiple of 8" and `SW` "DW / 8": no elaboration check enforces them. Write "should be" or name them as AXI conventions.

### 40. UNCLEAR (DS Definitions, "Clock domain"): "The constraint files declare two clocks for the SoC"
- The Sky130 check file and the TM instance table also use the TCK domain (`tck_i`), and `u_sync_a` and `u_sync_b` use the scan clock.
- **Fix:** "...two functional clocks. The test logic adds the TCK domain and the scan clock."

## Requirement verdicts (53)

| Req | Verdict | Req | Verdict |
|---|---|---|---|
| DS-CDC-001 | 5 | DS-CDC-100 | 35 (otherwise OK; the structural test is good) |
| DS-CDC-002 | OK (true); 38 minor | DS-CDC-101 | 32 |
| DS-CDC-003 | 15 | DS-CDC-102 | 16 |
| DS-CDC-005 | OK | DS-CDC-103 | 2, 10, 30 |
| DS-CDC-006 | OK (the bounds in the files are 0.5, 0.9 and 1.0 of the receiving period) | DS-CDC-104 | OK (race test is good) |
| DS-CDC-020 | OK | DS-CDC-105 | OK |
| DS-CDC-021 | OK | DS-CDC-106 | 2 |
| DS-CDC-022 | OK (user rule, review) | DS-CDC-107 | OK |
| DS-CDC-023 | OK (review; a lint without `SIMULATION` could test it) | DS-CDC-108 | OK (four ratios) |
| DS-CDC-024 | OK; 30 (style) | DS-CDC-109 | OK as a user rule; 20 (consequence) |
| DS-CDC-040 | OK | DS-CDC-110 | OK (the coverage gate fails on a miss) |
| DS-CDC-041 | OK (`..._still_retimed_by_the_chain` checks "not earlier") | DS-CDC-111 | OK (user rule) |
| DS-CDC-042 | OK | DS-CDC-112 | OK |
| DS-CDC-043 | 18 | DS-CDC-113 | OK |
| DS-CDC-044 | OK (user rule) | DS-CDC-114 | OK; 33 |
| DS-CDC-045 | 14 | DS-CDC-115 | 9; 33 |
| DS-CDC-046 | OK (test holds `scan_rst_ni` = 0 through the release) | DS-CDC-116 | 13 |
| DS-CDC-060 | OK; 30 (style) | DS-CDC-150 | OK (review; the cited test does not prove "no other sequential logic") |
| DS-CDC-061 | OK; 30 (style) | DS-CDC-151 | OK |
| DS-CDC-062 | OK; 38 | DS-CDC-152 | 11 |
| DS-CDC-063 | OK | DS-CDC-153 | 12 |
| DS-CDC-064 | OK (exact count measured; `d4` mutant targets it) | DS-CDC-154 | OK; 33 |
| DS-CDC-065 | OK | DS-CDC-155 | OK ("same path" is structural, so review) |
| DS-CDC-066 | OK; 34, 30 | DS-CDC-156 | OK |
| DS-CDC-067 | OK | DS-CDC-157 | **1 (WRONG)** |
| DS-CDC-068 | OK (`peak == depth` is asserted) | DS-CDC-158 | OK |
| | | DS-CDC-159 | **8 (WRONG)** |

## The eight source disagreements

1. **`-datapath_only`, RTL headers vs SDC.** The headers say "STA must set set_max_delay -datapath_only". The check files use plain `set_max_delay -from -to`, and the SDC comments say "OpenSTA has no set_max_delay -datapath_only". The chapters are right: DS-CDC-006 names no tool, and the TM explains both forms.
2. **`async_axi_fifo` depth comment.** The comment says "validated at >= 4 only -- cdc_gray_fifo itself accepts 2 since 3snb". The code has no check in `async_axi_fifo`, and the guard in `cdc_gray_fifo` accepts 2. The TM and `cdc.yaml` say this correctly. The comment itself holds a tracker ID ("3snb", "#96") and a reference to a delivery report, which is a source style problem.
3. **A docstring citing header text that does not exist.** `test_apb_cdc_bridge.py` cites header sections ("Availability-gating exception", "No fabricated destination-side write, RZ argument") that the current header no longer has. The chapters do not rely on them. They do repeat the substance of the header claim, and finding 2 shows that claim fails in one race.
4. **"No injector exists" docstring.** `test_soc_multiclock_reset.py` says "No injector exists today (see rtl/soc/cdc/cdc_sync.sv)". The code has the `g_rand_cdc_delay` block under `SIMULATION`, default off, and nothing sets `RAND_CDC_DELAY_EN`. The TM states the true situation: the model exists and no regression uses it.
5. **`cdc_config.yml` waivers.** The references `async_axi_fifo.sv:174-175`, `apb_cdc_bridge.sv:226-227`, `:558-587` and `:574-587` are stale. `rst_both_n` is now at lines 123-124 and 70-71, and the response capture at 296-309. The waiver text says "2-phase-handshake" and "ack toggle", but the code is a 4-phase level handshake. The chapters do not repeat these errors. The config file needs a fix (outside these chapters).
6. **`SYNC_STAGES`+2 vs +1.** The code gives exactly +1 in simulation, and `run_empty_boundary` measures it. The chapters state +1 and quote +2 without reconciling the two (finding 19).
7. **No check-SDC section for `u_apb_pll_cdc`.** The code: s = `core_clk`, m = `pll_ref_clk`, and both are `sys_clk` in the SDC. The TM gives the right reason, but it hides that the crossing is real and unchecked (finding 4).
8. **Reset-hold wording.** `cdc_reset_sync` says "STAGES+1 periods of `clk_i`". `async_axi_fifo` says "SYNC_STAGES+1 periods of the other clock". `apb_cdc_bridge` says both. The DS takes the first form for `cdc_reset_sync` and the `m_rst_n_i` form for the APB bridge, and has no rule for the AXI bridge. The module needs neither form (finding 18). The owner must decide.

## Confirmed right (checked against code)
- **`cdc_sync`:** the latency is exactly `STAGES` edges; the reset is asynchronous to `RESET_VAL` at every rank; the guard `STAGES < 2`; the `magic_cdc` attribute on `sync_q`. The settling-delay model: `d_prev_q` follows `d_i` every edge, the hold is drawn only when `d_i !== d_prev_q`, it adds at most one cycle if the input is stable, it is seeded once at time 0, and it exists only under `SIMULATION`, which the cocotb Makefile defines and which no instance enables. Test facts: 6+1 instances, 4 tests, `cdc_sync_stages1_neg` greps the guard message, and `periph_sync_stages` uses `-GSYNC_STAGES=3`.
- **`cdc_reset_sync`:** the input mux and output mux; rank 0 loads 1; one `always_ff` for each rank; the output follows `scan_rst_ni` in scan mode. Both timing figures are correct edge by edge. 7 tests, `STAGES` = 2 only, no negative target.
- **`cdc_gray_fifo`:** `PTR_W = $clog2(DEPTH)+1`; gray = `b ^ (b>>1)`; registered flags with `empty_q` reset to 1 and `full_q` reset to 0; `wr_ready_o = wr_rst_n_i && !full_q`; `rd_valid_o = !empty_q`; the depth-2 full compare (all four rows of the table and the "three entries" claim); the 2-bit gray ring; the reset domain of each synchroniser; latency +1 in each direction; mutants a1-a6, b1, c1-c3, d1-d5 (15); lint depths 2, 4, 8, 16; negative depths 0, 1, 3, 6, 12; the stream clock pairs; the monitor is sticky and cleared only by `mon_rst_n_i`; drive and sample are mid-cycle. Block structure and timing figure are correct (except findings 26 and 27).
- **`apb_cdc_bridge`:** both state machines (states, transitions, the priority of `ack_s`); the capture at SETUP; `req_fwd_q`; the `req_q` clamp; the forced response (0, error); `S_DROP` waits for `ack_s` to fall; one-cycle pready in `S_DONE`; the reset topology (source from `s_rst_n_i` only, destination from `rst_both_n`); the status polarity; the false-alive window of `SYNC_STAGES_TO_S`; the `m_*` outputs hold the last command; `s_prdata_o` and `s_pslverr_o` hold the last response. The timing figure is correct edge by edge (finding 28 is presentation only). 23 tests, the clock pairs, the stream of 150, the latency test bound derived and not exact. ADDR_W is 12 at all three instances; `s_pstrb_i = 4'hF` and `m_pstrb_o` is unused at `u_apb_dbg_cdc`.
- **`async_axi_fifo`:** 5 FIFOs and 2 reset synchronisers, both on `rst_both_n`. Each FIFO uses one stage count for both directions (AW, W, AR: `_TO_M`; B, R: `_TO_S`), which the TM explains correctly. Payload widths 45, 37, 2, 45, 35 and depths 4, 8, 4, 4, 8. 28 tests and the clock pairs. `s_rst_n_i = cpu_core_rst_n`; the ISO clamp sits on the s face.
- **Constraints:** the check-file parts (fallback 0.9, false path on `*rst_sync*` reset pins, FIFO pointers 0.5, `req_q` and `ack_q` at 1.0 for `pll2` and `dbg`, PMU and IRQ, coverage gate); the make targets and scripts exist; the script exit codes are 0, 1, 2; the Sky130 counterpart files exist.
- **Instances:** the instance table in the TM matches every instantiation in `rtl/` (38 instantiations in 14 files).
- **UM:** the code listings use the right port and parameter names. `make cdc`, `CDC_STRICT=1`, the path `sim/build/cdc/soc_top_cdc.txt`, `tools/cdc/versions.env` and the last line `SURVIVORS:` of the mutation script all exist.
- **Style:** "must" appears only inside requirement bodies. There are no dates, tracker IDs, run names, file:line references or section numbers in the chapters. The only figures with units are testbench clock periods, which are not results.

## Not reviewed
- The generated `requirements-cdc.tex` map table, `labels.tsv`, `glossary.tex` and the other cross-reference plumbing. Cross-book references render as "??" in the PNGs. I assume this is because each book was built alone.
- PNG pages other than tm-01, 04, 07, 09, 11, 13, 14, 15, 16 and ds-03. I checked the TikZ source of the other figures (reset-sync block, ring, AXI channels, state machines) but did not look at their renders. I did not open the UM renders.
- `cdc_gate.py` internals; `check_cdc_timing_sky130.tcl`; the content of the sign-off `phase5_soc_multiclock.sdc` beyond its comment; `tb_async_axi_fifo.sv`, `tb_apb_cdc_bridge.sv` and `tb_cdc_sync.sv`; the valid-withdrawal monitors; `test_soc_pmu_multiclock.py`; CI wiring (whether `make cdc CDC_STRICT=1` or the negative targets run in CI); whether the mutation script exits non-zero on a survivor (I saw the print line only).
- The `soc_top` claim "A PMU power cycle keeps the state of the bridge, as it keeps the state of the CPU", given that `cpu_domain_rst_n` includes the PMU reset. The TM copies it from the `soc_top` comment, and I did not resolve it.
- The tests were not run. Every verdict above comes from reading the code.
