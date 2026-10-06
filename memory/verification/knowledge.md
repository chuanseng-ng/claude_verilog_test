# Verification Knowledge Base — RV32I SoC Project

## Build Environment

### nix-shell Python Conflict (CRITICAL — affects all sim_build rebuilds)

When RTL changes require a fresh Verilator compilation, `make -C sim dcache` (or
any sim target) fails with:

```
Fatal Python error: init_fs_encoding: failed to get the Python codec of the filesystem encoding
ModuleNotFoundError: No module named 'encodings'
```

Root cause: `verilated.mk` hardcodes `PYTHON3 = /nix/store/.../python3.11` but the
system has `PYTHONHOME=/usr` pointing to Python 3.10 stdlib — so Python 3.11 cannot
find `encodings`.

Fix procedure for any sim_build_* directory that needs rebuilding:

**IMPORTANT — cocotb binary naming rule**: cocotb's Verilator makefile always uses
`--prefix Vtop -o Vtop` regardless of TOPLEVEL name. When rebuilding manually you
MUST pass these flags plus `--vpi -DCOCOTB_SIM=1` and include the cocotb
`verilator.cpp` shim. The elaboration generates `Vtop.mk`; the binary is called
`Vtop`. If you omit these flags, you get `Vrv32i_<toplevel>` which cocotb cannot find.

1. Run elaboration inside nix-shell (generates Vtop*.cpp):
   ```bash
   COCOTB_SHARE=/home/neuromorphic/.local/lib/python3.10/site-packages/cocotb/share
   COCOTB_LIBS=/home/neuromorphic/.local/lib/python3.10/site-packages/cocotb/libs
   cd ~/Downloads/Github/librelane && nix-shell --run "
     /nix/store/mky7gdsf8m3da333lxz2mjf2n3n1v1xy-verilator/bin/verilator -cc --exe \
       -Mdir <sim_build_dir> \
       --prefix Vtop -o Vtop \
       --top-module <toplevel> \
       --timescale 1ns/1ps --no-timing \
       -DCOCOTB_SIM=1 --vpi --public-flat-rw \
       -Wno-fatal -Wno-WIDTH -Wno-CASEINCOMPLETE -Wno-TIMESCALEMOD -Wno-UNOPTFLAT \
       -LDFLAGS \"-Wl,-rpath,\$COCOTB_LIBS -L\$COCOTB_LIBS -lcocotbvpi_verilator\" \
       [sources...] \$COCOTB_SHARE/lib/verilator/verilator.cpp
   "
   ```
2. Build binary outside nix-shell with system python3:
   ```bash
   cd <sim_build_dir>
   rm -f Vtop__ALL.o Vtop__ALL.a Vtop
   make PYTHON3=/usr/bin/python3 \
        CXX=<proj>/sim/cxx_shim.sh LINK=<proj>/sim/cxx_shim.sh \
        -f Vtop.mk
   ```
3. Once Vtop binary exists, `make -C sim <target>` inside nix-shell finds the
   pre-built binary and skips compilation, going straight to simulation.

### pytest Location

System python3 has no pytest. Use:
```bash
/home/neuromorphic/Downloads/Github/librelane/venv/bin/pytest tb/tests/ -v
```

### Verilator path (nix)
`/nix/store/xjx9zx3vaz367c7lbnvsd1isvqfkmgg7-verilator-5.048/bin/verilator`

(Updated 2026-05-19: old path `mky7gdsf8m3da333lxz2mjf2n3n1v1xy-verilator` is stale.)

## SRAM Simulation Model Verilator Guards (sram_1rw_256x32_freepdk45.v)

Two Verilator-incompatible constructs exist in the FreePDK45 SRAM behavioral model
and are guarded with `` `ifndef VERILATOR ``. These guards MUST be preserved in any
future edits to `sim/sram_1rw_256x32_freepdk45.v`.

### Guard 1 — `%m` in `$display` (STMTDLY / Internal Error)

Verilator 5.048 raises an internal error (`Display with %m but no AstScopeName`)
when `$display` contains `%m` inside a module compiled with `--no-timing`. Fixed by
splitting to a `` `ifndef VERILATOR `` / `` `else `` / `` `endif `` block:

```verilog
`ifndef VERILATOR
  $display($time," Reading %m addr0=%b dout0=%b", addr0_reg, mem[addr0_reg]);
`else
  $display($time," Reading addr0=%b dout0=%b", addr0_reg, mem[addr0_reg]);
`endif
```

### Guard 2 — `#(T_HOLD) dout0 = 32'bx` (BLKANDNBLK error)

