# UPF Power Intent Specification

Document status: Phase 1 integration
Target audience: Physical design engineers, power architects, verification engineers
Standard: IEEE 1801-2015 (UPF 3.0)

## Overview

This document specifies the power intent for the RV32I+GPU SoC using Unified Power Format (UPF). Power management is introduced incrementally across phases to balance complexity and power savings.

### Power Management Goals

1. **Reduce dynamic power**: Clock gating, power gating idle blocks
2. **Reduce leakage power**: Power down unused domains
3. **Preserve functionality**: Isolation and retention strategies
4. **Enable flexibility**: Multiple power modes for different workloads

### Incremental Power Strategy

- **Phase 1**: Single domain (prepare infrastructure, no power gating yet)
- **Phase 2**: Core + debug domains (enable basic power gating)
- **Phase 3**: Core + I-cache + D-cache domains (cache power management)
- **Phase 4**: Add GPU domain with DVFS (voltage/frequency scaling)
- **Phase 5**: Full system with 5+ domains (always-on, peripherals, etc.)

## UPF Concepts

### Power Domains

A **power domain** is a collection of design elements that share the same power supply and can be powered on/off together.

**Example**: CPU core, debug interface, caches, GPU, peripherals

### Supply Networks

A **supply network** defines the power (VDD) and ground (VSS) nets for a domain.

**Example**: `VDD_CORE`, `VDD_GPU`, `VDD_AON` (always-on), `VSS`

### Isolation Cells

**Isolation cells** prevent X (unknown) values from propagating from a powered-down domain to a powered-on domain.

**Location**: At domain boundaries (outputs of powered-down domain)
**Clamp value**: 0 or 1 (designer specifies safe value)
**Control**: Enabled when source domain is powered down

### Level Shifters

**Level shifters** convert signals between domains operating at different voltages.

**Example**: Core at 0.9V, peripherals at 1.8V

**Direction**: Low-to-high or high-to-low

### Retention Registers

**Retention registers** preserve their state during power-down using a separate always-on supply.

**Use case**: Save critical state (PC, control registers) during sleep mode

**Restore**: State restored automatically when domain powers back on

### Power State Tables (PST)

A **power state table** defines the legal combinations of power states across domains.

**States**:

- `ON`: Domain fully powered
- `OFF`: Domain powered down
- `RETENTION`: Domain powered down but state preserved

## Phase 1: Single-Domain CPU

### Power Architecture

**Domains**: Single domain (no power gating yet)
**Purpose**: Establish UPF infrastructure, prepare for multi-domain in Phase 2

```text
┌─────────────────────────────┐
│       PD_TOP (VDD)          │
│                             │
│  ┌───────────────────────┐  │
│  │    RV32I Core         │  │
│  │  (single-cycle)       │  │
│  └───────────────────────┘  │
│                             │
│  ┌───────────────────────┐  │
│  │  AXI4-Lite Master     │  │
│  └───────────────────────┘  │
│                             │
│  ┌───────────────────────┐  │
│  │  APB3 Slave (Debug)   │  │
│  └───────────────────────┘  │
│                             │
└─────────────────────────────┘
```

### UPF File: phase1_cpu.upf

```tcl
# Phase 1: Single-domain CPU (infrastructure only)

# Create top-level power domain
create_power_domain PD_TOP -include_scope

# Create supply ports
create_supply_port VDD -direction in
create_supply_port VSS -direction in

# Create supply nets
create_supply_net VDD -domain PD_TOP
create_supply_net VSS -domain PD_TOP -reuse

# Connect supply ports to nets
connect_supply_net VDD -ports {VDD}
connect_supply_net VSS -ports {VSS}

# Define primary supply set
create_supply_set SS_TOP \
    -function {power VDD} \
    -function {ground VSS}

# Associate supply set with domain
associate_supply_set SS_TOP -handle PD_TOP

# Define single power state (always on)
add_power_state PD_TOP \
    -state ON {-supply_expr {power == FULL_ON && ground == FULL_ON}}

# Set design top
set_design_top rv32i_cpu_top
```

