# Design Expectation

## CPU

Start with simple micro-processor based on RV32I architecture

- Single-issue
- In-order
- No pipeline (or 2-stage max)
- Blocking loads/stores

Once that is done, use it as a foundation to develop a pipelined CPU

- 5-stage pipeline
- No speculation
- Static hazard handling

Develop the memory system and caches once the pipelined CPU design is completed

- I-cache + D-cache
- Write-back but no coherence
- Basic interface (As detailed in RTL_DEFINITION.md)

Future work

- Support speculation via branch target predictor
- Support ECC single-error detect (Move on to SECDED later on)
- Support direct memory access via MEM protocol
- Support coherent write-back
- Plan for multi-CPU design and cluster-based with L2 cache support

## GPU

Keep GPU design feasible with basic blocks

- Single compute unit
- SIMD/SIMT lanes
- No graphics
- No preemption
- No out-of-order
- No dynamic scheduling

Future work

- Support multiple compute units
- Support graphics
- Support preemption
- Support out-of-order
- Support dynamic scheduling

## SoC

Create basic SoC structure with following components

- CPU
- GPU
- Interconnect
- DMA (Implement AXI + APB interfaces)
  - AXI as main communication protocol
  - APB as config register read/write protocol
- UART, SPI, Timer
- Boot ROM
