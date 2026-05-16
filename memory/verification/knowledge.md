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