**Notes**:

- No isolation or retention in Phase 1 (single domain)
- This UPF establishes the foundation for Phase 2 multi-domain
- Gate-level simulation uses this UPF to verify supply connections

## Phase 2: Pipelined CPU with Power Domains

### Power Architecture

**Domains**: 3 domains (core, debug, always-on)
**Power gating**: Core can be powered down (debug remains on)
**Isolation**: Between core and debug

```text
┌─────────────────────────────────────────────┐
│         PD_AON (VDD_AON - always on)        │
│  ┌─────────────────────────────────────┐   │
│  │  Power Control Registers            │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│         PD_CORE (VDD_CORE - gatable)        │
│  ┌─────────────────────────────────────┐   │
│  │  5-Stage Pipeline                   │   │
│  │  - Fetch, Decode, Execute           │   │
│  │  - Memory, Writeback                │   │
│  │  - Register File                    │   │
│  │  - ALU, Control                     │   │
│  └─────────────────────────────────────┘   │
│                                             │
│       [Isolation Cells] ───────►            │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│      PD_DEBUG (VDD_DEBUG - always on)       │
│  ┌─────────────────────────────────────┐   │
│  │  APB3 Debug Interface               │   │
│  │  - Control registers                │   │
│  │  - Breakpoint logic                 │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### UPF File: phase2_pipelined_cpu.upf

```tcl
# Phase 2: Pipelined CPU with power domains

#=============================================
# Power Domains
#=============================================

# Top-level domain (always on)
create_power_domain PD_TOP -include_scope

# Always-on domain (power control, clock control)
create_power_domain PD_AON \
    -elements {i_power_ctrl}

# CPU core domain (can be gated)
create_power_domain PD_CORE \
    -elements {i_rv32i_core}

# Debug domain (always on for debugger access)
create_power_domain PD_DEBUG \
    -elements {i_rv32i_debug}

#=============================================
# Supply Ports
#=============================================

create_supply_port VDD_AON -direction in
create_supply_port VDD_CORE -direction in
create_supply_port VDD_DEBUG -direction in
create_supply_port VSS -direction in

#=============================================
# Supply Networks
#=============================================

# Always-on supply
create_supply_net VDD_AON -domain PD_TOP
create_supply_net VDD_AON_AON -domain PD_AON -reuse

# Core supply (switchable)
create_supply_net VDD_CORE -domain PD_TOP
create_supply_net VDD_CORE_CORE -domain PD_CORE -reuse

# Debug supply (always on)
create_supply_net VDD_DEBUG -domain PD_TOP
create_supply_net VDD_DEBUG_DEBUG -domain PD_DEBUG -reuse

# Ground (shared)
create_supply_net VSS -domain PD_TOP -reuse

# Connect ports to nets
connect_supply_net VDD_AON -ports {VDD_AON}
connect_supply_net VDD_CORE -ports {VDD_CORE}
connect_supply_net VDD_DEBUG -ports {VDD_DEBUG}
connect_supply_net VSS -ports {VSS}

#=============================================
# Supply Sets
#=============================================

create_supply_set SS_AON \
    -function {power VDD_AON_AON} \
    -function {ground VSS}

create_supply_set SS_CORE \
    -function {power VDD_CORE_CORE} \
    -function {ground VSS}

create_supply_set SS_DEBUG \
    -function {power VDD_DEBUG_DEBUG} \
    -function {ground VSS}

# Associate with domains
associate_supply_set SS_AON -handle PD_AON
associate_supply_set SS_CORE -handle PD_CORE
associate_supply_set SS_DEBUG -handle PD_DEBUG

#=============================================
# Isolation Strategy
#=============================================

# Isolate core outputs when powered down
set_isolation ISO_CORE_OUT \
    -domain PD_CORE \
    -isolation_supply_set SS_AON \
    -clamp_value 0 \
    -applies_to outputs \
    -isolation_signal iso_core_en \
    -isolation_sense high \
    -location parent

# Map isolation control signal
map_isolation_cell ISO_CORE_OUT \
    -domain PD_CORE \
    -lib_cells {ISO_LOW}

