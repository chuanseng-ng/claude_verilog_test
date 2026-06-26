# sw/bench — RV32I cache benchmarks (Phase 5 M10 L2 decision)

Bare-metal C benchmarks compiled for the SoC CPU to measure **L1 I$/D$ miss rates**
and decide the M10 L2-cache gate (`docs/PHASE5_SOC_INTEGRATION_PLAN.md` M10:
"add `rtl/mem/l2_cache.sv` only if justified"). M9 recorded cycle counts but not
miss rates; these workloads dump `mhpmcounter3` (I$ miss) / `mhpmcounter4` (D$ miss).

## Toolchain

`riscv32-none-elf-gcc` (newlib, GCC 15.2) ships in the `bench` nix devshell:

```bash
nix develop ~/Downloads/Github/claude_verilog_test#bench --command make -C sw/bench
```

Target ISA is **`-march=rv32i_zicsr -mabi=ilp32`** (the CPU is RV32I + Zicsr; `csrr`
needs Zicsr).

## Build outputs (per program `<p>`)

| File | Use |
| ---- | --- |
| `build/<p>.hex` | SRAM image, word-per-line LE hex; backdoor-load into `u_sram.mem` at index `(addr-0x2000)/4` |
| `build/trampoline.hex` | shared ROM image; backdoor-load into `u_boot_rom.mem` (jumps 0x1000→0x2000) |
| `build/<p>.elf` | symbol resolution (`__result`, `BENCH_SCRATCH_ADDR`) |
| `build/<p>.sym` / `.dis` | nm / disassembly for debug |

## Memory map (must stay in sync across `rv32i.ld`, `bench.h`, the testbench)

- ROM trampoline @ `0x0000_1000` (RESET_PC) → `jr` to `0x0000_2000`.
- Benchmark image linked into **SRAM @ `0x0000_2000`** — the cacheable main-memory
  region, so all I-fetch + data traffic flows through L1 (uncached MMIO is
  `0x2000_0000+`). `crt0.S` (`_start`) is first at `0x2000`.
- Stack top `0x0004_1C00` (grows down).
- **Bench scratch region `0x0004_1C00..0x0004_1FFF` (1 KB, 256 words)** — reserved
  for the multi-slot append protocol (see below). SRAM word index of base =
  `(0x41C00 - 0x2000) / 4 = 0x7F00`.
- **Requires the bench testbench to instantiate SRAM with `MEM_WORDS = 65536`**
  (256 KB window `0x2000..0x42000`). The default model is only 4096 words (16 KB)
  and *aliases* higher addresses — the harness MUST override `MEM_WORDS` (and
  size working-set sweeps ≤ ~64 KB to fit below the stack).

## Multi-slot scratch protocol

`bench.h` implements an **append-on-write** scratch protocol so that all records
from a single run survive in SRAM until EBREAK, regardless of how many times
`bench_report()` is called (e.g. `sweep.c` calls it 16 times).

| Word offset from `BENCH_SCRATCH_ADDR` | Content |
|---------------------------------------|---------|
| 0 | record count N (written last by each `bench_report`) |
| 1 + k×8 .. 1 + k×8 + 7 | slot k (0-indexed), 8 words |

Slot layout (8 words):

| Slot word | Content |
|-----------|---------|
| 0 | `BENCH_MAGIC \| (id & 0xFF)` |
| 1 | checksum (dead-code guard) |
| 2 | Δcycles |
| 3 | Δinstret |
| 4 | ΔI$-miss |
| 5 | ΔD$-miss |
| 6 | Δbranch-miss |
| 7 | 0 (pad) |

Maximum 31 slots (1 header + 31×8 = 249 words ≤ 256-word region).

**Every `main()` must call `bench_init()` first** to zero the count word before
any `bench_report()` call. All three programs (`hello.c`, `matmul.c`, `sweep.c`)
already do this.

## Adding benchmarks (A3)

Drop `dhrystone.c` / `coremark.c` here — the Makefile builds every `*.c`
automatically. Each `main()` must:
1. Call `bench_init()` at the very top (before any `bench_report()`).
2. Bracket hot regions with `bench_snapshot()` and `bench_report(id, checksum,
   &before, &after)` (see `bench.h`) to append cycle/instret/I$-miss/D$-miss/
   branch-miss delta records.

`hello.c` is the toolchain-validation example (not a real benchmark).

## Harness handoff (A2)

The cocotb side (`tb/cocotb/...`, owned by the verification flow) must:
1. Load `trampoline.hex` into ROM + `<p>.hex` into SRAM; override `MEM_WORDS=65536`.
2. Run to EBREAK.
3. Backdoor-read `BENCH_SCRATCH_ADDR` (SRAM word index `0x7F00`): read Word[0]
   to get count N, then read N slots (8 words each starting at word index
   `0x7F00 + 1 + k*8` for slot k).
4. Also read `__result` (parked in `a0` at EBREAK by `crt0.S`) for checksum
   cross-check.
5. Compute miss rates (misses / 1k-instr and miss / mem-access) per slot.
