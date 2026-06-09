# CDC Snitch integration — feasibility POC

**Status:** parked / informational (2026-06-09)
**Tool:** [BerkeleyLab/Bedrock `cdc_snitch`](https://github.com/BerkeleyLab/Bedrock/blob/master/build-tools/cdc_snitch.md) (pinned commit `8929d4d`)
**Runner:** `make -C sim cdc` → `tools/cdc/` (see [`tools/cdc/README.md`](../../tools/cdc/README.md))

## Goal

Evaluate whether Berkeley Lab's open-source `cdc_snitch` can detect clock-domain-crossing
(CDC) issues in this RV32I + GPU-lite SoC and serve as a CI gate.

## What cdc_snitch does

A small Python tool that runs Verilog through **yosys** (≥0.23), flattens the design to
gates/memories, writes a JSON netlist, and classifies every register by whether its
data-source clock domains match its own clock:

| Category | Meaning |
| -------- | ------- |
| `OK1` | all inputs in the register's own domain (normal logic) |
| `CDC` | single-source crossing through trivial logic, marked `magic_cdc` (intentional) |
| `OKX` | single-source crossing, not marked (e.g. an input-sampling flop) |
| `BAD` | a register's data combines **multiple** clock domains (the dangerous anti-pattern) |

Non-zero `BAD` → non-zero exit code. **Every top-level input port is treated as its own
clock domain.**

## Toolchain (what actually worked)

```text
sv2v (SystemVerilog -> Verilog-2005)  ->  yosys (flatten -> JSON)  ->  cdc_snitch.py
```

Front-end finding: **pure oss-cad-suite could not parse this RTL.**
- yosys built-in `read_verilog -sv` → syntax error on package-import-in-package
  (`soc_addr_map_pkg.sv`).
- the bundled `slang` plugin → rejects the **frozen** Phase 3 cache RTL's mixed
  blocking/non-blocking writes to `valid_array`/`dirty_array` (`rv32i_dcache.sv`).

Adding **sv2v** as a preprocessor resolves both with **zero RTL changes**. (Two unrelated
nits were worked around in the flow: `axi_lite_register_bank.sv` is absent from the
Verilator `SOC_TOP_SOURCES` list because Verilator auto-discovers it — it is added back
explicitly for the CDC flow.)

## Result (full `soc_top`, 52 RTL files, ~32k registers)

```text
OK1: 18249   CDC: 0   OKX: 8653   BAD: 5234
```

- ✅ The toolchain runs end-to-end and elaborates the **entire** SoC to a netlist.
- ✅ It **correctly recognized the real async input** `uart_rx_i`: 0 `BAD`, classified
  `OKX` (the 2-FF synchronizer in `uart_controller.sv` is seen). So it *would* catch a
  *missing* synchronizer.

### The 5234 `BAD` are ~100% false positives

Because cdc_snitch models every top-level input port as a separate clock domain, and this
SoC is **single-clock** (`soc_top` fans one `clk_i`/`rst_n_i` pair to everything):

| Foreign "domain" flagged | BAD registers | Reality |
| ------------------------ | ------------- | ------- |
| `rst_n_i` (async reset)  | ~4997 (95%)   | reset, not a clock domain |
| `apb_paddr_i` + APB ctrl | ~235          | APB debug bus, synchronous to `clk_i` |
| `spi_miso_i`             | 2             | SPI MISO sampled in `clk_i` domain (master mode) |

There are **zero genuine internal multi-clock crossings** — correct, because there is only
one clock. The one mildly interesting hit is `u_spi.rx_shift_q` / `rx_push_data` sampling
`spi_miso_i` without a 2-FF synchronizer; harmless in master mode but worth tracking as a
hardening opportunity (to be filed in beads — see "Follow-ups" below).

## Follow-ups

- **SPI MISO hardening:** evaluate adding a 2-FF synchronizer on `spi_miso_i` in
  `rtl/periph/spi_controller.sv` (`u_spi.rx_shift_q` / `rx_push_data`). Not a functional
  bug in master mode, but good CDC hygiene. File as a beads issue (`bd create`).

## Decision

**Park as a documented, informational tool.** Committed:
- `tools/cdc/` — pinned fetch (`fetch_cdc_tools.sh`, `versions.env`) + runner (`run_cdc.sh`).
- `make -C sim cdc` — informational by default; `make cdc CDC_STRICT=1` gives gate semantics.

**No CI gate yet.** As-is it is a permanently-red gate drowning in false positives.

## To make it a real gate (deferred to Phase 6+)

When real multiple clock domains are introduced, add a thin CDC verification wrapper that:
1. neutralizes the async-reset domain (synchronize reset internally / exclude `rst_n_i`),
2. declares the genuinely-synchronous top-level inputs (APB debug, SPI) as `clk_i`-domain
   (register them once before use, since cdc_snitch has no port-domain allowlist),
3. marks intentional crossings with the `magic_cdc` attribute (→ `CDC` instead of `OKX`).

The residual output then becomes meaningful and `BAD=0` can gate CI.