The posedge always block uses a blocking delayed assignment to `dout0`; the negedge
read block uses a non-blocking assignment to the same signal. Verilator raises
`%Error-BLKANDNBLK` regardless of whether the two assignments are in different
always blocks. Additionally `--no-timing` drops the `#(T_HOLD)` delay.
Fixed by wrapping in `` `ifndef VERILATOR ``:

```verilog
`ifndef VERILATOR
  #(T_HOLD) dout0 = 32'bx;
`endif
```

### Elaboration flags required for cache unit test sim_builds

When elaborating `sim_build_icache` or `sim_build_dcache` (top-level = rv32i_icache /
rv32i_dcache respectively), both `-Wno-STMTDLY` and `-Wno-BLKANDNBLK` must be passed
even with the guards in place, because Verilator may still flag residual warnings
from other instances:

```
-Wno-fatal -Wno-WIDTH -Wno-CASEINCOMPLETE -Wno-TIMESCALEMOD -Wno-UNOPTFLAT \
-Wno-STMTDLY -Wno-BLKANDNBLK
```

The main CPU top (`sim_build/Vtop`) elaboration only needs `-Wno-STMTDLY` (the
BLKANDNBLK error does not manifest when rv32i_cpu_top is the top-level, likely due
to different elaboration scope resolution).

## Known Pre-existing Test Failures — RESOLVED 2026-05-15

### test_icache.py: test_basic_miss_then_hit, test_fence_i_invalidation

FIXED. Both tests now pass. See fix details below.

Root cause: Tests asserted `ic_stall_o=0` after exactly 1 rising edge following
`_fetch()` return, but the correct count is 3 edges. The FSM hit path is:
  CS_TAG_CHECK (where _fetch returns) → CS_IDLE → CS_SRAM_LATCH → CS_TAG_CHECK (stall=0)

Critical detail: `_fetch()` returns at the CS_TAG_CHECK rising edge where stall
deasserts. After that, the FSM still needs one more edge to complete the
CS_TAG_CHECK→CS_IDLE transition. Then two more edges for CS_IDLE→CS_SRAM_LATCH→
CS_TAG_CHECK. Total: 3 `await RisingEdge` calls after reasserting `ic_valid_i`.

The original fix suggestion in this file ("add a second await RisingEdge") was
incorrect — the actual required count is 3, not 2.

Note: `make icache` returns exit 0 even with these failures (cocotb Verilator
integration does not propagate test FAIL to make exit code).

## D-Cache Hit Latency (as of CS_HIT_PENDING change, 2026-05-15)

Hit path: CS_IDLE -> CS_SRAM_LATCH -> CS_HIT_PENDING -> CS_TAG_CHECK
Stall cycles on hit: 3 (deasserts in CS_TAG_CHECK)
Stall cycles on miss: 3 + AXI refill cycles

The `_read` / `_write` helpers in test_dcache.py use 128-cycle timeouts (safe).
The polling loops (`for _ in range(6)`) in test_read_miss_then_hit and
test_write_hit_no_axi provide 6-cycle windows — adequate for 4-cycle hit path.

## Flush signal correctness when inserting a pipeline register between redirector and its FF (Run-23 lesson)

When a new pipeline register (e.g. ex1b_ex2_reg_q) is inserted BETWEEN the stage that
generates ex_pc_redirect (EX1b) and the FF that used to be flushed by ex_pc_redirect_r
(u_ex2 / ex_mem_reg), the flush wiring for BOTH the new register AND the downstream FF
must be reconsidered:

**New register (ex1b_ex2_reg_q):** This register now holds the redirecting instruction
itself (branch/JALR) at the cycle when ex_pc_redirect_r fires. It must NOT be flushed
by flush_ex1_ex2 (= ex_pc_redirect_r | mem_trap_redirect_r). Use mem_trap_redirect_r only.

**Downstream FF (u_ex2 / ex_mem_reg):** At the cycle ex_pc_redirect_r fires, u_ex2 is
about to capture ex1b_ex2_reg_q (the branch). Its flush_ex1_ex2_i must also be changed
to mem_trap_redirect_r only — otherwise it blocks the branch from entering ex_mem_reg.

**Rule:** The flash signal for any FF that is downstream of the redirecting instruction
(in the direction of flow) must NOT fire during ex_pc_redirect_r if that FF is still
needed to carry the redirecting instruction to WB. Only mem_trap_redirect_r (a higher-
priority MEM-stage event that overrides everything) should flush those FFs.

**Root cause pattern:** Before inserting the new FF, the branch was captured into
ex_mem_reg at rising edge N (the cycle EX1b computed the redirect). The ex_pc_redirect_r
flush at N+1 only killed the wrong instruction trying to enter ex_mem_reg at N+1.
After inserting ex1b_ex2_reg_q, the branch arrives at ex_mem_reg one cycle later (N+1),
but the flush still fires at N+1 — now it kills the branch itself.

In rv32i_core.sv:
```sv
// ex1b_ex2_reg_q: only flush on MEM trap, not on branch redirect
always_ff @(posedge clk) begin
    if (!rst_n || mem_trap_redirect_r)
        ex1b_ex2_reg_q <= ex1_ex2_nop();
    else if (!stall_ex1_ex2)
        ex1b_ex2_reg_q <= ex1b_comb;
end

