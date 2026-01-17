# RTL Interface Definitions

System-level interface specifications for all IPs

Document status: Frozen
Last updated: 2026-01-17

## Protocol Standards

This project uses industry-standard AMBA protocols:

- **AXI4-Lite**: AMBA AXI4-Lite Protocol Specification (ARM IHI 0022E)
- **APB3**: AMBA APB Protocol Specification v2.0 (ARM IHI 0024C)

## CPU IP Interface

### Phase 1 (Single-Cycle CPU)

**Top-level module**: `rv32i_cpu_top`

#### Clock and reset

```systemverilog
input  logic        clk,        // System clock
input  logic        rst_n,      // Active-low synchronous reset
```

**Requirements**:

- Single clock domain
- Synchronous reset sampled on rising edge of clk
- Reset behavior per PHASE0_ARCHITECTURE_SPEC.md

#### AXI4-Lite master (memory interface)

**Purpose**: Unified instruction fetch and data access

**Configuration**:

- Protocol: AXI4-Lite (no burst, no lock, no cache)
- Address width: 32 bits
- Data width: 32 bits
- ID width: Not used (AXI-Lite)
- Outstanding transactions: 1 (no pipelining in Phase 1)

**Signals**:

```systemverilog
// Write address channel
output logic [31:0] axi_awaddr,     // Write address
output logic        axi_awvalid,    // Write address valid
input  logic        axi_awready,    // Write address ready

// Write data channel
output logic [31:0] axi_wdata,      // Write data
output logic [3:0]  axi_wstrb,      // Write strobes (byte enables)
output logic        axi_wvalid,     // Write data valid
input  logic        axi_wready,     // Write data ready

// Write response channel
input  logic [1:0]  axi_bresp,      // Write response (00=OKAY, 10=SLVERR)
input  logic        axi_bvalid,     // Write response valid
output logic        axi_bready,     // Write response ready

// Read address channel
output logic [31:0] axi_araddr,     // Read address
output logic        axi_arvalid,    // Read address valid
input  logic        axi_arready,    // Read address ready

// Read data channel
input  logic [31:0] axi_rdata,      // Read data
input  logic [1:0]  axi_rresp,      // Read response (00=OKAY, 10=SLVERR)
input  logic        axi_rvalid,     // Read data valid
output logic        axi_rready,     // Read data ready
```

**Behavior**:

- Address phase completes when `VALID && READY`
- Data phase completes when `VALID && READY`
- CPU must not issue new transaction until previous completes
- `axi_rresp` or `axi_bresp` != OKAY triggers illegal instruction trap

**AXI4-Lite response encoding**:

- `2'b00`: OKAY - Normal access success
- `2'b01`: EXOKAY - Not used (reserved)
- `2'b10`: SLVERR - Slave error (triggers trap in CPU)
- `2'b11`: DECERR - Decode error (triggers trap in CPU)

**Write strobe encoding**:

- `wstrb[0]`: Byte lane [7:0] valid
- `wstrb[1]`: Byte lane [15:8] valid
- `wstrb[2]`: Byte lane [23:16] valid
- `wstrb[3]`: Byte lane [31:24] valid

#### APB3 slave (debug interface)

**Purpose**: Debug register access (halt, resume, step, breakpoints, register inspection)

**Configuration**:

- Protocol: APB3 (with PREADY support)
- Address width: 12 bits (4KB space)
- Data width: 32 bits
- Base address: Configurable (SoC integration determines base)

**Signals**:

```systemverilog
input  logic [11:0] apb_paddr,      // APB address (byte-aligned)
input  logic        apb_psel,       // APB select
input  logic        apb_penable,    // APB enable
input  logic        apb_pwrite,     // APB write (1=write, 0=read)
input  logic [31:0] apb_pwdata,     // APB write data
output logic [31:0] apb_prdata,     // APB read data
output logic        apb_pready,     // APB ready (completes transfer)
output logic        apb_pslverr,    // APB slave error
```

**Protocol timing**:

```text
IDLE → SETUP (psel=1, penable=0) → ACCESS (psel=1, penable=1, pready=1) → IDLE
```

**Address map**: See MEMORY_MAP.md for complete register definitions

**Access restrictions**:

- Registers writable only when CPU halted (except control bits)
- Reads always allowed
- Out-of-range addresses return `pslverr=1`

#### Commit interface (verification observability)

**Purpose**: Signals for testbench scoreboard to verify correctness

**Signals**:

```systemverilog
output logic        commit_valid,   // Instruction committed this cycle
output logic [31:0] commit_pc,      // PC of committed instruction
output logic [31:0] commit_insn,    // Instruction word
output logic        trap_taken,     // Trap occurred this cycle
output logic [3:0]  trap_cause,     // Trap cause encoding
```

**Usage**:

- Testbench monitors these signals
- Scoreboard compares with Python reference model
- Not used in silicon (optional for synthesis)

### Phase 2+ Extensions

**Planned additions**:

- Interrupt request input (`irq`)
- Interrupt acknowledge output (`irq_ack`)
- External debug request (`dbg_req`)
- Performance counter outputs

**Note**: Interrupts NOT supported in Phase 1

## GPU IP Interface

### Phase 4 (GPU-Lite Compute Engine)

**Top-level module**: `gpu_compute_top`

#### Clock and reset

