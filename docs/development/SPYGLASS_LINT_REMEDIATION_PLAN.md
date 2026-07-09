# Spyglass Lint Remediation Plan (Handoff)

**Status**: Proposal / handoff — **no RTL modified yet**. Drafted 2026-07-09.
**Owner branch**: `claude/spyglass-lint-violations-iib0r4`
**Purpose**: Enumerate every Synopsys Spyglass lint violation reported against the `soc_top` design,
with a precise, file-level remediation instruction (fix or documented waiver) so a subsequent session
can execute the cleanup without re-discovering scope.

---

## 0. Ground rules & context

- Spyglass is **not installed in this repo/environment** — remediation must be pattern-based and
  re-verified with the repo's own gates: `cd sim && make lint && make lint_soc && make verible`.
- The screenshots that seeded this plan show only a **subset per category**. **Every RTL file under
  `rtl/` must be swept for each rule** — do not fix only the files named below.
- **Two decisions are locked** (confirmed with the user):
  - **Design-intent violations → WAIVE + DOCUMENT** (do not rewrite verified RTL for style). In
    particular the CPU pipeline stays **synchronous-reset** — converting to async reset is explicitly
    out of scope (it would require whole-CPU re-verification + ASAP7 PPA re-sign-off; tracked as the
    existing P3 audit item in `CODING_GUIDELINES.md` §1.4).
  - **Non-synthesizable `initial`/`$fatal`/`$readmemh` → GUARD WITH PRAGMAS** (`` `ifndef SYNTHESIS ``),
    keeping them for simulation while hiding them from lint/synth.
- Existing verified RTL is grandfathered per `CODING_GUIDELINES.md`. These lint fixes are the
  exception — they are mechanical/behavior-preserving or documented waivers, each re-verified.

---

## 1. Violation catalog & disposition summary

| # | Spyglass rule(s) | Meaning | Disposition |
|---|------------------|---------|-------------|
| A | **IND** (DESIGN) | `clk`/`rst_n` "not declared yet" — artifact of `` `default_nettype none `` | **FIX** — remove all `default_nettype` directives |
| B | **SM_BNP / W336 / NonBlockAssign** | Blocking (`=`) mixed with non-blocking (`<=`) in one `always_ff` | **FIX** — reset for-loops → `<=` |
| C | **SM_IGN_INITIAL / W430 / W213 / LINT_SV_STRING_USED_IN_DESIGN** | `initial` blocks, `$fatal` PLI, string literals not synthesizable | **FIX** — guard with `` `ifndef SYNTHESIS `` |
| D | **UndrivenInTerm-ML** | `boot_rom.mem[...]` undriven under synthesis view | **FIX** — resolved by guarding `$readmemh` (item C) + waiver note |
| E | **W192** | Empty `begin/end` block | **FIX** — collapse to `;` / null statement |
| F | **LINT_IMPROPER_RANGE_INDEX** | `int` index wider than the indexed array needs | **FIX** — size the index variable |
| G | **SignedUnsignedExpr-ML** (×34) | Signed expr mixed with unsigned expr | **FIX (selective) + WAIVE** |
| H | **STARC05-2.10.3.1** | Operand width mismatch on `PLL_IMPL == "RNM"` string compare | **WAIVE** (or optional refactor) |
| I | **STARC05-2.3.6.1 / UnInitializedReset-ML** | No-reset flop/array coexists with async-reset flops; signals not init in reset | **WAIVE** (memories/stacks) + selective |
| J | **W392** | `core_rst_n` "used with different polarity" (cross-module name clash) | **WAIVE** (false positive) |
| K | **SynchReset-ML** (×56) | Synchronous reset used (entire CPU pipeline + peripherals) | **WAIVE** (intentional, grandfathered) |

---

## 2. FIX items — detailed instructions

### A. Remove `` `default_nettype none `` (rule IND) — ALL FILES

**Why**: Spyglass raises `IND / DESIGN` ("Identifier 'clk'/'rst_n' has not been declared yet") on the
port list of files that open with `` `default_nettype none ``. Per user direction, remove the
directive project-wide.

**Action**: In every RTL file, delete both:
- the opening `` `default_nettype none `` (near top of file), and
- the closing `` `default_nettype wire `` (near end of file), where present.

Also delete/adjust the header comment lines that advertise the convention (e.g.
`rtl/soc/boot_rom.sv:15`, `rtl/soc/pll/pll_apb_regs.sv:39`, `rtl/soc/pll/pll_clkgen_stub.sv:28`).

**Affected files (31 — from `grep -rn default_nettype rtl/`)** — sweep for any added since:

```
rtl/gpu/gpu_memory_unit.sv        rtl/gpu/warp_scheduler.sv         rtl/gpu/shared_memory.sv
rtl/gpu/memory_coalescer.sv       rtl/gpu/gpu_top.sv                rtl/gpu/gpu_compute_unit.sv
rtl/gpu/gpu_command_queue.sv      rtl/gpu/vector_alu.sv             rtl/gpu/vector_register_file.sv
rtl/periph/dma_engine.sv          rtl/periph/interrupt_controller.sv rtl/periph/spi_controller.sv
rtl/periph/timer.sv               rtl/periph/uart_controller.sv
rtl/cpu/core/pipeline/rv32i_pipeline_ex.sv    rtl/cpu/core/pipeline/rv32i_pipeline_ex1b.sv
rtl/cpu/core/pipeline/rv32i_pipeline_ex1c.sv  rtl/cpu/core/pipeline/rv32i_pipeline_ex2.sv
rtl/cpu/core/rv32i_forwarding_unit.sv
rtl/soc/apb_interconnect.sv       rtl/soc/soc_top.sv                rtl/soc/axil_to_apb.sv
rtl/soc/boot_rom.sv               rtl/soc/axilite_to_axi4.sv        rtl/soc/axi4_to_axilite.sv
rtl/soc/soc_bus.sv                rtl/soc/apb4_register_bank.sv
rtl/soc/pll/pll_clkgen.sv         rtl/soc/pll/pll_apb_regs.sv       rtl/soc/pll/pll_clkgen_stub.sv
rtl/soc/pll/pll_subsystem.sv
```

> Note: several files have `none` **without** a matching `wire` (e.g. `interrupt_controller.sv`,
> `timer.sv`, `soc_top.sv`, `axilite_to_axi4.sv`, `axi4_to_axilite.sv`, `soc_bus.sv`) — remove the
> lone `none` too.

**Verify**: `grep -rn default_nettype rtl/` returns nothing; `make lint`/`lint_soc` still clean
(Verilator still catches implicit nets via `IMPLICIT`/`UNDRIVEN`).

### B. Blocking→non-blocking in `always_ff` reset loops (rules SM_BNP / W336 / NonBlockAssign)

**Why**: an `always_ff` block that assigns `<=` everywhere but uses `=` in its reset for-loop mixes
blocking and non-blocking in one sequential process.

**Fix**: change the reset-loop `=` to `<=`.

| File | Lines | Change |
|------|-------|--------|
| `rtl/mem/rv32i_dcache.sv` | 951–953 | `valid_array[j] = 1'b0;` → `<=`; `dirty_array[j] = 1'b0;` → `<=` |
| `rtl/mem/rv32i_icache.sv` | 604–605 | `valid_array[j] = 1'b0;` → `<=` |

**Also sweep** every `always_ff` for a for-loop (or any statement) using `=`. Do **not** touch `=` in
`always_comb` (correct there).

**`rv32i_csr_file.sv:334-339` (csr_cur/csr_nxt)** — these are **local automatic temporaries** declared
and consumed within the same `always_ff` iteration (blocking is correct for locals). W336/
UnInitializedReset flags them, but converting to `<=` would be a **functional bug**. **Disposition:
WAIVE** (see §3), keep the blocking locals. Optionally lift the computation into an `always_comb`
helper if a future refactor wants zero waivers — not required.

### C. Guard non-synthesizable `initial` / `$fatal` / `$readmemh` (rules SM_IGN_INITIAL / W430 / W213 / LINT_SV_STRING)

**Why**: parameter-check assertions (`initial begin if (DW!=32) $fatal(...) end`) and the boot ROM
hex preload use constructs synthesis ignores; Spyglass flags the `initial`, the `$fatal` PLI, and the
string literals.

**Fix**: wrap them so simulation keeps them but lint/synth skip them:

```systemverilog
`ifndef SYNTHESIS
    initial begin
        if (DW != 32) $fatal(1, "apb4_register_bank requires DW == 32");
        if (SW != 4)  $fatal(1, "apb4_register_bank requires SW == 4");
    end
`endif
```

| File | Line | Construct |
|------|------|-----------|
| `rtl/soc/apb4_register_bank.sv` | 58–61 | param-check `initial $fatal` |
| `rtl/soc/axi_lite_register_bank.sv` | 75–78 | param-check `initial $fatal` |
| `rtl/soc/axil_to_apb.sv` | 93–95 | param-check `initial $fatal` |
| `rtl/soc/boot_rom.sv` | 102–113 | `$readmemh` preload — already has a `__pnr__` guard; wrap the whole `initial` in `` `ifndef SYNTHESIS `` (or ensure the lint run defines the synth macro) so the `initial` disappears from the lint view |

**Note on `pll_rnm.sv:155` `initial`** — this is a **real-number behavioral model** (RNM), never
synthesized and typically outside the synth/lint filelist. Confirm whether the Spyglass run includes
it; if so, guard identically. Otherwise leave (behavioral-only file).

### D. Undriven boot_rom memory read (rule UndrivenInTerm-ML) — `rtl/soc/boot_rom.sv:224`

`assign s_rdata = mem[r_idx];` where `mem` is loaded only in the (synthesis-ignored) `initial`. Once
item C hides the `initial` from the synthesis view, `mem` reads as fully undriven. This is inherent to
a `$readmemh`-loaded behavioral ROM. **Disposition**: accept + **waive** `UndrivenInTerm-ML` on
`soc_top.u_boot_rom.mem` with rationale "behavioral ROM, contents back-annotated at bring-up / loaded
by boot flow." (A synthesizable `case`-based ROM is possible but drops the hex-file flexibility — not
recommended for this behavioral SoC model.)

### E. Empty blocks (rule W192)

| File | Line | Current | Fix |
|------|------|---------|-----|
| `rtl/cpu/core/pipeline/rv32i_pipeline_ex1c.sv` | 155 | `3'b010: begin // Word store — defaults already set above` (empty) | `3'b010: ; // Word store — defaults already set above` |
| `rtl/cpu/core/pipeline/rv32i_pipeline_if.sv` | 144 | `end else if (stall_if_id) begin // Hold current IF/ID` (empty) | Either add explicit hold `if_id_reg_o <= if_id_reg_o;` **or** drop the empty `else if` and fold its condition into the trailing `else`. Prefer the explicit self-assign to keep intent readable. |

Sweep for any other empty `begin ... end` / empty case arms.

### F. Oversized index variable (rule LINT_IMPROPER_RANGE_INDEX) — `rtl/gpu/warp_scheduler.sv:111-116`

`cand_i` is declared `int` (32-bit) but indexes `warp_busy`/`warp_done` (max value 7). Replace the
`int` temporary with a sized vector:

```systemverilog
// before
for (int i = 0; i < N_WARPS; i++) begin
    int cand_i;
    cand_i = (int'(rr_ptr) + i) % N_WARPS;
    if (!found && cand_i < int'(n_warps_q) && !warp_busy[cand_i] && !warp_done[cand_i]) ...
// after
for (int i = 0; i < N_WARPS; i++) begin
    logic [WARP_W-1:0] cand_i;
    cand_i = WARP_W'((int'(rr_ptr) + i) % N_WARPS);
    if (!found && (cand_i < n_warps_q) && !warp_busy[cand_i] && !warp_done[cand_i]) ...
```

Re-check the `cand_i < int'(n_warps_q)` comparison keeps unsigned semantics (both `[WARP_W-1:0]`).
Sweep GPU/coalescer for other `int` loop temporaries used as small-array indices
(`memory_coalescer.sv` uses `3'(i)` casts — already sized, OK).

### G. Signed/unsigned mix (rule SignedUnsignedExpr-ML, ×34 subset shown)

Two sub-classes — treat differently:

1. **Clearly-unintended mixes → FIX** with explicit casts / matched widths. Examples to review:
   - `rtl/gpu/gpu_top.sv:250` `assign n_warps_w = |n_warps_raw[9:WARP_W] ? WARP_W'(N_WARPS-1) : n_warps_raw[WARP_W-1:0];`
     — make both ternary arms explicitly unsigned (`unsigned'(WARP_W'(N_WARPS-1))`).
   - Width-cast comparisons/selects flagged elsewhere in `gpu_top`, `warp_scheduler`, coalescer.
2. **Functionally-required signed math → WAIVE (comment inline)**:
   - `rtl/cpu/core/rv32i_alu.sv:76` `ALU_SRA: result = $signed(operand_a) >>> shamt;` — arithmetic
     right shift **must** be signed; do not "fix".
   - `parameter string` declarations flagged as signed/unsigned (`soc_top.sv:55,64`,
     `boot_rom.sv:39`, `pll_subsystem.sv:51`, `pll_clkgen.sv:36`) — string parameters are benign;
     **waive**.

Because Spyglass shows only 34 of N, the executing session must run Spyglass (or approximate with
Verible/Verilator width lint) to enumerate the full set, then bucket each into FIX vs WAIVE using the
rule above.

---

## 3. WAIVE + DOCUMENT items

Create a repo Spyglass waiver file (proposed path **`lint/spyglass/waivers.awl`**) — new directory,
since none exists today. Each waiver carries a one-line rationale. Reference it from the Spyglass run
script and from `CODING_GUIDELINES.md`.

| Rule | Waiver scope | Rationale |
|------|-------------|-----------|
| **SynchReset-ML** | CPU core/pipeline + peripheral modules | Intentional, signed-off **synchronous-reset** discipline (`CODING_GUIDELINES.md` §1.4). Async conversion is a separate P3 effort requiring full regression + PPA re-sign-off. |
| **STARC05-2.3.6.1 / UnInitializedReset-ML** | `warp_scheduler.div_stack`, `div_depth` no-reset stack; large memory arrays; `rv32i_csr_file` local temporaries (`csr_cur`/`csr_nxt`); combinational defaults (`do_fire`) | No-reset **memory/stack** arrays are intentional (reset would cost a huge mux); local blocking temporaries and combinational defaults are not flip-flops. |
| **W392** | `dma_engine` / `soc_top` `core_rst_n` | False positive from cross-module signal-name collision, not an actual polarity conflict. |
| **STARC05-2.10.3.1** | `pll_clkgen.sv:63` `PLL_IMPL == "RNM"` | Elaboration-time **string parameter** compare selecting the PLL implementation; not real hardware. (Optional refactor: map `PLL_IMPL` string → `localparam int` selector to silence without waiver.) |
| **SignedUnsignedExpr-ML** (residual) | `rv32i_alu` `$signed >>>`, `parameter string` decls, other functionally-required signed ops | Signed arithmetic / string params are correct by design. |
| **UndrivenInTerm-ML** | `boot_rom.mem` | Behavioral `$readmemh` ROM; contents supplied by boot flow, not RTL-driven. |

---

## 4. Coding-guideline updates (`docs/development/CODING_GUIDELINES.md`)

1. **§1.3 Language constructs** — **reverse** the current mandate. Replace:
   > `` `default_nettype none `` at the top of each file (restore with `` `default_nettype wire ``…)
   with guidance to **not** use `default_nettype` directives (Spyglass `IND` conflict); rely on
   Verilator/Verible for implicit-net detection.
