# Architecture Knowledge Base — RV32I Pipeline CPU

## Design Identity
- Design: rv32i_cpu_top (RV32I 5-stage in-order pipeline, Phase 2/3)
- Technology: ASAP7 7nm predictive PDK (asap7sc7p5t_SIMPLE RVT TT 0.7V 25C)
- Achieved fmax: ~462 MHz (ASAP7 run 4, 2026-04-25)
- SDC target: 1.0 ns (1000 MHz); WNS at that constraint: ~-1165 ps

## Critical Path Anatomy (EX stage)

The worst setup path runs through the EX stage combinational block (rv32i_pipeline_ex.sv).
The full chain is:

  [ID/EX register] -> fwd_rs1 mux (~2L) -> ALU src_a mux (~2L) -> ALU adder (~8L)
  -> alu_result[1:0] -> misaligned_load/store detection (~2L)
  -> trap priority encoder (8-condition if-else, ~8-10L)
  -> ex_pc_redirect_o -> hazard_unit (~3-4L) -> flush_if_id / flush_id_ex

Estimated total: ~25-27 logic levels at ~15 ps/level = ~375-405 ps combinational.
With FF setup (~20 ps), clock uncertainty (~20 ps), source latency (~50 ps):
effective critical path ~465-495 ps -> fmax ~500-540 MHz theoretical ceiling before retiming.

## Key Structural Facts

1. All trap flag inputs to EX (illegal, ebreak, mret, fence_i) are REGISTERED
   in the ID/EX register. They do not add fanin depth to the EX chain.

2. irq_valid_i is COMBINATIONAL from interrupt_ctrl. However, ext_irq_i and
   timer_irq_i are already declared false_path in asap7.sdc. The residual
   constrained path is [mstatus_mie_eff FF] -> interrupt_ctrl AND -> irq_valid_i
   -> EX chain. This path is ~2-3 levels deep (shallow relative to the bottleneck).

3. The real bottleneck is: ALU adder -> alu_result[1:0] -> misaligned detection
   -> trap priority chain. This is the ONLY path where a deeply computed EX signal
   (alu_result) feeds back into the redirect decision combinationally.

4. JALR address (alu_result[31:1]) also feeds redirect_target — but redirect_target
   is NOT on the critical path (WNS is dominated by the do_redirect signal, not
   the target value).

5. The hazard unit is purely combinational and adds ~3-4 levels after ex_pc_redirect_o.
   Its outputs fan out to all four pipeline registers.

## Retiming Option Summary

### Option A: Split EX into EX1 + EX2
- Verdict: Architecturally valid
- CPI delta: +0.16 (11% degradation) at 20% branch freq, 70% taken, 2% JALR
- Estimated frequency gain: +150 ps saved -> ~513 MHz achievable fmax
- Net throughput: neutral (frequency gain offsets CPI penalty)
- Risk: Medium — 6-stage pipeline changes hazard interactions; re-verify forwarding
- Recommended: YES as the primary RTL retiming option

### Option B: Move misaligned detection to MEM stage
- Verdict: Architecturally valid (misalign trap penalty increases from 2 to 3 cycles)
- CPI delta: negligible (misaligned access frequency ~0.1% of instructions)
- Estimated frequency gain: +35-50 ps saved -> ~470-480 MHz fmax
- Risk: Low — isolated change to EX and MEM stages
- Recommended: YES as a prerequisite or companion to Option A
- Note: Breaks alu_result -> trap_chain dependency, which is the root cause of the bottleneck

### Option C: Register hazard unit outputs
- Verdict: ARCHITECTURALLY INVALID — load-use stall and branch flush both arrive
  1 cycle late, corrupting pipeline state (wrong register read, extra instruction
  executed past branch). Cannot be fixed without fundamental redesign.
- Recommended: NO

### Option D: SDC multicycle path exceptions
- Verdict: Valid with constraints — limited actual benefit
- The two raw IRQ pins are ALREADY false_path. Remaining action: add multicycle 2
  from mstatus_mie_eff FF to EX trap chain (legitimate per RISC-V spec: no
  single-cycle IRQ delivery requirement).
- Estimated frequency gain: +20-30 ps -> marginal
- Risk: Low (SDC-only change, no RTL modification)
- Recommended: YES as a low-cost supplement, but not as a standalone fix

## Recommended Implementation Order
1. Option D (SDC only, zero RTL risk) — apply immediately
2. Option B (move misaligned detection to MEM) — low-risk RTL change, breaks
   the alu_result -> chain dependency
3. Option A (EX1+EX2 split) — primary frequency gain, apply after B is verified

## Expected Combined Outcome
- Option D alone: +20-30 ps -> ~465-470 MHz
- Options D+B:    +55-80 ps -> ~480-490 MHz
- Options D+B+A:  +200-230 ps -> ~540-560 MHz (accounting for synthesis variation)
- CPI impact of A: +0.16 CPI units -> net throughput roughly neutral vs baseline

## PDK Notes (ASAP7)
- Cell delay: ~15 ps/level (INV, NAND2, NOR2)
- FF setup: ~20 ps; FF hold: ~10 ps
- Clock jitter: ~10 ps (synthesized PLL environment)
- SRAM black-boxed: no timing arcs from SRAM; critical path is pure std-cell logic
- asap7.sdc: 1.0 ns target, IO budget 15% (150 ps), APB multicycle 2 already applied