```systemverilog
input  logic        clk,            // System clock
input  logic        rst_n,          // Active-low synchronous reset
```

#### AXI4-Lite master (memory interface)

**Purpose**: Global memory access for GPU kernels

**Configuration**:

- Protocol: AXI4-Lite
- Address width: 32 bits
- Data width: 32 bits (may extend to 64/128 in later phases)
- Outstanding transactions: 1 (Phase 4), N (future)

**Signals**: Same as CPU AXI4-Lite master (see above)

**Behavior**:

- Memory coalescing when possible (multiple lanes → single transaction)
- Serialized access when lanes access different addresses
- No coherence with CPU in Phase 4

#### APB3 slave (control/config interface)

**Purpose**: GPU kernel launch, status, configuration

**Configuration**:

- Protocol: APB3
- Address width: 12 bits (4KB space)
- Data width: 32 bits

**Signals**: Same as CPU APB3 slave (see above)

**Key registers** (see MEMORY_MAP.md for details):

- GPU_CTRL: Launch kernel, reset
- GPU_STATUS: Idle, running, done
- GPU_KERNEL_ADDR: Kernel instruction start address
- GPU_GRID_DIM: Grid dimensions
- GPU_BLOCK_DIM: Block dimensions
- GPU_WARP_SIZE: Warp size configuration

#### Interrupt output

**Purpose**: Notify CPU when kernel completes

**Signals**:

```systemverilog
output logic        gpu_irq,        // Interrupt request to CPU
```

**Behavior**:

- Asserts when kernel completes
- Cleared when CPU reads GPU_STATUS or writes GPU_CTRL

**Note**: Phase 1-3 CPU does not support interrupts. Integration requires Phase 2+ CPU.

### Phase 4+ Extensions

**Planned additions**:

- Multiple compute units
- Wider AXI data width (128/256 bits)
- Shared local memory interface
- Texture/constant cache interfaces

## SoC Integration Interface

### Phase 5 (SoC Top-Level)

**Top-level module**: `soc_top`

#### External memory interface (AXI4-Lite master)

**Purpose**: Off-chip memory or memory controller

**Configuration**:

- Protocol: AXI4-Lite
- Address width: 32 bits
- Data width: 32 bits
- Aggregates CPU + GPU memory requests

**Signals**: Standard AXI4-Lite master interface

#### External APB interface (APB3 master)

**Purpose**: External peripherals (UART, SPI, Timer)

**Configuration**:

- Protocol: APB3
- Address width: 32 bits (full SoC address space)
- Data width: 32 bits

**Signals**: Standard APB3 master interface

#### External interrupts

**Purpose**: External devices signal CPU

**Signals**:

```systemverilog
input  logic        ext_irq,        // External interrupt request
input  logic        timer_irq,      // Timer interrupt request
```

**Note**: Requires Phase 2+ CPU with interrupt support

#### Boot configuration

**Purpose**: Select boot mode, clock configuration

**Signals**:

```systemverilog
input  logic [31:0] boot_addr,      // Boot address override
input  logic        boot_sel,       // 0=ROM, 1=external
```

### Phase 5+ Extensions

**Planned additions**:

- Multi-core support (CPU clusters)
- L2 cache interface
- DMA engine interface
- Power management (clock gating, power domains)

## Peripheral IP Interfaces

### UART (Phase 5)

**Protocol**: APB3 slave
**Registers**: TX_DATA, RX_DATA, STATUS, CTRL, BAUD_DIV
**Interrupts**: TX_DONE, RX_READY

### SPI Master (Phase 5)

**Protocol**: APB3 slave
**Registers**: TX_DATA, RX_DATA, STATUS, CTRL, CLK_DIV, CS_CTRL
**Interrupts**: TRANSFER_DONE

### Timer (Phase 5)

**Protocol**: APB3 slave
**Registers**: COUNTER, COMPARE, CTRL, PRESCALER
**Interrupts**: TIMER_MATCH

## Interface Protocol Compliance

### AXI4-Lite compliance checklist

- [ ] Address/data widths match specification
- [ ] Handshake protocol (VALID/READY) implemented correctly
- [ ] Only one outstanding transaction at a time (Phase 1 requirement)
- [ ] No unsupported signals driven (AWID, ARID, etc.)
- [ ] Response codes handled correctly
- [ ] Write strobe alignment correct

### APB3 compliance checklist

- [ ] SETUP → ACCESS state transition correct
- [ ] PREADY can extend ACCESS phase
- [ ] PSLVERR handled for invalid addresses
- [ ] No combinational paths from PSEL to outputs
- [ ] Register addresses aligned to 32-bit boundaries

## Testing Requirements

All interfaces must be verified with:

1. Protocol compliance checkers (SVA or cocotb monitors)
2. Back-pressure testing (randomized READY deassertion)
3. Error injection (SLVERR, DECERR responses)
4. Corner cases (address boundaries, alignment)

## References

- ARM IHI 0022E: AMBA AXI4-Lite Protocol Specification
- ARM IHI 0024C: AMBA APB Protocol Specification v2.0
- PHASE1_ARCHITECTURE_SPEC.md: CPU implementation details
- PHASE4_GPU_ARCHITECTURE_SPEC.md: GPU implementation details
- MEMORY_MAP.md: Complete register address map
