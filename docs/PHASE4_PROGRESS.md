# Phase 4 (GPU-Lite SIMT) — Sign-Off Progress

Tracks progress against the golden-plan sign-off checklist
(`docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md` §9). Updated 2026-05-23.

## Completed & verified

| ID | Workstream | Status |
| :- | :--------- | :----- |
| A | Shared-memory hardware path | ✅ VLDS/VSTS opcodes + `IC_SHMEM`; compute-unit EXECUTE/WB drive the shared path; `sh_rvalid_o` added to `shared_memory.sv`; `gpu_asm` `vlds`/`vsts`; `kernel_shared_mem_pingpong` rewritten to use real shared memory |
| — | RTL bug fix: divergence | ✅ Retirement outputs (`warp_retire_o`/`warp_done_o`/`div_push_o`/`div_pop_o`) were level signals held through WB memory stalls, causing duplicate VRET issue and premature `warp_done` (dropped lane-4..7 false-path store). Now gated by `!pipe_stall` → single-cycle pulses |
| — | RTL bug fix: shared-load capture | ✅ VLDS read data was lost when the instruction advanced out of WB the same cycle data became valid. `shmem_rvalid_i` added to `pipe_stall` to hold the load one extra cycle (mirrors the VLD capture-then-advance contract) |
| B | Missing tests | ✅ `tb/cocotb/gpu/test_memory_unit.py` (gpu_memory_unit, 5/5); `test_cpu_gpu_handoff.py` (1/1); fixed stale `test_warp_scheduler.test_div_push_pop_state` (must drive `exec_warp_id_i`) |
| C | Makefile | ✅ Added `gpu_memunit` target; folded `gpu_memunit`+`gpu_top_smoke` into `gpu_unit`; fixed false-"ALL PASSED" via `results.xml` `<failure>`/`<error>` check in all aggregate loops |
| D | Functional regression | ✅ `make gpu_all` green: 9 unit targets (regfile 5, alu 14, diverge 6, sched 5, cmdq 3, coalescer 5, memunit 5, shmem 4, top_smoke 4), 6/6 kernels, handoff 1/1 |

## Remaining milestones

| ID | Workstream | Notes |
| :- | :--------- | :---- |
| ✅ F | Phase 2+3 CPU-only re-gate (hard gate) | **PASSED** 2026-05-23. Directed regression `make test` = 140/140, 0 failures (smoke 12, c_programs 1, axi_protocol 12, debug_if 6, isa_uvm 54, fault_injection 7, hazards 16, interrupts 12, icache 7, dcache 8, cache_integration 5). Random UVM `make random_uvm` = 1000 seeds × 100 instr (100k total), all passed, 0 scoreboard mismatches. Confirms GPU-only edits did not break the CPU (CPU build does not compile `rtl/gpu/`) |
| ✅ E | 1000-kernel random regression | **PASSED** 2026-05-23: 1000 random straight-line kernels vs new `tb/cocotb/gpu/gpu_ref_model.py` (`GpuRefModel`, matches RTL/`gpu_asm` encoding), 0 deadlocks, 0 mismatches. Harness: `tb/cocotb/gpu/test_random_kernels.py`, `make gpu_random` (sets `EXTRA_ARGS=""` to skip tracing). Report: `docs/regression/PHASE4_RANDOM_KERNELS.md`. Branches/loads/shared-mem out of random scope (covered by directed kernels) |
| G | ASAP7 GPU-block P&R | New `pnr/asap7/gpu/` (`config.json` DESIGN_NAME `gpu_top`, `constraints/asap7_gpu.sdc`, `macro_placement.cfg`, `pdn.tcl`); multi-hour LibreLane run; sign-off WNS≥0 setup+hold, 0 DRC, 0 antenna; record power/area. GPU UPF deferred to Phase 5 |
| H | Docs + tag | Update the stale Phase 4 block in `docs/PHASE_STATUS.md` (currently "NOT STARTED"); add PD run-history entry; tag Phase 4 complete in `CLAUDE.md` |
