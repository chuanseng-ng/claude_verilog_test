# GPU Execution Model

**Feasible by design**

## Design goals

❌ No:

- Cache coherence
- Preemption
- Out-of-order
- Dynamic scheduling

✅ Yes:

- SIMT-like execution
- Deterministic behavior
- CPU-managed launches

## Execution model (Simple but real)

Key concepts

- Grid → Blocks → Warps
- Fixed warp size (e.g. 8 or 16 lanes)
- Single instruction per warp

Control

- One Warp Scheduler
- Round-robin warp issue
- No scoreboarding across warps

## Pipeline (GPU core)

```text
Fetch → Decode → Execute → Memory → Writeback
```

- Shared instruction per wrap
- Per-lane register files
- Mask register for divergence

## Divergence handling

```text
if (cond) {
  A;
} else {
  B;
}
```

Implemented via:

- Per-lane predicate mask
- Serial execution of paths
- Mask restore

🚫 No reconvergence stacks beyond 1 level initially

## Memory model

- Global memory only
- Coalesced access when lanes hit same cache line
- Otherwise serialized

## AI vs Human scope

| Component     | AI  | Human  |
| :-----------: | :-: | :----: |
| Vector ALU    | ✅  | Review |
| Warp FSM      | ⚠️  | ✅     |
| Divergence    | ❌  | ✅     |
| Kernel launch | ⚠️  | ✅     |
| Test kernels  | ✅  | Review |

## GPU verification (Python)

Reference kernel execution

```python
def execute_kernel(kernel, data):
    for warp in warps:
        for pc in kernel:
            execute_instruction(pc, warp)
```

Scoreboard compares:

- Memory outputs
- Per-lane registers