// u_ex2: same — only MEM trap flush, not branch redirect
rv32i_pipeline_ex2 u_ex2 (
    ...
    .flush_ex1_ex2_i  (mem_trap_redirect_r),  // NOT flush_ex1_ex2
    ...
);
```

## dbg_halted pipeline drain rule (Run-17 lesson)

When a new FF stage is inserted into the pipeline (e.g. the EX1a→EX1b register in
Run-17), the `dbg_halted` condition in `rv32i_core.sv` MUST be updated to gate on
the new register's `.valid` field. The pattern:

```sv
assign dbg_halted = dbg_halted_wb && !id_ex_reg.valid && !ex1a_ex1b_reg_q.valid && !ex_mem_reg.valid;
```

Without `!ex1a_ex1b_reg_q.valid`, the CPU appears halted while a valid instruction
is still in EX1b. That instruction eventually reaches WB where it de-asserts
`dbg_halted_wb`, causing an intermittent race that makes `halt_cpu()` time out.

Rule: every pipeline register struct with a `.valid` field that lies between ID and
MEM must appear in the `dbg_halted` drain check.

## cocotb make exit code behaviour

`make sim MODULE=...` returns exit 0 even when cocotb tests fail (FAIL > 0).
Only compile/link errors cause non-zero exit. The `make test` / `phase3_all`
aggregate targets inherit this — they cannot detect test-level failures.
Always grep for `TESTS=.*FAIL=[^0]` in output to find failures.

## make phase3_all "FAILED PHASE 3 TARGETS" false alarm (Run-22 lesson)

When `make phase3_all` reports "FAILED PHASE 3 TARGETS: icache dcache" it does NOT
necessarily mean tests failed. The icache and dcache targets require fresh Vtop
binary builds. If sim_build_icache/Vtop and sim_build_dcache/Vtop are absent
(e.g. RTL changed since last build), the targets fail at the compile step with the
nix Python3.11 PYTHONHOME conflict — before any cocotb test runs.

Diagnosis: check for "ModuleNotFoundError: No module named 'encodings'" in the log.
If present, the failure is a build-env issue, not a test failure.
The cache_integration target (which uses sim_build/Vtop, the main CPU top binary)
is unaffected and runs normally.

Recovery: apply the 2-step rebuild procedure (nix-shell elaboration + direct Vtop.mk
make with PYTHON3=/usr/bin/python3) for sim_build_icache and sim_build_dcache,
then re-run `make icache` and `make dcache` inside nix-shell. The pre-built Vtop
binaries will be found and tests will run without recompilation.

## I-cache registered write path (Run-22 RTL change)

As of Run-22, the I-cache data-SRAM write path in `rtl/mem/rv32i_icache.sv` is
registered. The signals data_we_q, data_din_q, data_idx_q, data_bank_q are FFs
that capture the combinational write intent at the CS_REFILL clock edge, mirroring
the tag_we_q pattern from the Run-17 tag registered-commit fix. This adds 1 cycle
of write latency per AXI refill beat. Correctness is maintained because:
- valid_array is gated on tag_we_q (not data_we_q), so the new line is not exposed
  until the tag has been registered — this was already true before Run-22.
- All 7 icache unit tests pass with the registered write path.
- FENCE.I invalidation confirmed working (test_fence_i_invalidation PASS).

## EX1c removal — Vtop must be rebuilt (Run-25 lesson)

When EX1c combinational logic is moved back to EX1a and ex1c_ex1b_reg_q becomes
a pure retiming FF in rv32i_core.sv, the Vtop binary is stale and must be rebuilt
even though rv32i_pipeline_ex1c.sv still exists on disk and still compiles clean.

The module file rv32i_pipeline_ex1c.sv is listed in sim/Makefile VERILOG_SOURCES
(line 78) and in pnr/asap7/config.json VERILOG_FILES. The pnr config.json was
updated by the RTL team to remove ex1c from the PD source list, but sim/Makefile
was intentionally left unchanged (module compiles as an unused definition — 0 lint
errors, 0 functional impact — and removing it from Makefile is a cosmetic cleanup
deferred to the next RTL cleanup pass).

Rebuild procedure: apply the standard 2-step nix-shell elaboration + Vtop.mk make
for sim_build, sim_build_icache, sim_build_dcache (all three need rebuilds after
any EX-stage RTL change since the test_icache / test_dcache toplevel headers embed
the full RTL hierarchy via include-pch).

## sim/Makefile rv32i_pipeline_ex1c.sv entry (as of Run-25)

The Makefile still lists rv32i_pipeline_ex1c.sv. This causes no issues:
- Verilator compiles it as an unused top-level module definition.
- The module is no longer instantiated in rv32i_core.sv.
- Lint produces 0 errors (module is valid SV, just unreferenced).
- Do not remove from Makefile until a dedicated cleanup PR is created.

## Pre-decoded forwarding select FFs — stall behaviour (Run-31 lesson)

The fwd_*_sel_r / fwd_*_ex1c_r / fwd_*_ex1b2_r registers in rv32i_core.sv have
NO clock enable — they update every cycle, including during all stall conditions.
This is correct and intentional:

**During mem_cache_stall (global freeze):**
- if_id_reg frozen → if_id_rs1/rs2_addr stable → _pre outputs stable → _r holds
  the correct selects throughout the stall, still valid when stall releases.

**During load-use stalls (stall_if_id only, id_ex gets a bubble):**
- if_id_reg frozen, but producer registers advance (ex1a_ex1b, ex1c_ex1b,
  ex1b_ex2) shift the load further from the consumer each stall cycle.
- _pre outputs CHANGE each stall cycle (correctly tracking the shifting producer).
- _r captures the new _pre each cycle → after N load-use stall cycles, _r holds
  the select appropriate for the cycle the consumer enters EX1a.
- Adding a stall clock-enable would freeze _r at the first stall cycle value
  and lose the shifting — DO NOT add a clock enable.

**store forwarding alias:**
fwd_store_sel_r / fwd_store_ex1c_r / fwd_store_ex1b2_r are registered from
fwd_b_sel_pre_w / fwd_b_ex1c_pre_w / fwd_b_ex1b2_pre_w respectively. This
is correct because fwd_store_sel = fwd_b_sel in the hazard unit (store uses rs2).
No separate fwd_store_sel_pre output exists in the hazard unit — the alias in
the core is intentional, not an omission.

## sim_build_icache / sim_build_dcache rebuild after hazard_unit or rv32i_core change

As of Run-31: changes to rv32i_hazard_unit.sv or rv32i_core.sv do NOT require
rebuilding sim_build_icache or sim_build_dcache. Those sim_builds use a DUT
of just rv32i_icache / rv32i_dcache respectively — they do not include the full
pipeline hierarchy (no rv32i_core.sv, no rv32i_hazard_unit.sv). Their Vtop
binaries are built from CACHE_SOURCES only and remain valid across all CPU
RTL changes that do not touch rv32i_cache_pkg.sv, rv32i_icache.sv, or
rv32i_dcache.sv.

Confirmed extended scope (Run-35, Run-39): changes to rv32i_pipeline_ex1c.sv
and rv32i_alu.sv also do not require cache sim_build rebuilds — neither file
is in CACHE_SOURCES.

## nix-shell LDFLAGS variable expansion pitfall (Run-18 / Run-23 lesson)

When running `nix-shell --run "verilator -cc ... -LDFLAGS \"...$COCOTB_LIBS...\"`,
shell variables defined outside the nix-shell invocation may not expand inside the
--run string. Symptoms in the generated Vtop.mk:
- LDFLAGS contain empty paths: `-Wl,-rpath, -L -lcocotbvpi_verilator`
- verilator.cpp appears as a relative path: `/lib/verilator/verilator.cpp`