#=============================================
# Retention Strategy
#=============================================

# Retain critical state (PC, control registers)
set_retention RET_CORE \
    -domain PD_CORE \
    -retention_supply_set SS_AON \
    -retention_signal ret_core_en \
    -retention_sense high \
    -save_signal save_core \
    -save_sense high \
    -restore_signal restore_core \
    -restore_sense high

# Map retention cells
map_retention_cell RET_CORE \
    -domain PD_CORE \
    -lib_cells {RET_DFF}

#=============================================
# Power State Table
#=============================================

# Define power states for each domain
add_power_state PD_AON \
    -state ON {-supply_expr {power == FULL_ON}}

add_power_state PD_CORE \
    -state ACTIVE {-supply_expr {power == FULL_ON}} \
    -state IDLE {-supply_expr {power == FULL_ON}} \
    -state RETENTION {-supply_expr {power == OFF}} \
    -state OFF {-supply_expr {power == OFF}}

add_power_state PD_DEBUG \
    -state ON {-supply_expr {power == FULL_ON}}

# Define system-level power states
create_pst system_pst -supplies {VDD_AON_AON VDD_CORE_CORE VDD_DEBUG_DEBUG}

# Active mode: all domains on
add_pst_state ACTIVE -pst system_pst \
    -state {ON ACTIVE ON}

# Idle mode: core idle but powered
add_pst_state IDLE -pst system_pst \
    -state {ON IDLE ON}

# Sleep mode: core in retention
add_pst_state SLEEP -pst system_pst \
    -state {ON RETENTION ON}

# Deep sleep: core powered off (no retention)
add_pst_state DEEP_SLEEP -pst system_pst \
    -state {ON OFF ON}
```

### Power Mode Transitions (Phase 2)

**ACTIVE → IDLE**:

1. CPU idle (WFI instruction or no work)
2. Clock gating enabled automatically
3. No state change required

**IDLE → SLEEP**:

1. Software writes to power control register
2. Assert `save_core` signal (save state to retention cells)
3. Assert `iso_core_en` (enable isolation)
4. Assert `ret_core_en` (enable retention supply)
5. Gate `VDD_CORE` supply

**SLEEP → ACTIVE**:

1. Interrupt or wake event
2. Ungate `VDD_CORE` supply
3. Wait for supply to stabilize
4. Assert `restore_core` (restore state from retention cells)
5. Deassert `ret_core_en`
6. Deassert `iso_core_en`
7. Resume execution

## Phase 3: Cache System with Power Domains

### Power Architecture

**Domains**: 5 domains (core, I-cache, D-cache, debug, always-on)
**Power gating**: Caches can be powered down independently
**Retention**: Cache tags retained (data lost)

```text
┌─────────────────────────────────────────────┐
│         PD_AON (VDD_AON - always on)        │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│         PD_CORE (VDD_CORE - gatable)        │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│       PD_ICACHE (VDD_ICACHE - gatable)      │
│  ┌─────────────────────────────────────┐   │
│  │  I-Cache Tag Array (retention)      │   │
│  │  I-Cache Data Array (no retention)  │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│       PD_DCACHE (VDD_DCACHE - gatable)      │
│  ┌─────────────────────────────────────┐   │
│  │  D-Cache Tag Array (retention)      │   │
│  │  D-Cache Data Array (no retention)  │   │
│  │  Write-back buffer (retention)      │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│         PD_DEBUG (VDD_DEBUG - always on)    │
└─────────────────────────────────────────────┘
```

### UPF Additions (Phase 3)

```tcl
# Additional domains for Phase 3

create_power_domain PD_ICACHE \
    -elements {i_icache}

create_power_domain PD_DCACHE \
    -elements {i_dcache}

# Isolation for caches
set_isolation ISO_ICACHE_OUT \
    -domain PD_ICACHE \
    -isolation_supply_set SS_AON \
    -clamp_value 0 \
    -applies_to outputs

