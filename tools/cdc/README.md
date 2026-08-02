# CDC check — `cdc_snitch` + `cdc_gate`

Static clock-domain-crossing (CDC) check for the SoC RTL, built on the
open-source
[`cdc_snitch`](https://github.com/BerkeleyLab/Bedrock/blob/master/build-tools/cdc_snitch.md)
tool from Berkeley Lab's Bedrock project, plus an in-repo post-processor that
turns its raw output into a usable gate.

**Status: real gate** (GH #95). Was parked/informational from the 2026-06-09
POC until the SoC actually became multi-clock (GH epic #90). Full POC history:
[`docs/verification/CDC_SNITCH_POC.md`](../../docs/verification/CDC_SNITCH_POC.md).

## How it works

```
sv2v (SystemVerilog -> Verilog-2005)
  -> yosys (flatten to gates/mem -> JSON)
  -> cdc_snitch.py   (classify every register)
  -> cdc_gate.py     (canonicalize domains, apply waivers, decide)
```

`cdc_snitch.py` classifies every register by whether its data-source clock
domains match its own clock:

| Category | Meaning |
| -------- | ------- |
| `OK1` | all inputs in the register's own domain (normal logic) |
| `CDC` | single-source crossing through trivial logic, marked `magic_cdc` (intentional) |
| `OKX` | single-source crossing, *not* marked (e.g. an input-sampling flop) |
| `BAD` | a register's data combines **multiple** clock domains |

### Why the raw `BAD` count is not the verdict

`cdc_snitch` has three structural blind spots on a design like this one:

1. **Every top-level input port is its own clock domain.** So an async reset
   port appears as a foreign "domain" on the reset pin of every flop it
   reaches.
2. **A clock-gate output is a different net from its source clock.** So
   `cpu_gated_clk` and `cpu_clk_i` look like two domains when they are one.
3. **A synchronous bus contributes one "domain" per bit.** A 12-bit address
   bus alone puts 12 domains into a register's input set.

None of these can be fixed with the `magic_cdc` attribute: that attribute only
promotes a **single**-source crossing from `OKX` to `CDC`. A multi-domain
register stays `BAD` regardless — from `cdc_snitch.py`'s own `check_bit()`:
*"doesn't matter if they claim CDC or not, it's still bad."*

On the 2026-08-02 baseline (first multi-clock run, main + GH #93):

```
OK1: 17009   CDC: 37   OKX: 464   BAD: 16233
```

…of which **15962 (98.3%) are pure modelling artifacts**.

### What `cdc_gate.py` does

1. **Canonicalizes** each source domain using [`cdc_config.yml`](cdc_config.yml)
   — clock aliases, reset ports, synchronous buses. These rules encode the same
   design facts that `pnr/constraints/phase5_soc_multiclock.sdc` already
   encodes for STA. They are deliberately *not* per-line waivers: they apply
   uniformly, and if the clock topology changes they stop matching and the gate
   re-opens.
2. **Re-decides**: a register is still `BAD` only if ≥2 distinct canonical
   domains remain.
3. **Waives** the residue those rules cannot express, from an explicit list.
   Each waiver needs an `id`, a `kind`, a `reason`, and a `ref`.
   - `kind: tool-limitation` — a correct, reviewed structure `cdc_snitch`
     cannot represent (a qualified async FIFO, a 2-phase handshake).
   - `kind: accepted-risk` — a real gap we knowingly carry. Must name a
     tracking bead, and is printed loudly on every run.
4. **Fails** on any unwaived `BAD`, **and** on any waiver that matched nothing.
   A stale waiver means the crossing it covered was renamed, removed, or is no
   longer being checked — all failures, not free passes.

## Usage

```bash
cd sim
make cdc                 # fetch tools (if needed) + run, informational
make cdc CDC_STRICT=1    # same, but exit non-zero if the GATE fails
```

Or drive the pieces directly:

```bash
tools/cdc/fetch_cdc_tools.sh               # cdc_snitch + sv2v (yosys assumed on PATH)
tools/cdc/fetch_cdc_tools.sh --with-yosys  # also download oss-cad-suite (~700 MB)

# re-run just the gate against an existing report (fast, no yosys needed)
tools/cdc/cdc_gate.py sim/build/cdc/soc_top_cdc.txt -v
```

Tools land in the git-ignored `sim/build/cdc/`; pinned versions are in
[`versions.env`](versions.env). Outputs:

| File | Contents |
| ---- | -------- |
| `sim/build/cdc/soc_top_cdc.txt` | raw `cdc_snitch` report |
| `sim/build/cdc/soc_top_cdc_gate.json` | machine-readable gate summary |

## Requirements

- `yosys` >= 0.23 on `PATH` (or fetch oss-cad-suite with `--with-yosys`)
- `python3` with **PyYAML** (`python3 -m pip install --user pyyaml`)
- `sv2v` (auto-fetched). Needed because oss-cad-suite's built-in `yosys -sv`
  reader can't parse this RTL's package-import-in-package, and its `slang`
  plugin rejects the (frozen) Phase 3 cache RTL's mixed blocking/non-blocking
  array writes. `sv2v` sidesteps both with zero RTL changes.

This flow runs in the **plain system shell**, not inside `nix develop` — the
sim devshell deliberately ships no Python interpreter and no yosys.

## Marking intentional crossings in RTL

Put `(* magic_cdc *)` on the synchroniser flop array itself. The attribute
survives `sv2v` and `yosys` flattening (verified: it reaches
`pnr/sky130/soc/soc_top_sv2v.v`). Two places carry it today, and every
synchroniser in the design is an instance of one of them:

- [`rtl/soc/cdc/cdc_2ff_sync.sv`](../../rtl/soc/cdc/cdc_2ff_sync.sv) — the
  generic N-stage data synchroniser
- [`rtl/soc/cdc/cdc_reset_sync.sv`](../../rtl/soc/cdc/cdc_reset_sync.sv) — the
  reset synchroniser chain

**Do not remove those attributes.** Prefer instantiating these primitives over
hand-rolling a synchroniser — you get the marking, the elaboration guards, and
the STA hooks for free.

## What the gate does and does not prove

It **does** prove that every register combining two real clock domains is
either passing through a marked synchroniser or is explicitly waived with a
written justification. It caught a genuine unsynchronised chip-boundary
crossing that no simulation suite could see.

It **does not** model metastability, does not check synchroniser *depth*
against an MTBF target, and does not verify that a qualified crossing's
handshake protocol is actually correct — that is the directed cocotb suites'
job (`async_axi_fifo`, `apb_cdc_bridge`, `soc_multiclock`) and STA's
(`set_max_delay -datapath_only` in `phase5_soc_multiclock.sdc`).
