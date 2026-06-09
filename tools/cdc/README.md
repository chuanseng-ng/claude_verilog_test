# CDC check — BerkeleyLab/Bedrock `cdc_snitch`

Clock-domain-crossing (CDC) static check for the SoC RTL, using the open-source
[`cdc_snitch`](https://github.com/BerkeleyLab/Bedrock/blob/master/build-tools/cdc_snitch.md)
tool from Berkeley Lab's Bedrock project.

**Status: parked / informational.** Wired up and proven to run on the full
`soc_top`, but **not a CI gate** — see "Why it's informational" below and the
full POC writeup in [`docs/verification/CDC_SNITCH_POC.md`](../../docs/verification/CDC_SNITCH_POC.md).

## How it works

```
sv2v (SystemVerilog -> Verilog-2005)  ->  yosys (flatten to gates/mem -> JSON)  ->  cdc_snitch.py
```

`cdc_snitch.py` walks the flattened netlist and classifies every register by
whether its data-source clock domains match its own clock:

| Category | Meaning |
| -------- | ------- |
| `OK1` | all inputs in the register's own domain (normal logic) |
| `CDC` | single-source crossing through trivial logic, marked `magic_cdc` (intentional) |
| `OKX` | single-source crossing, *not* marked (e.g. an input-sampling flop) |
| `BAD` | a register's data combines **multiple** clock domains (the dangerous anti-pattern) |

`cdc_snitch` treats **every top-level input port as its own clock domain**.

## Usage

```bash
# from the repo root
cd sim
make cdc                 # fetch tools (if needed) + run, informational
make cdc CDC_STRICT=1    # same, but exit non-zero if BAD>0 (gate semantics)
```

Or directly:

```bash
tools/cdc/fetch_cdc_tools.sh             # cdc_snitch + sv2v (yosys assumed on PATH)
tools/cdc/fetch_cdc_tools.sh --with-yosys  # also download oss-cad-suite (~700 MB)
```

Tools land in the git-ignored `sim/build/cdc/`; pinned versions are in
[`versions.env`](versions.env). The report is `sim/build/cdc/soc_top_cdc.txt`
(`grep BAD` it to inspect findings).

## Requirements

- `yosys` >= 0.23 on `PATH` (or fetch oss-cad-suite with `--with-yosys`)
- `python3`
- `sv2v` (auto-fetched). Needed because oss-cad-suite's built-in `yosys -sv`
  reader can't parse this RTL's package-import-in-package, and its `slang`
  plugin rejects the (frozen) Phase 3 cache RTL's mixed blocking/non-blocking
  array writes. `sv2v` sidesteps both with zero RTL changes.

## Why it's informational (not a gate yet)

The SoC is currently **single-clock** (`soc_top` fans one `clk_i`/`rst_n_i`
pair to everything). Because `cdc_snitch` models every top-level input port as a
separate clock domain, a raw run reports ~5200 `BAD` registers that are **all
false positives**:

- ~95% are the **async reset** `rst_n_i` modeled as a foreign domain (every flop).
- the rest are **synchronous** top-level buses (the APB debug bus, SPI) that are
  actually in the `clk_i` domain.
- there are **zero genuine internal multi-clock crossings** (correct — one clock).

It *does* correctly recognize the real async input `uart_rx_i` (→ `OKX`, the
2-FF synchronizer is seen), so it would catch a *missing* synchronizer.

To become a meaningful gate it needs a thin CDC wrapper that neutralizes the
reset domain and declares the synchronous top-level inputs as `clk_i`-domain.
That work is deferred to **Phase 6+**, when real multiple clock domains exist
and the tool earns its keep. See the POC writeup for details.