These produce link failures or a Vtop binary that immediately crashes.

**Reliable fix:** Write the elaboration command to a temp bash script where all
variables are defined and used in the same shell process, then pass the script to
nix-shell:

```bash
cat > /tmp/elaborate.sh << 'EOF'
#!/bin/bash
COCOTB_SHARE=/home/neuromorphic/.local/lib/python3.10/site-packages/cocotb/share
COCOTB_LIBS=/home/neuromorphic/.local/lib/python3.10/site-packages/cocotb/libs
/nix/store/xjx9zx3vaz367c7lbnvsd1isvqfkmgg7-verilator-5.048/bin/verilator -cc --exe \
  -Mdir <sim_build_dir> --prefix Vtop -o Vtop \
  --top-module <toplevel> --timescale 1ns/1ps --no-timing \
  -DCOCOTB_SIM=1 --vpi --public-flat-rw \
  -Wno-fatal -Wno-WIDTH -Wno-CASEINCOMPLETE -Wno-TIMESCALEMOD -Wno-UNOPTFLAT \
  -LDFLAGS "-Wl,-rpath,$COCOTB_LIBS -L$COCOTB_LIBS -lcocotbvpi_verilator" \
  [sources...] $COCOTB_SHARE/lib/verilator/verilator.cpp
EOF
chmod +x /tmp/elaborate.sh
cd ~/Downloads/Github/librelane && nix-shell --run "bash /tmp/elaborate.sh"
```

After elaboration, verify Vtop.mk LDFLAGS line contains actual paths (not empty strings)
before proceeding to the `make PYTHON3=...` compile step.

## Large stress UVM run can be silently killed (smoke fallback)

A full stress_uvm run (100 seeds × 500 instructions × 4 profiles) may be silently
killed partway through — not due to OOM, disk full, or kernel errors; root cause
unknown. Symptoms: sim exits without error after completing 2–3 of 4 profiles; VCD
file grows to ~10 GB before exit.

**Reliable fallback:** Use `STRESS_TEST_SMOKE=1` (10 seeds × 100 instructions per
profile). All 4 profiles complete cleanly in smoke mode and resolve any pass/fail
ambiguity from a partial full run. Smoke run times: alu≈6.5 s, jump≈32 s,
shift≈3.8 s, immediate≈3.8 s. The smoke run is adequate for gate-verdict purposes.

## rv32i_clock_gate.sv — `ifdef __pnr__` guard and rebuild scope (Run-36 lesson)

`rv32i_clock_gate.sv` contains an `always_latch` body that is wrapped in an
`` `ifdef __pnr__ `` / `` `else `` behavioral latch `` `endif `` guard. In Verilator
simulation the `__pnr__` macro is never defined, so the behavioral `always_latch`
path is always taken — zero functional change in sim.

The file is referenced inside `` `elsif SRAM_ASAP7 `` conditional guards in
rv32i_icache.sv and rv32i_dcache.sv. In the default freepdk45 simulation build
(no `SRAM_ASAP7` define), the clock gate file is NOT compiled into the main
sim_build/Vtop — only into sim_build_icache and sim_build_dcache when those are
explicitly built with ASAP7 defines.

**Rebuild scope for clock gate changes:** Only sim_build_icache/Vtop and
sim_build_dcache/Vtop need rebuilding. The main sim_build/Vtop is unaffected and
does not require rebuild.

## AXI4SlaveModel r_delay Incompatibility with Burst DUT rd_idx (CRITICAL)

**Discovered: 2026-06-01, Phase 5 M5 DMA engine verification.**

### Symptom

When `AXI4SlaveModel` is constructed with `r_delay > 0` and the DUT captures
`m_rdata` into a line buffer indexed by a registered counter (`rd_idx_q`) that
increments on `m_rvalid`, the destination memory shows a "doubling" pattern:
each source word is written to two consecutive destination addresses.

Example with 8 source words and `r_delay=1`:
```text
DST[0] = linebuf[0]  ✓
DST[1] = linebuf[0]  ✗  (expected linebuf[1])
DST[2] = linebuf[1]  ✗  (expected linebuf[2])
...
```

### Root cause

In Verilator+cocotb, the per-time-step execution order is:

1. **RisingEdge** — RTL registers update (including `rd_idx_q++` when rvalid=1)
2. **Active phase** — Python VPI writes fire (`rdata`, `rvalid` set by slave)
3. **ReadOnly phase** — Python VPI reads fire (slave polls rready)

