# RTL filelists (`rtl/filelist/`)

Committed, tool-agnostic `.f` filelists of the RTL, for feeding an external tool (simulator, linter,
formatter, sv2v wrapper). Bead `1as3`.

| File | Contents | Top module |
| :--- | :------- | :--------- |
| `soc_top.f` | full SoC, as the cocotb regression elaborates it (default arm) | `soc_top` |
| `soc_top_sim_models.f` | simulation-only SRAM models for `soc_top.f` | |
| `cpu_top.f` / `cpu_top_sim_models.f` | CPU hard-macro cone (core + I$/D$ + arbiter) | `rv32i_cpu_top` |
| `gpu_top.f` / `gpu_top_sim_models.f` | GPU-lite hard-macro cone | `gpu_top` |

No testbench file is ever listed. Packages come first, then the remaining RTL in the authoritative
Make order. The behavioural SRAM models are kept in the `*_sim_models.f` companions because a hard
macro replaces them in the Sky130/ASAP7 arms; the synthesisable list never contains them.

## Path convention

- One path per line, **relative to the repository root**; `+incdir+<dir>` lines (also root-relative)
  for every directory holding a listed file. Comments are `//` lines.
- Run from the repository root and use **`-f`** (Verilator, VCS, Xcelium, Questa all resolve `-f`
  paths against the current directory).
- Do **not** use `-F`: it resolves paths against the `.f` file's own directory
  (`rtl/filelist/`) and would look for `rtl/filelist/rtl/...`.
- From another directory, print an absolute copy:
  `python3 tools/verif/gen_filelist.py --print soc_top --prefix /abs/path/to/repo > soc_top.abs.f`
  (add `--models` for the `_sim_models` companion).
- No `` `include `` exists in `rtl/` today, so the `+incdir+` lines are not load-bearing; they are there
  so a future include next to a source still resolves.

```bash
# Verilator (verified, 5.048)
verilator --lint-only -Wall -Wno-fatal --top-module soc_top \
    -f rtl/filelist/soc_top.f -f rtl/filelist/soc_top_sim_models.f

# sv2v takes no -f: strip comments/options and pass the paths
grep -hvE '^(//|\+|-|$)' rtl/filelist/soc_top.f rtl/filelist/soc_top_sim_models.f | xargs sv2v
```

VCS (`-f`), Xcelium (`xrun -f`) and Questa (`vlog -f`) accept this syntax per their documentation, but
no licence is available here, so those invocations are **unverified**.

## Defines (arm selectors) are not baked in

Pass them on the command line (`+define+NAME`, sv2v `--define=NAME`). The default arm (no define)
is what the cocotb regression elaborates.

| Define | Effect |
| :----- | :----- |
| *(none)* | default arm; behavioural SRAM models from `*_sim_models.f` |
| `SIMULATION` | sim-only checks, e.g. `cdc_sync` assertions (the regression sets it) |
| `SRAM_SKY130` | Sky130 SRAM macros in caches, `sram_controller`, `npu_weight_mem` |
| `SRAM_ASAP7` | ASAP7 SRAM macros (behind `rv32i_clock_gate`) in caches / `npu_weight_mem` |
| `FPGA` | block-RAM-inferable memories; also add `rtl/fpga/*.sv` (or `-y rtl/fpga`) |
| `__pnr__` | physical-design arm (sv2v/Yosys flows); drops sim-only code |
| `USE_ICG_CELL` | `rv32i_clock_gate` instantiates the ASAP7 ICG cell |
| `SRAM_CTRL_2P` | `sram_controller` dual-port variant (sim) |
| `TRNG_RO_SKY130` | Sky130 ring-oscillator entropy; needs `rtl/periph/trng_ro_sky130.sv` (in no list) |

`USE_SKY130_CLKCELLS` does not exist in `rtl/` and is not documented as a define.
In the `SRAM_*` and `__pnr__` arms the macros / ICG cell are hard macros with no source in these
lists; elaborating them reports exactly those cells as undefined (documented blackboxes).

## How the lists are produced (no drift)

`tools/verif/gen_filelist.py` derives them from the existing authoritative Make variables, with the
repo's single Make parser (`check_source_closure.extract_makefile_lists`):

| List | Source |
| :--- | :----- |
| `soc_top.f` | `tb/cocotb/soc/Makefile::PLL_SOURCES` minus `tb_*` plus `rtl/mem/rv32i_clock_gate.sv` |
| `cpu_top.f` | `pnr/Makefile::CPU_SV_FILES` |
| `gpu_top.f` | `pnr/Makefile::GPU_SV_FILES` |
| `*_sim_models.f` | the `sim/` entries of the list, plus `SRAM_SIM_MODEL` / `GPU_SRAM_SIM` |

`rv32i_clock_gate.sv` is added because `PLL_SOURCES` never names it (Verilator finds it via
`-I rtl/mem`); sv2v has no `-I` discovery and **silently blackboxes a missing module**.

```bash
python3 tools/verif/gen_filelist.py          # regenerate; commit the result
python3 tools/verif/gen_filelist.py --check  # what CI runs (qa-checks.yml); exit 1 on drift
python3 -m pytest tb/tests/test_gen_filelist.py
```

Change a Make source list, then run the generator and commit `rtl/filelist/`. The Makefiles do **not**
consume these files yet (follow-up: have them `-f` the `.f` so there is a single copy).

## Proving a list is complete

Verilator `+incdir+` behaves like `-I`: it auto-discovers a module by file name, which can hide a
missing list entry (that is how `rv32i_clock_gate` stayed out of `PLL_SOURCES`). Prove completeness
with the include lines stripped:

```bash
grep -v '^+incdir' rtl/filelist/soc_top.f > /tmp/soc_top.noinc.f
grep -v '^+incdir' rtl/filelist/soc_top_sim_models.f > /tmp/soc_top_sim_models.noinc.f
verilator --lint-only -Wno-fatal --top-module soc_top -f /tmp/soc_top.noinc.f -f /tmp/soc_top_sim_models.noinc.f
```

Dropping the `_sim_models.f` companion then fails with `MODMISSING` for `sram_1rw_256x32_freepdk45`,
which confirms the separation is real.
