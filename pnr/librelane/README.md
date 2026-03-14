# LibreLane Flow — Phase 3 RV32I CPU + L1 Caches

## Overview

This directory contains the LibreLane (OpenLane 2) flow configuration for the Phase 3 SoC design:
**rv32i_cpu_top** — 5-stage RV32I pipeline + 4 KB I-cache + 4 KB D-cache.

| Parameter | Value |
|-----------|-------|
| Top module | `rv32i_cpu_top` |
| PDK | sky130A / sky130_fd_sc_hd |
| Target frequency | 75 MHz (13.333 ns period) |
| Die area | 370 × 370 µm |
| Core utilisation | 45% |

---

## Prerequisites

### 1. LibreLane (nix-shell)

LibreLane is available via the local nix-shell at `~/Downloads/Github/librelane`.
Enter it with:

```bash
cd ~/Downloads/Github/librelane
nix-shell
# librelane is now on PATH inside the shell
librelane --version
```

The Makefile in this directory handles the nix-shell invocation automatically —
you do **not** need to enter the shell manually before running `make`.

### 2. Sky130 PDK

LibreLane will automatically fetch the PDK via [volare](https://github.com/efabless/volare)
on first run if `~/.volare/sky130A` does not exist.

To pre-install manually:

```bash
# Inside the LibreLane nix-shell:
cd ~/Downloads/Github/librelane && nix-shell --run \
  "volare enable --pdk sky130 bdc9412b3e468c102d01b7cf6337be06ec6e9c9a"
```

If the PDK is installed at a non-default location, override `PDK_ROOT`:

```bash
make run PDK_ROOT=/path/to/directory/containing/sky130A
```

---

## Usage

All commands are run from this directory (`pnr/librelane/`).

### Full flow (synthesis through GDS)

```bash
make run
```

### Synthesis only

```bash
make synth
```

### Show results from last run

```bash
make results
```

### Clean all run outputs

```bash
make clean
```

### Verify environment before running

```bash
make check_env
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `config.json` | Main LibreLane configuration — PDK, RTL, timing, placement, routing |
| `pin_order.cfg` | I/O pin placement — assigns ports to die edges |
| `../constraints/phase3_cache.sdc` | SDC timing constraints (75 MHz clock, I/O delays, false paths) |

### Key config.json parameters

| Key | Value | Notes |
|-----|-------|-------|
| `CLOCK_PERIOD` | 13.333 ns | 75 MHz |
| `FP_CORE_UTIL` | 45% | Conservative; cache FF arrays are large |
| `PL_TARGET_DENSITY` | 0.55 | 10% headroom above FP util for buffers |
| `CTS_TARGET_SKEW` | 100 ps | Target clock skew |
| `SYNTH_STRATEGY` | `DELAY 1` | Prioritise timing over area |

---

## Run Outputs

Each run creates a timestamped directory under `runs/RUN_<timestamp>/`:

```
runs/RUN_<timestamp>/
├── final/
│   ├── gds/rv32i_cpu_top.gds      # Final GDS (layout)
│   ├── def/rv32i_cpu_top.def      # Final DEF
│   ├── verilog/gl/                # Gate-level netlist
│   └── spef/                      # Parasitics
├── reports/
│   ├── synthesis/                 # Yosys area/timing
│   ├── timing/                    # OpenSTA setup/hold
│   ├── power/                     # Power estimates
│   └── drc/                       # DRC violations
└── logs/                          # Per-step logs
```

---

## Notes on Phase 3 Design

- **No SRAM macros**: The cache arrays are synthesised as register arrays (flip-flops). No macro LEF files are needed.
- **Phase 2 arbiter excluded**: `rv32i_axi_arbiter.sv` is not listed in `VERILOG_FILES` — it is superseded by `rv32i_cache_arbiter.sv` in Phase 3.
- **SystemVerilog packages**: `rv32i_pipeline_pkg.sv` and `rv32i_cache_pkg.sv` must appear first in `VERILOG_FILES`; Yosys reads them before the modules that import them.
- **Power domains**: The UPF file (`../constraints/phase3_cache.upf`) defines three power domains: `PD_TOP`, `PD_CORE`, `PD_CACHE`. LibreLane does not currently apply UPF during physical implementation; the UPF is used for documentation and future power-gating integration.

---

## Troubleshooting

**`librelane` not found**: The Makefile invokes LibreLane via `~/Downloads/Github/librelane/shell.nix`. If the repo is at a different path, override: `make run LIBRELANE_NIXDIR=/your/path`.

**PDK not found**: Set `PDK_ROOT` to the directory containing the `sky130A` folder, e.g.:
```bash
export PDK_ROOT=~/.volare
make run
```

**Synthesis fails with SV package errors**: Ensure Yosys version is 0.35+ (supports SV packages). Check with `yosys --version`.

**Timing violations after route**: The 75 MHz target is achievable but tight for the EX-stage ALU path on Sky130. Try increasing `SYNTH_STRATEGY` to `DELAY 2` and `PL_TARGET_DENSITY` to 0.50 to reduce routing detours.

**High congestion in cache area**: The FF-based cache arrays create dense clusters. Increase `FP_CORE_UTIL` to 40% (lower density) or `DIE_AREA` to 400×400 µm if congestion persists.
