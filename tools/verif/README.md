# `tools/verif` — static verification-infrastructure checks

## `check_source_closure.py`

Checks that a Verilog/SystemVerilog source list — a PD `config.json`'s
`VERILOG_FILES`, or a Makefile's `VERILOG_SOURCES`/`*_SOURCES` variable —
**closes over its own imports**: every `import <pkg>::...` used by a file in
the list is satisfied by a `package <pkg>;` declared in another file *also in
that list*.

```bash
python3 tools/verif/check_source_closure.py               # scan the whole repo
python3 tools/verif/check_source_closure.py --json         # machine-readable
python3 tools/verif/check_source_closure.py tb/cocotb/cpu/Makefile
python3 tools/verif/check_source_closure.py pnr/asap7/cpu/config.json
```

Exit 0 if every discovered list closes; exit 1 if any list is missing a
package, references a file that doesn't exist on disk, or contains a Make
variable/`$(shell ...)` idiom the built-in resolver doesn't recognize (in
which case it's reported as an unresolved token rather than silently
ignored).

### Why this exists

Bead `claude_verilog_test-50t`: `tb/cocotb/cpu/Makefile`'s `VERILOG_SOURCES`
never picked up `rtl/soc/axi_pkg.sv` (or `soc_addr_map_pkg.sv`, or the
EX1b/EX1c/EX2 pipeline-retiming split) after the RTL moved onto them —
Verilator failed at elaboration with `Import package not found: 'axi_pkg'`
on every target, and nothing caught it because CI never built that TB (the
maintained regression, `tb/cocotb/soc soc_all`, builds its own source list
and was unaffected). This is the same defect class as bead `v2q`
(`pnr/asap7/cpu/config.json` had the identical gap before that fix): a
hand-maintained file list silently rotting behind RTL package additions,
with no gate anywhere checking the two against each other.

This script is that gate. It's deliberately dependency-free (stdlib only, no
simulator, no `nix develop`) so it can run in the fast/PR CI tier, not just
nightly.

### Scope and known limitations

- Only checks **package closure** (SystemVerilog `import pkg::*`/`import
  pkg::name`), not module-instantiation closure — a list can close on
  packages while still being missing a leaf module. That failure mode
  degrades differently (Verilator reports the specific missing module by
  name at elaboration, versus the `axi_pkg` case where every downstream
  error looked like a mysterious type error) and was judged lower-priority
  to check statically; instantiation closure would need a real parser, not
  regex.
- The bundled Make-variable resolver is a narrow reimplementation of the GNU
  Make idioms actually used in this repo's Makefiles (`:=`, `+=`, `?=`,
  backslash continuation, `$(PWD)`/`$(CURDIR)`, `$(abspath ...)`, and a
  two-entry `$(shell ...)` allowlist: `pwd` / `cd .. && pwd` and a `find
  <dir> -name '<glob>'` pattern) — not a general Make evaluator. A Makefile
  using a `$(shell ...)` call outside that allowlist is reported as an
  *unresolved token* (a real failure, not a false negative) rather than
  silently mis-resolved; extend `_resolve_shell()` if a new one is needed.
- A `config.json`'s `VERILOG_FILES` entries that aren't `dir::`-prefixed
  (e.g. PDK-relative `$PDK_ROOT/...` macro views) are skipped — they aren't
  repo-relative design sources this check can reason about.
- Relative paths in a Makefile resolve against **that Makefile's own
  directory**, not the repo root and not the invoking CWD. `pnr/Makefile`
  has `RTL_DIR := ../rtl` and `PROJECT_ROOT := $(abspath ..)`, both of which
  mean the repo root only when read from `pnr/`. Getting this wrong doesn't
  under-report — it reports every file in the list as missing.
- `pnr/asap7/template/config.json` reports as a gap when scanned in place —
  it's a stencil meant to be copied into a sibling `pnr/asap7/<design>/`
  directory (its `dir::../../rtl/...` paths are one level short from
  `template/`), not a runnable list on its own. Known, not a bug.

### Repo-wide status as of 2026-08-11

| List | Status |
| ---- | ------ |
| `tb/cocotb/cpu/Makefile:VERILOG_SOURCES` | closes (fixed by bead `50t`) |
| `tb/cocotb/soc/Makefile` (18 source vars) | closes |
| `sim/Makefile:VERILOG_SOURCES`/`CACHE_SOURCES`/`GPU_SOURCES`/`SOC_TOP_SOURCES` | closes |
| `pnr/asap7/{cpu,gpu,soc}/config.json`, `pnr/sky130/{cpu,soc}/config.json` | closes |
| `pnr/Makefile:RTL_SOURCES` (the `make -C pnr lint` list) | closes (fixed by bead `a7k`) |
| `pnr/Makefile:SOC_SV_FILES`/`SKY130_SOC_SV_FILES` (sv2v inputs) | closes |
| `pnr/freepdk45/config.json`, `pnr/librelane/config.json`, `pnr/openlane/config.json`, `pnr/openlane1/config.json` | **gap** — missing `axi_pkg`/`soc_addr_map_pkg`, same defect class as `50t`, predates the M2 AXI4 burst upgrade. Not fixed here (out of scope for a verification-branch bead) — file a follow-up bead against whichever of these flows is still live before relying on them. |
| `pnr/asap7/template/config.json` | reports a gap in place — expected, see above |

Run `python3 tools/verif/check_source_closure.py` to reproduce.
