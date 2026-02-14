# micro_p — Phase 1 Legacy Archive

This directory is a **read-only, frozen snapshot** of the Phase 1 single-cycle RV32I CPU.

Phase 1 was declared complete on 2026-02-13 with all 9/9 verification exit criteria met.

**Do not modify files in this directory.** Phase 2 and later work lives in `rtl/`, `tb/`, and `sim/`
at the repo root. Phase 2 RTL may reference Phase 1 modules from `micro_p/rtl/` (e.g., to reuse
leaf modules like `rv32i_alu.sv`) but must not modify them in place.

---

## Directory Layout

```
micro_p/
├── rtl/
│   └── cpu/
│       ├── rv32i_cpu_top.sv          # Top-level (AXI4-Lite + APB3)
│       ├── CRITICAL_FIXES.md
│       ├── DATAFLOW_DIAGRAM.md
│       ├── INTEGRATION_SUMMARY.md
│       ├── VERIFICATION_READY.md
│       └── core/
│           ├── rv32i_alu.sv          # ALU (all 37 RV32I ops)
│           ├── rv32i_branch_comp.sv  # Branch comparator
│           ├── rv32i_control.sv      # Control FSM (8 states)
│           ├── rv32i_core.sv         # Core wrapper
│           ├── rv32i_decode.sv       # Instruction decoder
│           ├── rv32i_imm_gen.sv      # Immediate generator
│           └── rv32i_regfile.sv      # 32x32-bit register file
├── tb/                               # Complete Phase 1 testbench
│   ├── models/                       # Python reference models
│   ├── tests/                        # pytest unit tests (66 tests)
│   ├── cocotb/                       # cocotb BFMs and test files
│   ├── generators/                   # Instruction generator
│   ├── common/                       # Shared utilities
│   └── cpu_uvm/                      # pyuvm verification framework
├── sim/
│   ├── Makefile                      # Simulation Makefile (self-relative paths)
│   └── riscv_encoder.py              # RISC-V instruction encoder utility
└── README.md                         # This file
```

---

## Running Phase 1 Verification Tests

All Makefiles use self-relative paths, so they work identically from `micro_p/` as they do
from the repo root. No path changes were needed.

### From WSL (recommended for cocotb simulation tests)

```bash
# pyuvm smoke tests (4 tests, ~30s)
cd micro_p/tb/cocotb/cpu
make smoke_uvm

# pyuvm ISA compliance (54 tests, 37 instructions)
make isa_uvm

# pyuvm random instruction tests (100 seeds x 100 instructions)
make random_uvm

# Quick random smoke (10 seeds x 50 instructions, ~10s)
make random_uvm_smoke

# All pyuvm suites
make all_uvm

# AXI protocol tests
make MODULE=test_axi_protocol

# Debug interface tests (halt/resume/step/breakpoints)
make debug
```

Or via the sim/ Makefile:

```bash
cd micro_p/sim

# Run all tests
make test

# Run with coverage
make coverage

# Lint only (works from Windows too)
make lint
```

### pytest unit tests (reference model, Python-only)

```bash
# From repo root — tests still reference the original tb/tests/
pytest tb/tests/ -v

# Or directly from micro_p/ (requires micro_p/ in PYTHONPATH)
cd micro_p
PYTHONPATH=. pytest tb/tests/ -v
```

---

## Phase 1 Verification Exit Criteria (all met 2026-02-13)

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Smoke tests | 6/6 |
| 2 | Scoreboard mismatches | 0 |
| 3 | Instruction coverage | 37/37 (100%) |
| 4 | Random instruction tests | 10,000 instructions, 0 failures |
| 5 | AXI protocol tests | 11/11 |
| 6 | Debug interface tests | 6/6 |
| 7 | Code coverage | >95% (Verilator annotated) |
| 8 | FSM state coverage | 8/8 (100%) |
| 9 | Failing random seeds | 0/100 |

---

## Constraints for Phase 2

- Phase 2 RTL **may import** Phase 1 leaf modules (ALU, register file, imm_gen, branch_comp)
  by referencing `micro_p/rtl/cpu/core/*.sv` in its Makefile `VERILOG_SOURCES`.
- Phase 2 RTL **must not** modify any file under `micro_p/`.
- Phase 2 Python tests **may import** Phase 1 reference models from `micro_p/tb/models/`
  if they add CSR/interrupt behaviour on top, without modifying the originals.
- The top-level `rv32i_cpu_top.sv` interface is the Phase 1 contract. Phase 2 produces
  a new top-level (e.g., `rv32i_cpu_top_v2.sv`) that preserves the same external port names.