The slave asserts `rdata=mem[addr+i*4]` and `rvalid=1` in the **active phase**
of cycle T. The slave immediately polls ReadOnly of cycle T and sees `rready=1`
(DMA drives it combinationally in S_R). The slave then does `await RisingEdge`
(cycle T+1). At cycle T+1's RisingEdge, the RTL posedge fires **first**: the
DMA sees `m_rvalid=1` (set in T's active phase), captures `m_rdata`, and
increments `rd_idx_q` (0→1). **Then** the active phase fires (slave deasserts
rvalid, sets up beat i+1). **Then** ReadOnly fires for the next beat.

When `r_delay > 0`, there are extra `await RisingEdge` calls between beats.
This shifts the timing so the slave's ReadOnly sample for beat i captures
`m_rdata = linebuf[rd_idx_q]` **after** `rd_idx_q` has already incremented
(the posedge fired before ReadOnly). Result: beat 0 reads `linebuf[1]`,
beat 1 reads `linebuf[2]`, etc. — except the slave's address counter advances
by 1 per beat so consecutive slave beats collide.

The net observable pattern is each unique value appearing at two destination
addresses before the next value appears — a stutter-then-advance artifact.

### Safe patterns

- `r_delay=0` (default): no extra RisingEdge between beats; timing is correct.
- `aw_delay > 0`: safe — the write path's `wr_idx_q` is gated by `m_wready`,
  and the slave's `wready=0→1` toggle in the active phase is visible at
  ReadOnly of the same cycle (before the next posedge). No off-by-one.
- `ar_delay > 0`: safe — only delays before asserting arready; does not
  affect R-channel beat-to-beat timing once arready is asserted.

### Workaround for slow-read scenarios

To exercise read-side backpressure in a Verilator+cocotb testbench, either:
1. Keep `r_delay=0` and use `aw_delay` to control overall transfer throughput.
2. Write a custom slave that drives `rvalid` and `rdata` on the **RisingEdge**
   callback (not via active-phase VPI writes) so the RTL sees the data at the
   same posedge it samples `rvalid`.

### Applies to

Any DUT that captures `rdata` into a registered buffer indexed by a counter
incremented on `rvalid`. This includes `dma_engine.sv` (linebuf via rd_idx_q)
and any future burst-read DUT using the same pattern.

## cocotb Inter-Test Coroutine Leakage (CRITICAL for soc/ tests)

**Discovered: 2026-06-01, Phase 5 M5 DMA engine verification.**

### Symptom

When multiple cocotb tests share a single DUT instance (Verilator simulation),
`cocotb.start_soon` coroutines from test N are **not automatically cancelled**
when test N+1 starts. The stale slave model loops (e.g., `AXI4SlaveModel`
`_write_loop` / `_read_loop`) continue running and compete with the new slave
for `m_awready`, `m_arready`, and write-data signals. This causes:

- Corrupted slave memory (writes go to the stale slave's `mem` dict instead
  of the new test's `slave.mem`)
- Spurious handshake completions (stale slave grabs an AW/AR transaction
  intended for the new slave, then idles waiting for W-data that never comes)
- Intermittent test failures that depend on coroutine scheduling order

### Fix

Track all slave task handles in a module-level list. At the start of each
`_setup` call, call `.kill()` on every stored handle before starting new ones:

```python
_active_slave_tasks = []   # module-level

async def _setup(dut, ...):
    global _active_slave_tasks
    for task in _active_slave_tasks:
        task.kill()
    _active_slave_tasks = []
    ...
    t1 = cocotb.start_soon(slave._write_loop())
    t2 = cocotb.start_soon(slave._read_loop())
    _active_slave_tasks.extend([t1, t2])
```

### Scope

Applies to all soc/ testbenches that use `AXI4SlaveModel` or any long-running
background coroutine. The existing crossbar, register_bank, and
axil_interconnect tests are unaffected only because they do not use a
persistent background slave model — they drive signals directly.

## GH #104 sram_controller SRAM_SKY130: RVALID one cycle ahead of negedge-launched macro data (P0 bug, escalated 2026-07-24)

**Symptom:** Under `+define+SRAM_SKY130`, `sram_controller`'s AXI read channel
returns stale or one-beat-shifted data. Single-beat reads return whatever the
macro's `dout1` register last held (0x0 on a pristine sim, or leftover data
from an unrelated prior transaction) instead of the addressed word. Bursts
shift by one beat (a bogus stale beat prepended) and silently drop the true
final beat. 6/10 `tb/cocotb/soc/test_sram_controller.py` tests FAIL with
`SRAM_TARGET=sky130`; the same 10/10 tests PASS on the default flat-array
build. See `design_state.json` fix_request `fr_null_20260724_051800_00`.

**Root cause:** `sram_controller.sv`'s SRAM_SKY130 read FSM (`rd_dv_q` /
`r_issue_now` in the R_BUSY state, ~lines 307-391) asserts `s_rvalid` at the
SAME edge the macro's `csb1_r`/`addr1_r` input registers capture the new
address. But `sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv` (and the real
OpenRAM macro it models) is **negedge-launched**: `dout1` only updates at the
`negedge clk1` roughly half a cycle *after* that same posedge, i.e. from a
rising-edge-sampling AXI consumer's point of view, `dout1` is only
*guaranteed* settled starting the edge *after* the one where `rd_dv_q` was
set. The RTL is missing one full cycle of pipeline delay between "address
registered into the macro" and "RVALID asserted" — it assumes a plain
posedge-only-registered-output SRAM (1-cycle: address cycle N → data cycle
N+1), but the actual model needs the FULL period to settle before it's safe
to declare RVALID (effectively: address cycle N → data ready cycle N+1, but
only *provably* settled by the START of cycle N+2 given the negedge-launch).