set_isolation ISO_DCACHE_OUT \
    -domain PD_DCACHE \
    -isolation_supply_set SS_AON \
    -clamp_value 0 \
    -applies_to outputs

# Retention for cache tags
set_retention RET_ICACHE_TAG \
    -domain PD_ICACHE \
    -retention_supply_set SS_AON \
    -elements {i_icache/tag_array}

set_retention RET_DCACHE_TAG \
    -domain PD_DCACHE \
    -retention_supply_set SS_AON \
    -elements {i_dcache/tag_array}

# Power states for caches
add_power_state PD_ICACHE \
    -state ACTIVE {-supply_expr {power == FULL_ON}} \
    -state RETENTION {-supply_expr {power == OFF}} \
    -state OFF {-supply_expr {power == OFF}}

add_power_state PD_DCACHE \
    -state ACTIVE {-supply_expr {power == FULL_ON}} \
    -state RETENTION {-supply_expr {power == OFF}} \
    -state OFF {-supply_expr {power == OFF}}
```

## Phase 4: GPU with DVFS

### Power Architecture

**Domains**: 6 domains (core, caches, GPU, debug, always-on)
**Voltage scaling**: GPU operates at lower voltage for power efficiency
**Level shifters**: Between core (0.9V) and GPU (0.7V)

```text
┌─────────────────────────────────────────────┐
│         PD_AON (1.8V - always on)           │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│         PD_CORE (0.9V - switchable)         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│          PD_GPU (0.7V - switchable)         │
│  ┌─────────────────────────────────────┐   │
│  │  GPU Compute Unit                   │   │
│  │  - Warp scheduler                   │   │
│  │  │  - 8-lane SIMT datapath         │   │
│  │  - Register file                    │   │
│  └─────────────────────────────────────┘   │
│                                             │
│       [Level Shifters] ◄───► Core          │
└─────────────────────────────────────────────┘
```

### UPF Additions (Phase 4)

```tcl
# GPU power domain
create_power_domain PD_GPU \
    -elements {i_gpu_compute}

# GPU supply (lower voltage)
create_supply_port VDD_GPU -direction in
create_supply_net VDD_GPU -domain PD_TOP
create_supply_net VDD_GPU_GPU -domain PD_GPU -reuse

create_supply_set SS_GPU \
    -function {power VDD_GPU_GPU} \
    -function {ground VSS}

associate_supply_set SS_GPU -handle PD_GPU

# Level shifters (core <-> GPU interface)
set_level_shifter LS_CORE_TO_GPU \
    -domain PD_GPU \
    -applies_to inputs \
    -rule low_to_high \
    -location parent

set_level_shifter LS_GPU_TO_CORE \
    -domain PD_GPU \
    -applies_to outputs \
    -rule high_to_low \
    -location self

# Map level shifter cells
map_level_shifter_cell LS_CORE_TO_GPU \
    -domain PD_GPU \
    -lib_cells {LS_LOHV}

map_level_shifter_cell LS_GPU_TO_CORE \
    -domain PD_GPU \
    -lib_cells {LS_HVLO}

# GPU power states
add_power_state PD_GPU \
    -state ACTIVE_HIGH {-supply_expr {power == 0.9}} \
    -state ACTIVE_LOW {-supply_expr {power == 0.7}} \
    -state OFF {-supply_expr {power == OFF}}

# DVFS modes
add_pst_state COMPUTE_HIGH_PERF -pst system_pst \
    -state {ON ACTIVE ON ACTIVE ON ACTIVE_HIGH}

add_pst_state COMPUTE_LOW_POWER -pst system_pst \
    -state {ON ACTIVE ON ACTIVE ON ACTIVE_LOW}
