# Debug Interface (Phase 1+)

The APB3 debug interface provides the following registers:

| Address | Register | Description |
| :------ | :------- | :---------- |
| 0x000 | DBG_CTRL | Control: [0]=halt, [1]=resume, [2]=step, [3]=reset |
| 0x004 | DBG_STATUS | Status: [0]=halted, [1]=running, [7:4]=halt_cause |
| 0x008 | DBG_PC | Program Counter |
| 0x00C | DBG_INSTR | Current instruction |
| 0x010-0x08C | DBG_GPR[0:31] | General purpose registers |
| 0x100 | DBG_BP0_ADDR | Breakpoint 0 address |
| 0x104 | DBG_BP0_CTRL | Breakpoint 0 control: [0]=enable |
| 0x108 | DBG_BP1_ADDR | Breakpoint 1 address |
| 0x10C | DBG_BP1_CTRL | Breakpoint 1 control: [0]=enable |

See [`docs/design/MEMORY_MAP.md`](../design/MEMORY_MAP.md) for complete register definitions.