**How this was diagnosed (reusable technique):** A raw same-timestep signal
read taken directly after `await RisingEdge(dut.clk)` (no `ReadOnly()`)
misleadingly showed the *correct* data one delta earlier than a disciplined
`await RisingEdge(); await ReadOnly()` read of the same signal in the same
test — i.e. two coroutines racing to sample `s_rdata` in the same timestep
disagreed. Trust the `ReadOnly()`-disciplined read (the same idiom the
project's own `AXI4Master` BFM and all working regression tests already use)
as ground truth for what a real AXI consumer would see; a bare post-edge read
without `ReadOnly()` is not a reliable oracle for this kind of race and
produced a false-negative ("looks fine") during initial investigation.

**Test-harness gap found + fixed while investigating (NOT an RTL fix):**
`tb/cocotb/soc/Makefile`'s `sram_controller` target didn't override
`MEM_WORDS` to 1024 when `SRAM_TARGET=sky130` — the module's default
`MEM_WORDS=4096` (12-bit word index) silently truncates onto the
sky130_sram_4kbyte macro's fixed 10-bit `addr0`/`addr1` ports (Verilator
`WIDTHTRUNC`, caught at `--lint-only` before any sim ran). Fixed by adding
`-GMEM_WORDS=1024` to both the `verilator_lint` and `sram_controller`
Makefile targets under `SRAM_TARGET=sky130`. The RTL's own
`MEM_WORDS != 1024` guard (`sram_controller.sv` ~line 108) is an `initial
$error` — this is a **runtime-only** check; it does not fire under
`--lint-only` and does not stop a live cocotb simulation either (`$error` is
non-fatal per IEEE spec). Any future `SRAM_SKY130` build must pass the
parameter override explicitly; don't rely on that guard to catch a missing
override.

**Full soc_top-level SRAM_SKY130 cocotb coverage does not exist yet:** as of
this session, `tb/cocotb/soc/Makefile`'s `SRAM_TARGET=sky130` switch only
wires the real macro into the standalone `sram_controller` unit-test target.
`soc_boot`/`soc_periph`/`soc_coherency`/`soc_cpu_gpu` still always build with
the flat behavioral array regardless of `SRAM_TARGET`. Full-SoC SRAM_SKY130
elaboration is currently lint-only, via `make -C sim lint_soc_sky130`. A
future verification pass (once the read-latency bug above is fixed) should
either wire `SRAM_SKY130` through to the soc_top cocotb targets, or
explicitly accept unit-level-only coverage as the sign-off boundary for this
macro.

## Multi-Clock CDC Verification Lessons (GH #93, 2026-08-01; bead nan, 2026-09-09)

- **Only a coprime clock ratio with independently released resets finds CDC reset-ordering
  bugs.** GH #93 found two RTL bugs that every 1:1 suite missed, including `async_axi_fifo`'s
  own 22 unit tests: (1) `4398c2e`: the CPU clock-gate enable synchroniser reset to "disabled",
  so `cpu_gated_clk` never toggled during reset and the CPU's synchronous reset never loaded
  `RESET_PC` (`soc_boot` 0/8 commits); (2) `7a9f9d4`: `cdc_gray_fifo` `wr_ready_o = !full_q`
  was not gated by `wr_rst_n_i`, so the CPU's first AXI AR was accepted and dropped whenever the
  CPU domain left reset before the fabric did. `test_soc_multiclock` / `test_soc_multiclock_pll2`
  run at **7 ns / 3 ns**. Both bugs share one signature: **a reset value that advertises
  availability**. Final tallies: `soc_all` 159/159, `async_axi_fifo` 22/22, `apb_cdc_bridge`
  15/15, `soc_multiclock` 4/4, `soc_pll_multiclock` 1/1. Fix requests: `fr_57f49b7f9b29`,
  `fr_280f3ac18c66`.
- **A correct RTL fix can expose a testbench that relied on the bug.** After `7a9f9d4`,
  `test_reset_while_busy_s_side` failed. The interrupted AXI4Master write had only passed because
  the buggy `wready` let it finish instantly during reset. With correct backpressure it blocked,
  then pushed orphaned W beats into the fresh FIFO. Fix: call `t.kill()`/`_idle_s_side()` when
  reset is asserted, not after recovery. Re-run the full ratio matrix after any CDC fix.
- **Count a timeout budget in the clock domain being polled.** `test_pll_lock._wait_for_cpu_lock`
  counted `clk_i` edges while it polled a lock counter in the `cpu_clk_i` domain. That was harmless
  only at 1:1.
- **A software handshake counter can undercount by one when the reader clock is slow (bead
  `nan`). This is a harness stall, not a DUT deadlock.** Releasing backpressure
  (`dut.s_bready.value=1`) right after the *other* domain's `RisingEdge` (as
  `_poll_until(dut.m_clk, …)` does) can land within nanoseconds of the slow `s_clk` edge. A
  `RisingEdge`+`ReadOnly` counter (`_count_handshakes_bg`) then misses one real completion, and an
  exact-count saturation gate never completes. Disproved as a DUT bug three ways: the internal
  `wr_bin_q`/`rd_bin_q` trace showed 9 writes and 9 reads; syncing the release to
  `await RisingEdge(dut.s_clk)` passed immediately; and the realistic fast-`s_clk` direction
  self-corrects. Rule: sync any release write to the counting domain's own edge. Rule out the
  harness before suspecting `async_axi_fifo`/`cdc_gray_fifo` for a symptom that depends on
  direction. Bead `nan` was left open by design.
