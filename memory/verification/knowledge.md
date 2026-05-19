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
`/nix/store/mky7gdsf8m3da333lxz2mjf2n3n1v1xy-verilator/bin/verilator`

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