```

## Phase 5: Full SoC Integration

The Phase 5 SoC (`soc_top`) has **four** power domains on one nominal voltage, not the seven
sketched when this chapter was first written. The authoritative description is
`pnr/constraints/phase5_soc.upf` (IEEE 1801-2015 / UPF 3.0); this chapter summarises it and records
what the RTL does and does not implement. The file was rewritten on 2026-10-17 (bead `h3lm`) after an
audit found it had drifted from the RTL. Its purpose is input for UPF-aware test tools.

### Power Architecture

| Domain | Elements | Primary supply | Notes |
| :----- | :------- | :------------- | :---- |
| `PD_CPU` | `u_cpu` (hard macro, incl. L1 caches) | `SS_CPU` (`VDD_CPU`, switchable) | gated by clock gate + reset + clamp |
| `PD_GPU` | `u_gpu` | `SS_GPU` (`VDD_GPU`, switchable) | same |
| `PD_SRAM` | `u_sram` | `SS_AON` (`VDD`) | always on |
| `PD_PERIPH` | the top scope and every other instance | `SS_AON` (`VDD`) | always on |

`PD_PERIPH` is `-elements {.}` minus the three carved-out instances, and its **membership is
explicit**: the UPF header carries a `# upf-check aon <instance>` roster of the 32 always-on
top-level instances with the reason each must stay powered (the CPU-domain synchronisers, both clock
gates, the CDC bridges, the PMU, the DFT seam, the PLLs, the fabric and the peripherals). The checker
fails if a top-level instance is added to or removed from `soc_top` without updating the roster.

### What is modelled, and what is deliberately not

- **Power switches: none.** `pmu.sv` emits no switch control (`cpu_pg_ctrl` / `gpu_pg_ctrl` do not
  exist) and no `soc_top` net could drive one. The old `create_power_switch` commands controlled
  ports that were never in the RTL and used options no UPF parser accepts. `VDD_CPU` / `VDD_GPU` are
  therefore modelled as externally driven supply ports with ON / OFF port states, so each supply net
  has a source. The UPF header carries the shape of the switch to add once RTL control exists.
- **Isolation: exactly the signals `soc_top` clamps**, not every output. `ISO_CPU` (6 signals,
  control `pmu_cpu_iso_en_sync`) and `ISO_GPU` (8 signals, control `pmu_gpu_iso_en`), clamp value 0,
  sense high, `-location parent`, supply `SS_AON`. The set is checked for equality with the RTL in
  both SRAM arms. AXI address/data/control buses stay unclamped because each is qualified by a clamped
  valid and is don't-care once valid is 0. Every other output of `u_cpu` / `u_gpu` is classified in the
  UPF (`payload`, `slave_response`, `observability`) so a new output cannot escape review.
- **PMU outputs are flop Q pins (bead `ktwt`).** `pmu_*_clk_en` / `iso_en` / `rst_n` / `ret_*` are each
  registered inside `pmu.sv` from the decode of the *next* FSM state, so they appear in exactly the
  cycle the earlier combinational decode showed them (the sequence above and `test_pmu`'s per-cycle
  expectations are unchanged: zero added latency). They feed `cdc_sync` D pins, the asynchronous clear
  of `u_cpu_pmu_rst_sync` and the GPU async reset / clamp select, where a decode glitch on the 4-bit
  binary state (possible on 4 of the 9 transitions, including a runt reset on `DOM_PU_RESTORE` ->
  `DOM_PU_ISO`) would be a real event. Zero-delay simulation cannot show a glitch, so
  `tools/verif/check_registered_outputs.py` proves it on the netlist (`tb/tests/test_pmu_registered_outputs.py`).
- **Retention: none.** The old header claim that state is "rebuilt from SRAM on wakeup" was never
  true. `pmu.sv` emits `ret_save` / `ret_restore` in order but `soc_top` leaves them unconnected.
  See `docs/POWER_DOMAIN_EVALUATION.md` section 3 for what survives a PMU off/on cycle.
- **Not expressed** because the RTL or library offers nothing to bind: macro PG-pin connections (done
  by `pnr/*/pdn*.tcl`), level shifters (single voltage), isolation and retention cell mapping (neither
  ASAP7 nor Sky130 ships an isolation cell).

### Power states

Supply sets carry ON (and OFF for the two switchable rails). The system group `SOC_PST` has five
states whose names and encodings come from `rtl/soc/pmu.sv` (`CTRL[1:0]`, `u_pmu/pmu_mode_req`):