- **Root-cause technique for ns-level reset sequencing:** a throwaway free-running 1 ns `Timer()`
  coroutine (never committed) pinpointed the sequence: `cpu_domain_rst_n` released at 33 ns, AR
  falsely completed at 45 ns, `core_rst_n` released at 98 ns.

## Build / Harness Infrastructure Lessons (2026-08 → 2026-10)

- **Stale Verilator/cocotb build cache after a shared TB wrapper's port list changes looks like
  an RTL bug.** (Folded in from the old XDG-root knowledge file and confirmed by the 2026-09-27
  GPIO SoC session.) Adding ports to a wrapper used by MULTIPLE Makefile targets, each with its
  own `sim_build_<target>`, leaves every other target's cache stale. Separate build dirs do not
  protect a target from its OWN stale build. Symptom: VPI reports "Toplevel instances: <name> !=
  <garbage bytes>", then a UnicodeDecodeError while logging it, then a double-free / core dump.
  Cause: Verilator regenerates all `.cpp` files, but make only recompiles files whose mtime
  changed, so `.o` files from the old and new port layouts get linked together. Fix: `rm -rf` the
  stale `sim_build_<target>` dirs. Confirm with a clean rebuild of ONE target before concluding
  "no RTL bug". For `tb_soc_top.sv`, the targets affected were `soc_boot`, `soc_periph`,
  `soc_coherency`, `soc_cpu_gpu`, `soc_multiclock`, `soc_multiclock_reset` and
  `soc_pmu_multiclock`. `lint_soc` is unaffected because it lints `soc_top` directly.
- **Hand-maintained source lists rot silently (bead `50t`).** `tb/cocotb/cpu/Makefile`
  `VERILOG_SOURCES` fell behind the M2 burst upgrade and the EX retiming split. It was missing
  `axi_pkg.sv`, `soc_addr_map_pkg.sv`, `rv32i_clock_gate.sv` and `rv32i_pipeline_ex1b/ex1c/ex2.sv`,
  so every target failed with "Import package not found: axi_pkg". Three lists existed for one
  macro and only the one CI exercised stayed current. Fix: the new stdlib-only
  `tools/verif/check_source_closure.py` (includes a small GNU-Make variable resolver) and a
  `cpu_phase2_all` job in `.github/workflows/cocotb.yml`. Same defect class as bead `v2q`/`135`
  on PD configs.
- **`tb/cocotb/cpu` needs `USE_VERILATOR_EXTRALIBS=1`.** Without it, `Vtop` fails to dlopen
  `libpython3.10.so.1.0` (missing `libexpat.so.1`). This looks like a build failure, not a missing
  runtime library. Confirmed across 2 runs (2026-08-11, 2026-09-17).
- **cocotb JUnit `results.xml` has no `tests`/`failures`/`errors` attributes on `<testsuite>`.** A
  gate script must count `<testcase>` children and look for `<failure>`/`<error>` child elements.
  A parser that reads attributes reports 0 tests / PASS for every suite. The established
  convention (rvb/ydw/8yd sessions) is to run every `soc_all` sub-target individually and gate on
  each `results.xml`.
- **Read the rtk tee log, not a piped redirect.** When stdout is piped to a file instead of a tty,
  rtk's output-volume elision can truncate the redirected copy mid-stream. The full log is in
  `~/.local/share/rtk/tee/`.
- **Watch-pattern pitfalls.** `^\*\*`-anchored greps miss cocotb's indented continuation lines,
  so the monitor only matched benign `libssl.so.3` noise. `pgrep -f` inside an `until` loop
  matches its own shell and never exits. Re-derive tallies from the raw log.
- **Unquoted heredocs execute backticks and `$(…)`.** `python3 - <<EOF` containing
  `` `make -C sim lint` `` actually ran the command. Use `<<'EOF'` or a script file.
- **Host settings for big regressions:** route `SIM_BUILD_ROOT` to `/nobackup/...` and use
  `MAKEFLAGS=-j2` (15.9 GB host + systemd-oomd).
- **Attribute build-time regressions on the module alone first (bead `8yd`).** A SoC-wide cocotb
  rebuild at `SRAM_MEM_WORDS=65536` under the required `-j2` extrapolated to ~8 h per arm. A
  standalone `sram_controller` Verilator scaling curve at `-j16` (MEM_WORDS 1024→65536) settled
  it in minutes:
  - The pre-Path-A baseline (`7024319^`) is flat, about 6.5 s at every size.
  - Path A (`7024319`) and `23bacae` both grow ~4.6–4.7× per 4× size.
  - At 65536 the totals are `23bacae` 457 s, pre-rvb2 348 s, pre-Path-A 6.6 s.

  Verdict: the `l2_bench` slowdown comes from the per-word `always_ff` write decode added in rvb
  Path A. `23bacae` only adds a ~1.1–1.3× tax on top. The flat genvar loop at 65536 also needs
  Verilator `--unroll-count`/`--unroll-limit 70000`.

## Coverage / Test-Quality Lessons (2026-09 → 2026-10)

- **The shared `AXI4Master` BFM hardcodes INCR bursts.** `AXI_BURST_FIXED` coverage needs a
  hand-driven AR/AW helper. 4 tests were added to `test_sram_controller.py` (bead `ydw`): FIXED
  read/write, MEM_WORDS wrap, and randomised R backpressure over 8 seeds.
- **A black-box ordering test can be structurally blind when the latency arithmetic leaves no
  slack (rvb `23bacae`).** The read FSM's 2-cycle AR→fetch latency plus cocotb's minimum 1-cycle
  reactive lag equals the 3-cycle write-landing latency. So an AR issued reactively after BVALID
  can never race the data, and an early-BVALID mutant passes. Fix: a whitebox `dut.mem[]` peek
  (guarded by `hasattr`, flat-array build only) as the decisive check. Check the latency
  arithmetic before trusting a black-box race test.
