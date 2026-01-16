# RTL Definition

## IP Interface

### CPU IP

Basic interface:

- AXI protocol for communication with SoC bus
- APB protocol for CPU config register access (Read/Write)
- Interrupt support (Timer & external)
- Debug trace information (PC, instruction & valid output)
- Input clock and active-low reset

### GPU IP

Basic interface:

- AXI protocol for communication with SoC bus
- APB protocol for GPU config register access (Read/Write)
- Interrupt support (Output to CPU)

### SoC

Basic interface:

- AXI protocol for communication with CPU & GPU IPs
- AXI protocol to communicate with external
- APB protocol to config CPU & GPU config register
- APB protocol to communicate with external
- Interrupt support (Output to CPU - Timer & external)
- TBD

### TOP

Basic interface:

- AXI protocol to communicate with SoC
- APB protocol to communicate with SoC
- Interrupt support (Send external interrupt to CPU)