| State | `pmu_mode_req` | `SS_CPU` | `SS_GPU` | `scan_mode_i` |
| :---- | :------------- | :------- | :------- | :------------ |
| `NORMAL` | `2'b00` | ON | ON | 0 |
| `CPU_OFF` | `2'b01` | OFF | ON | 0 |
| `GPU_OFF` | `2'b10` | ON | OFF | 0 |
| `IDLE` | `2'b11` | OFF | OFF | 0 |
| `SCAN` | not constrained | ON | ON | 1 |

`pmu_mode_req` is the *requested* mode; the PMU takes four single-cycle actions per direction, and
those transient cycles belong to no named state.

**`SCAN` versus the RTL (confirmed in `soc_top.sv` and `dft_ctrl_ports.sv`):**

| Aspect under `scan_mode_i = 1` | RTL behaviour | Matches "all ON"? |
| :----------------------------- | :------------ | :---------------- |
| Clock gates | forced open: `test_en_o = scan_mode_i`, `rv32i_clock_gate` latches `en \| test_en` | yes (checked) |
| Domain resets | forced to the scan reset (`dft_rst_mux`, `cdc_reset_sync` output muxes) | yes |
| PMU | **not overridden**: mode register and FSM are ordinary scan-chain flops | no |
| ISO clamps | **not qualified by `scan_mode_i`**; follow `pmu_*_iso_en` | no |

So under scan a clamp can be active, depending on the PMU state shifted in. This is a real mismatch
with the intent of the `SCAN` state. It is documented, not changed (follow-up bead).

### Known gaps and follow-ups

1. **Isolation-versus-reset ordering (was: no handshake; FIXED, bead `3ogd`).** The PMU walks the UPF
   order (down: save, isolate, gate, reset; up: reset release, ungate, restore, de-isolate). The CPU
   clamp control passes a 2-flop synchroniser into `cpu_core_clk` while the reset reaches `u_cpu`
   through a `cdc_reset_sync` with asynchronous assertion, so with the actions merely spaced one
   `core_clk` cycle apart "isolate before reset asserts" held only while two `cpu_core_clk` edges were
   shorter than two `core_clk` cycles (it failed at a CPU clock 3x slower). `soc_top.u_cpu_iso_ack_sync`
   now synchronises the CPU-domain clamp control back into `core_clk` (`pmu_cpu_iso_ack`) and the CPU
   `DOM_PD_ISO` state waits for it before the clock gate and the reset; `DOM_PU_ISO` waits for it to
   fall (return-to-zero, which also stops a stale ack from satisfying the next power-down). Power-up
   needs no ack for the iso-release-vs-reset-release order: the clamp's consumers are clocked by
   `cpu_gated_clk`, which cannot tick before the reset release is observed (`cpu_gated_clk_en` includes
   `pmu_cpu_rst_n_cpu_sync`). The GPU needs none (same clock, the clamp control is the PMU flop). The step order of
   this UPF is unchanged. A dead CPU clock (CPU PLL unlocked) never acks: `ISO_ACK_TIMEOUT`
   (255 `core_clk` cycles) lets the PMU proceed and sets `STATUS[3]`.
2. **Slave-side responses are not isolated** (`u_gpu` AXI-Lite `rvalid`, `awready`, ... and `u_cpu` debug
   APB `pready` ...). With a really removed supply they would drive X into the always-on ring.
3. **Scan does not force the clamps off** (table above).
4. `m_axil_if_rready` was the one GPU-to-fabric handshake the RTL did not clamp; clamped as part of `h3lm`.

### Checking

`python3 tools/verif/check_upf.py` (stdlib only, CI gate in `qa-checks.yml`) verifies that every
`-elements` path and control net resolves in the elaborated `soc_top`, that the UPF clamp set equals
the RTL clamp set, that domain membership is explicit and disjoint, and that state names, encodings
and per-mode rail states equal `pmu.sv`. It reads `pnr/constraints/phase5_soc_rtl_facts.json`, which
`check_upf.py gen-facts` generates from `rtl/filelist/soc_top.f` with pyslang for both SRAM arms (ASAP7
and Sky130); `gen-facts --check` is the drift gate. A passing run proves **references and set
equalities, not tool acceptance and not electrical sufficiency of a clamp.**