- **Mutation-check every new directed test** (confirmed across 3 sessions: ydw, rvb, I2C). Use
  drop-a-beat, skip-W_DRAIN and off-by-one group mutants, then revert and confirm an empty
  `git diff`.
- **Suites written AFTER the RTL leave mutation survivors (I2C `f7vs.9`).** Two survivors (M3c,
  repeated-START arbitration abort; M30, COUNT=0 read NACK) passed because the flag-level assertion
  was satisfied by a later, different detection path. A mutant killed only by "default must lint
  clean" (M32) is a spurious kill: judge kills by behavioural tests. Verilator line coverage (91 %)
  found holes mutation had missed: continuation commands without START, and the loopback slave
  next-byte path.
- **STATUS/IRQ_STAT that mirror the NEXT state** (I2C) drop `busy` one clock before the registered
  oe/state flops move. A test that reacts to `busy=0` must wait 2 clocks.
- **I2C BFM: contention needs its own override flag.** A contention release overwrote the slave's
  own `_sda_drv`. The shared BFM is `tb/cocotb/bfm/i2c_slave.py`.
- **I2C SCL-rate DUT bug (`fr_609b42790e0f`): RESOLVED.** Verification found a 3-tick bit period
  (132.8 kHz at the documented 100 kHz setting, tHIGH 2.53 µs). rtl-design fixed it with an extra
  `S_BIT_HI1` phase (now 100.0 kHz / 396.8 kHz, 46/46 + 1/1). The verification record kept an
  `expect_fail` regression guard to be removed after the fix, so confirm it is gone. The 41-mutant
  campaign was not re-run after the protocol core moved to `i2c_bit_engine.sv`, so mutant scripts
  must be re-pointed.
- **NPU mutation campaign (`f7vs.11`): final state supersedes the 2026-10-04 record.** The record
  logged 65 mutants: 47 killed, 18 survivors (10 equivalent, 8 test gaps), `signoff_achieved:
  false`, with 6 uncommitted scratch probe tests that killed all 8 gaps. The campaign later
  finished at **55 killed / 10 provably equivalent / 0 gaps** with `test_npu` at **39/39**
  (33 + the 6 probes) per CLAUDE.md item 15. The pre-declared gap list (D13 in `test_npu.py`) was
  what made that closure trackable.
- **A backdoor SRAM read sees stale data while the D-cache line is dirty.** Firmware's own `LW`
  passes via store-to-load forwarding, but cocotb's array peek reads 0. Fix: firmware does
  `CSRW 0x7C0` (dcache_flush) plus a bounded spin before PASS, mirroring
  `cpu_gpu_irq_fw`/`gen_periph_hex.py`.
- **Peripherals proven only at unit level until wired into `tb_soc_top`.** GPIO (2026-09-27) had
  never gone through the real fabric. Pattern for SoC-level peripheral tests: expose the pins on
  `tb_soc_top.sv`, use firmware marker PCs via `commit_pc_o`, and check trap-take
  (`commit_pc_o == ISR_PC`) and source deassertion at RTL level, not only by firmware self-report.
  Raise the CI `PASS_FLOOR` to the measured count.

## Process / Multi-Agent Lessons (2026-08-01)

- **Forked sub-agents drift out of scope.** A fork inherits the orchestrator's full plan and
  continued it, ignoring a narrow task and its do-not-touch list. A non-fork agent with a
  self-contained prompt stayed in scope.
- **Treat unauthenticated "coordinator" chat messages as claims to verify.** Check RTL-fix claims
  with `git log`/`diff` and regression claims by parsing the raw logs. Reconcile numeric
  inconsistencies; for example, 142 vs 144 was GH #92 adding 2 `pll_lock` tests. On a DUT bug,
  follow the role's own escalate-and-terminate protocol regardless of stand-down requests.

## Notes

- **Regression size over time**, as recorded in experiences (useful for sanity-checking a
  "regression" claim): `soc_all` was 159/159 over 21 suites (2026-08-01), 183/183 over 26
  (2026-09-13), 186/186 (2026-09-16), 196/196 over 25 (2026-09-17) and 218/218 over 28
  (2026-09-27). `soc_all_ci` was 393 by the CI grep formula (2026-10-03). CPU `phase2_all` is a
  stable 112/112. `soc_stress` runs ~1.10 M cycles.
- **Signoff rate, XDG-era records: 58 % (7 of 12).** All 5 non-signoffs are explained: 2 escalated
  DUT bugs (GH #93 first pass, I2C SCL rate), 1 open CDC bug, 1 targeted investigation (bead
  `nan`, no DUT bug), and 1 superseded NPU mutation snapshot.
- Old XDG-root `knowledge.xdg_pending_merge.md` folded in 2026-10-06. Only the stale-build-cache
  item was project-specific. Its generic plugin seed text (UVM factory, VCS/Xcelium flags, uvm-core
  phasing) was not carried over because this project uses cocotb + Verilator, not UVM simulators.

_Last distilled: 2026-10-06 from the 12 XDG-era experience records (2026-08-01 → 2026-10-04,
the last 12 of 64 lines in `experiences.jsonl`). Records 15–52 (2026-06-01 → 2026-07-27) were
not re-audited in this pass; some of their lessons (e.g. GH #104 SRAM_SKY130) were already
added by hand. Previous distillation: 2026-06-01 from 14 records._