2. Add a new subsection **"1.8 Spyglass lint discipline"** codifying, for new RTL:
   - Non-blocking (`<=`) exclusively in `always_ff` (incl. reset for-loops); blocking only in
     `always_comb` and local automatic temporaries.
   - No empty `begin/end` blocks or empty case arms — use `;`.
   - Size index/loop-temporary variables to the array they index (no bare `int` indices).
   - No bare `initial` / `$fatal` / `$readmemh` / `$display` in synthesizable RTL — guard with
     `` `ifndef SYNTHESIS ``.
   - Match signedness/width in expressions; use explicit `signed'()`/`unsigned'()` casts.
   - List the standing **waivers** (synchronous CPU reset, no-reset memories, cross-module reset
     naming, string-param compares) and point to `lint/spyglass/waivers.awl`.
3. Update the **enforcement summary** table (§6) to mention Spyglass + the waiver file.

---

## 5. Execution order & verification (for the implementing session)

1. Branch `claude/spyglass-lint-violations-iib0r4` (create from latest default if the prior PR merged).
2. Land in reviewable commits, e.g.:
   - `[RTL] Remove default_nettype directives (Spyglass IND)` — item A.
   - `[RTL] Non-blocking reset loops in i/d-cache valid/dirty arrays` — item B.
   - `[RTL] Guard non-synth initial/$fatal/$readmemh blocks` — items C/D.
   - `[RTL] Fix empty blocks, size warp_scheduler index, signed/unsigned casts` — items E/F/G.
   - `[Doc] Spyglass waiver file + coding-guideline updates` — §3/§4.
3. **Verify after each**: `cd sim && make lint && make lint_soc && make verible` (clean),
   `cd sim && make phase3_all` (cache functional regression), and a `soc_top` boot/smoke sim to prove
   the blocking→non-blocking and guarded-initial changes are behavior-preserving.
4. If Spyglass access is available, re-run it and confirm the FIX categories are clear and the WAIVE
   categories map to the waiver file (0 unexpected).
5. Push; open PR only if the user asks.

---

## 6. Open confirmations for the next session

- Confirm the exact **Spyglass synthesis macro** name the lint run defines (assumed `SYNTHESIS`) so the
  `` `ifndef `` guards actually suppress items C/D in Spyglass, not just in the synth tool.
- Confirm whether `rtl/soc/pll/pll_rnm.sv` (RNM behavioral model) is in the Spyglass filelist.
- Confirm the preferred waiver-file location/format (`lint/spyglass/waivers.awl` vs `pnr/spyglass/`)
  and where the Spyglass run script lives.