### Tool compatibility

Measured 2026-10-17 on OpenROAD 26Q2: `read_upf -file` accepts only a small subset (it defines
`create_power_domain`, `set_isolation`, `create_power_switch`, `define_power_switch_cell` and
`map_power_switch`; there is no `upf_version`, `create_supply_*`, `add_power_state`, ...). It fails on
the first command of both the old file (`create_supply_port`) and the new one (`upf_version`). The
file targets full UPF 3.0, so this is a tool-subset limitation and no gate depends on it. No
UPF-aware simulator or linter is available in the open flow.

## Power-Aware Verification

### UPF Simulation Flow

1. **Compile with UPF**: Add UPF file to simulation

   ```bash
   verilator --upf phase2_pipelined_cpu.upf ...
   ```

2. **Apply power sequences**: Use testbench to control power supplies

   ```python
   # Example: cocotb power sequence
   await power_ctrl.power_down_core()  # ACTIVE → SLEEP
   await Timer(100, units='us')
   await power_ctrl.power_up_core()    # SLEEP → ACTIVE
   ```

3. **Check isolation**: Verify no X propagation during power-down

   ```python
   assert dut.axi_arvalid.value != "x", "Isolation failed!"
   ```

4. **Check retention**: Verify state preserved after power cycle

   ```python
   pc_before = dut.i_rv32i_core.pc_reg.value
   await power_cycle()
   pc_after = dut.i_rv32i_core.pc_reg.value
   assert pc_before == pc_after, "Retention failed!"
   ```

### UPF Testbench Structure

```python
# cocotb testbench with UPF support

import cocotb
from cocotb.triggers import Timer, RisingEdge

@cocotb.test()
async def test_power_down_core(dut):
    """Test core power-down and isolation"""

    # Initialize
    await reset_sequence(dut)

    # Run some instructions
    await run_instructions(dut, count=100)

    # Save PC value
    pc_before = dut.i_rv32i_core.pc_reg.value

    # Power down core
    dut.VDD_CORE.value = 0
    await Timer(1, units='us')

    # Check isolation (outputs should be clamped)
    assert dut.commit_valid.value == 0, "Isolation failed"

    # Power up core
    dut.VDD_CORE.value = 1
    await Timer(1, units='us')

    # Check retention (PC should be preserved)
    pc_after = dut.i_rv32i_core.pc_reg.value
    assert pc_before == pc_after, "Retention failed"

    # Resume execution
    await run_instructions(dut, count=100)
```

## UPF Best Practices

1. **Start simple**: Phase 1 has single domain, add complexity incrementally
2. **Isolate everything**: Always add isolation at domain boundaries
3. **Retain critical state**: PC, control registers, cache tags
4. **Test extensively**: Power-aware simulation catches 90% of UPF bugs
5. **Document power modes**: Clear PST with mode descriptions
6. **Use standard cells**: Isolation, retention, level shifter cells from PDK

## AI/Human Responsibilities

### AI MAY assist with

- UPF template generation (domains, supplies, boilerplate)
- Basic isolation and retention declarations
- Power state definitions
- Testbench power control sequences

### AI MUST NOT decide

- Number and boundaries of power domains
- Isolation clamp values (0 vs 1)
- Retention strategy (what to retain)
- Power state transitions
- Voltage levels for DVFS

### Human MUST review

- All UPF power intent files
- Power domain architecture
- Isolation and retention strategies
- Power state tables
- Power-aware simulation results

## References

- IEEE 1801-2015: UPF 3.0 Specification
- Accellera UPF Guide: https://www.accellera.org/downloads/standards/upf
- OpenROAD Power Analysis: https://openroad.readthedocs.io/en/latest/main/src/pdn/README.html
- Verilator UPF Support: https://verilator.org/guide/latest/extensions.html
