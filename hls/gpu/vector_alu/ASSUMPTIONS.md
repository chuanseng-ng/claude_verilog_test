# `vector_alu.c` — assumptions made where the spec was silent

GH #119 "NL → C → RTL" pilot, block 3 (GPU arm, arithmetic-heavy). This file is a **measured
output of the experiment**, not paperwork: it records every point at which the natural-language
specification did not determine the implementation, and what was chosen instead.

The spec I was given is reproduced at the top of `vector_alu.c`. **I did not read
`rtl/gpu/vector_alu.sv`, `rtl/gpu/gpu_pkg.sv`, or anything else under `rtl/`.**

Confidence ratings below are my honest estimate of the probability that the choice matches the
hand-written reference, not a measurement.

---

## Summary table

| # | Question the spec left open | Choice | Confidence |
| :- | :-------------------------- | :----- | :--------- |
| 1 | `imm` incoming form | Idempotent sign-extend from bit 11 | medium-high |
| 2 | Upper bits of the 32-bit `opcode` word | Masked to 7 bits, ignored | high |
| 3 | Shift-amount width | `rs2[4:0]`, 5 bits | high |
| 4 | Role of `funct3` / `funct7` | Not decoded at all | high |
| 5 | VMUL signedness / width | 32×32→32 unsigned (= low half either way) | high |
| 6 | `VSRA` vs `VSRL` | VSRA arithmetic (signed), VSRL/VSLL logical | high |
| 7 | `result_o` for VLD/VST/VLDS/VSTS | `rs1 + sign_ext(imm)` — effective address | medium-high |
| 8 | `result_o` for VBEQ/VBNE/VBLT/VBGE | 0 | medium |
| 9 | `result_o` / `branch_taken_o` for VJMP/VRET/VSYNC | both 0 | medium-high |
| 10 | `result_o` for VMOV_TID_* / VMOV_BID_* | 0 | **low-medium** ← main risk |
| 11 | `branch_taken_o` for every non-branch opcode | 0 | high |
| 12 | Unrecognised / undefined opcode | both outputs 0 | medium-high |
| 13 | `VBLT` / `VBGE` signedness | signed | high |
| 14 | Upper bits of `active_mask` | ignored | high |
| 15 | Mask applied to result, or to operands | to the outputs | high |

---

## 1. `imm` handling — the spec contradicts itself

The interface declares `logic [11:0] imm_i` — 12 bits — and the comment on the same line says
*"sign-extended by caller"*. A 12-bit port cannot hold a sign-extended 32-bit value, so exactly one
of the two statements has to be reinterpreted. Bambu's C interface hands us a 32-bit word either
way, which is what makes a reconciliation possible.

**Chosen:** sign-extend from bit 11, *idempotently*:

```c
#define SIGN_EXTEND_12(v) ( ((v) & 0x800u) ? ((v) | 0xFFFFF000u) : ((v) & 0xFFFu) )
```

This agrees with **both** readings for every legal input:

* caller drove a raw 12-bit field (bits 31:12 zero) → we perform the extension the value needs;
* caller already sign-extended to 32 bits → bits 31:11 are by definition all copies of bit 11, so
  the expression reproduces its input **unchanged**.

Verified natively: `VADDI rs1=10, imm=0x00000FFF` and `VADDI rs1=10, imm=0xFFFFFFFF` both give 9.
The two readings can only diverge on a word that is neither — junk in bits 31:12 not matching bit
11 — which is illegal under either reading.

**Residual risk:** if the reference RTL *zero*-extends its 12-bit port (which is what SystemVerilog
does by default when an unsigned `logic [11:0]` is widened into a 32-bit expression, unless it is
written `$signed(imm_i)` or `{{20{imm_i[11]}}, imm_i}`), then every **negative** immediate will
differ by 0x1000. That is a real possibility, and it is the single most likely functional mismatch
in this file after item 10. Note the mismatch would be a *bug in the reference*, not in this C —
the spec's own comment says the value is sign-extended — but a mismatch is a mismatch.
**Confidence: medium-high** that this matches; **high** that it matches the spec as written.

## 2. Opcode word width

`gpu_opcode_t` is stated to be 7-bit; the C parameter is a 32-bit word. Bits [31:7] are **masked
off and ignored**, not treated as an error. There is no fault or status channel on this interface
on which an illegal opcode could be reported, and a shim that leaves junk in the upper bits must
still behave. This mirrors the identical choice for register addresses in the previous pilot block
(`rv32i_hazard_unit.c`, its ASSUMPTION 1). Verified natively: opcode `0x81` behaves as `0x01`
(VADD). **Confidence: high** — with a 7-bit port on the RTL side the question does not even arise
there, so any 7-bit-equivalent behaviour matches.

## 3. Shift-amount width — 5 bits, from `rs2`

The spec says only *"this is an RV32I-derived vector ISA, so the standard RV32I meanings apply"*.
RV32I's `SLL`/`SRL`/`SRA` use `rs2[4:0]` and ignore `rs2[31:5]`; a shift by ≥ 32 is not
representable. So `shamt = rs2 & 0x1F`.

This is also the only choice that is *well defined in C at all*: shifting a 32-bit value by ≥ 32 is
undefined behaviour, so an unmasked shift would make the C source meaningless rather than merely
mismatched. Verified natively: `VSLL 1 << 33` gives 2 (i.e. `<< 1`).

Note the ISA table has **no shift-immediate opcode** — there is no VSLLI/VSRLI/VSRAI — so the shift
amount always comes from `rs2`, never from `imm`. **Confidence: high.**

## 4. `funct3` / `funct7` are decoded by nothing

The spec labels both *"reserved for future R-type sub-encoding"*, and every currently-defined
operation already has a unique primary opcode (VADD 0x01 … VSRA 0x09 are nine distinct opcodes, not
one opcode with nine funct3 values). There is therefore no sub-decode to perform, and both inputs
are `(void)`-cast so the source says "deliberately unused" rather than "forgotten".

**Measured:** Bambu **kept both ports** — `input [31:0] funct3;` and `input [31:0] funct7;` appear
in the generated top module even though nothing reads them. This was not a given: a tool that can
prove an input is unused is entitled to delete the port, which would have silently broken the
drop-in interface. It did not. **Confidence: high.**

## 5. VMUL — 32×32→32, signedness irrelevant

The spec: *"VMUL produces the lower 32 bits of the 64-bit product (no pipeline stage in Phase 4)."*
It does not say whether the operands are signed. It does not have to: **the low 32 bits of a 32×32
product are identical for signed and unsigned multiplication.** Writing it as `unsigned * unsigned`
(C unsigned arithmetic is modulo 2³², so the result *is* exactly the low half) also asks the tool
for a 32×32→32 multiplier rather than a 32×32→64 one whose upper half is then discarded.

Verified natively: `0x10000001 * 0x10 = 0x1_00000010` → result `0x00000010`. **Confidence: high.**

The parenthetical *"no pipeline stage in Phase 4"* is a statement about the reference RTL that this
C **cannot honour**, and Bambu did not honour it either — see the QoR section below.

## 6 / 13. Signed vs unsigned semantics — the explicit question

Two independent places where the spec's *"standard RV32I meanings apply"* is doing all the work:

* **`VSRA` (0x09) vs `VSRL` (0x08).** The whole reason both opcodes exist is that one is
  arithmetic and one is logical. `VSRL`/`VSLL` operate on the unsigned copy (vacated bits are 0);
  `VSRA` operates on the signed copy (vacated bits replicate the sign). Verified natively:
  `VSRA 0x80000000 >> 4 = 0xF8000000`, `VSRL 0x80000000 >> 4 = 0x08000000`.
* **`VBLT` (0x32) / `VBGE` (0x33).** RV32I's `BLT`/`BGE` are **signed** comparisons; the unsigned
  forms are *separate* opcodes (`BLTU`/`BGEU`) which this ISA does not define at all. Their absence
  from the table is itself the evidence: if VBLT were unsigned there would be no way to express a
  signed compare, which an RV32I-derived ISA would not do. Verified natively:
  `VBLT(-1, 1) = 1`, `VBLT(1, -1) = 0`, `VBGE(-1, 1) = 0`.

**Confidence: high** on both. `VADD`/`VSUB`/`VMUL` need no signedness decision (two's-complement
wraparound is identical); the bitwise ops obviously need none.

Sub-assumption (6a): C99 leaves `>>` on a **negative `int`** implementation-defined rather than
guaranteed-arithmetic. clang-16 — which is Bambu's front end here, pinned by
`--compiler=I386_CLANG16` — defines it as an arithmetic shift, and Bambu lowered it to a signed
right-shift operator. Written as `(unsigned)((int)a >> sh)` rather than as a hand-built sign-fill
so the tool infers its own ASR rather than a mask-and-OR tree.

## 7. `result_o` for memory opcodes = the effective address

The spec is **silent** on what this block does for `VLD`/`VST`/`VLDS`/`VSTS`. Chosen:
`result = rs1 + sign_ext(imm)` for all four, global and shared alike.

Three reasons, in increasing order of weight:

1. They are declared **I-type**, and in RV32I the I-type load/store address is exactly
   `rs1 + sign_ext(imm)` — which is what "the standard RV32I meanings apply" imports.
2. The interface hands this block precisely the two operands an address computation needs and
   nothing else, and no other per-lane input exists that they could be for.
3. **The downstream memory coalescer consumes eight per-lane byte addresses** (block 1 of this
   pilot: `a0..a7`), and the vector ALU is the only per-lane adder in the GPU datapath that can
   produce them. Returning 0 here would leave the coalescer with no address source.

Store *data* is `rs2` and is routed around this block, so `VST`/`VSTS` still emit the address, not
the data. Verified natively: `VLD rs1=0x1000, imm=0xFFC (= −4)` → `0x00000FFC`.
**Confidence: medium-high.** The failure mode if wrong is that the reference returns 0 and the
address adder lives in a separate address-generation unit.

## 8. `result_o` for branch opcodes = 0

The branch **target** cannot be computed here: RV32I branch targets are PC-relative and **no PC is
an input to this block**. So the only thing `result_o` could carry for a branch is some by-product
of the comparison. 0 is the one default value the spec actually states anywhere (*"inactive lanes
produce 0 on result_o and branch_taken_o"*), so it is reused rather than inventing a second one.

**Confidence: medium.** A plausible alternative is that the reference leaves `result_o` at whatever
the shared adder/comparator produced (e.g. `rs1 − rs2`) because a combinational ALU has no reason
to spend a mux forcing it to zero. That would still be functionally irrelevant — nothing consumes
`result_o` for a branch, because a branch writes no destination register — but it would be a
bit-level mismatch on a co-simulation that checks all outputs unconditionally. If an equivalence
run fails only on branch opcodes and only on `result_o`, this is the line to change.

## 9. `result_o` and `branch_taken_o` for VJMP / VRET / VSYNC = 0

`VJMP` and `VRET` are unconditional control transfers resolved by the warp scheduler / SIMT stack;
`VSYNC` is a scheduler barrier. None writes a destination register, and none is a per-lane
predicate, so neither output is meaningful.

`branch_taken_o` is deliberately **not** forced to 1 for `VJMP`, even though a jump is
unconditionally "taken". The port is named *"per-lane branch decision"* — a predicate for a
*conditional* branch. A `VJMP` needs no per-lane predicate (it is uniform across the warp by
construction), and asserting 8 taken bits for it would make the divergence stack believe a
divergence had occurred. **Confidence: medium-high**; the `VJMP` reading is the one I would check
first if divergence behaviour misbehaves.

## 10. VMOV_TID_* / VMOV_BID_* = 0 — the main risk in this file

**This block has no `tid` and no `bid` input.** It is physically incapable of producing a thread or
block id, so those values must be injected upstream (operand fetch pre-loading the id into the
`rs1` operand) or bypassed around the ALU entirely by a mux in the writeback path. Emitting 0 is
the honest expression of "this block does not have that information".

**The plausible alternative is `result = rs1` (pass-through)**, on the theory that operand fetch
pre-loads the id into `rs1` and the ALU is expected to forward it — which is how a VMOV-shaped
opcode would normally be built into an ALU that already has `rs1` in hand. That is a one-line
change (move the six `VMOV_*` cases from `default:` to a `_r = _a;` case).

**Confidence: low-medium.** Of everything in this file, this is the choice most likely to differ
from the reference, and it is squarely a consequence of the spec listing an opcode class whose
operands are not on the interface it also gave me.

## 11. `branch_taken_o` for every non-branch opcode = 0

Only `VBEQ`/`VBNE`/`VBLT`/`VBGE` write it; everything else leaves it 0. The spec gives
`branch_taken_o` no meaning outside the branch class, and 0 ("not taken") is the safe value for a
divergence stack that samples it every cycle. **Confidence: high** — any other choice would make
non-branch instructions divergence-relevant.

## 12. Unrecognised opcode

Anything not in the table (including the gaps 0x0A–0x10, 0x15–0x1F, 0x24–0x2F, 0x34–0x37,
0x39–0x3E, 0x43–0x45, 0x49–0x4F, 0x51–0x7F) falls to `default:` → `result = 0`,
`branch_taken = 0`. There is no illegal-opcode output port, so a defined constant is the only
available behaviour, and 0 is the value the spec already uses as its "nothing here" encoding.
**Confidence: medium-high** — hand-written RTL usually gives such a `case` a `default: result = '0`
for exactly the same reason (latch avoidance), so the values probably agree.

## 14 / 15. `active_mask` semantics

`active_mask` bit *i* selects lane *i*; bits [31:8] are ignored (the spec says the flags live "in
bits 0..7" and is silent on the rest — ignoring them is the only reading that keeps an 8-lane block
8 lanes wide).

The mask is applied **at the outputs**, not by suppressing the computation:
`res = act ? computed : 0`. In a combinational block there is nothing to "skip", and a mux to 0 is
precisely what the RTL builds. Verified natively: `VBEQ` with `active_mask = 0x05` gives
`branch_taken = 1,0,1,0` on lanes 0–3. **Confidence: high** — this one is stated outright by the
spec, the only freedom being *where* the zeroing happens, which is unobservable.

---

## Structural choices that are not spec ambiguities

**Manual 8× unroll instead of a `for` loop.** The eight lanes are written out explicitly. A loop
would have invited the scheduler to fold them onto one shared ALU across eight control steps, which
is a *different machine* from the one the spec describes. The measurement below confirms the unroll
survived: eight distinct multiplier instances exist, one per lane.

**Macro, not a `static` function, for the per-lane datapath.** Carried over from the previous pilot
block: Bambu 2024.10 answered *"Required never inline for function …"* to a `static` helper in
`rv32i_hazard_unit.c`, turned it into a shared 1-resource submodule, allocated internal memory to
pass its arguments, and then failed the run outright on the ASAP7 clock constraint.
`__attribute__((always_inline))` did not change that. A macro is the only construct that reliably
keeps a combinational block combinational here — and, for this block, the only one that guarantees
eight independent copies of the datapath rather than one sequentially-reused ALU.

---

## Measured QoR (Bambu 2024.10, flags exactly as in `hls/bambu.mk`)

Run in `/nobackup/hls/scratch/authoring_valu`, `--device-name=asap7-TC --clock-period=0.705`.

### Port shape — PASS

Top module `vector_alu` has, besides Bambu's own `clock` / `reset` / `start_port` / `done_port`:
21 plain scalar inputs (`opcode`, `funct3`, `funct7`, `rs1_0..7`, `rs2_0..7`, `imm`,
`active_mask`, all `input [31:0]`) and 16 plain scalar outputs (`result_0..7`,
`branch_taken_0..7`, all `output [31:0]`). **Zero** `_address0` / `_ce0` / `_we0` / `_d0` / `_q0`
ports anywhere in the 1.6 MB generated file. `funct3` and `funct7` survived despite being unread.

### Multipliers — 8 instances, no sharing, no DSP, 1 pipeline register each

Eight distinct `ui_mult_expr_FU` instances (`…_435_i0` … `…_435_i7`), each fed directly from
`in_port_rs1_N` / `in_port_rs2_N` and selected afterwards by a `MUX_GATE`. **They were not shared**
— the manual unroll held.

`Estimated number of DSPs: 0`, and no `DSP48`/`dsp_` string occurs in the output. This is correct
rather than a failure: the target is an **ASIC** device model (`asap7-TC`), which has no DSP hard
blocks, so the multiplier is emitted as a behavioural `assign mult_res = in1_in * in2_in;` for the
downstream RTL synthesiser (Yosys/ABC) to build from standard cells.

Each is instantiated with `PIPE_PARAMETER(1)`, i.e. **a registered-output multiplier** — Bambu
reported `No functional unit exists for the given clock period: the fastest pipelined unit will be
used (ui_mult_expr_FU): 1.18994` ns. **This directly violates the spec's "no pipeline stage in
Phase 4"**, and the C source cannot prevent it: 1.19 ns of multiplier simply does not fit in a
0.705 ns clock, so the tool inserts the stage the spec forbids.

### The 0.705 ns clock does not admit a combinational ALU

Bambu's ASAP7 delay model puts a 32-bit **adder** at 0.85016 ns and a 32-bit **subtractor** at
0.77230 ns — both longer than the 0.705 ns period. It emitted 32 warnings ("the fastest unit will
be used as **multi-cycle** unit": 24 adders — three per lane, for VADD, VADDI and the memory
address — plus 8 subtractors) before reaching the multiplier. So at this clock target *every*
arithmetic operation in the block is multi-cycle, and the spec's "all operations are single-cycle
combinational" is unreachable by construction, independent of how the C is written.

### Headline numbers (pinned flags, 0.705 ns)

| Metric | Value |
| :----- | :---- |
| FSM states | **81** |
| Control steps (scheduling) | 66 |
| Latency | **11 cycles min, 21 cycles max** (data-dependent) |
| Flip-flops | **6 014** |
| Registers (after binding) | 284 (lower bound 146 — Bambu flagged its own result sub-optimal) |
| Modules instantiated | 678 |
| 2-to-1 mux equivalents | 350 |
| Total estimated area (Bambu units) | **1 298 853** |
| Estimated DSPs | 0 |
| Minimum slack | met |
| Estimated max frequency | 1418.44 MHz (= 1 / 0.705 ns — met by construction, via multi-cycling) |
| Bambu exit status | 0 |

### Two companion runs, because the headline number invites a wrong conclusion

The obvious story — "the 0.705 ns target forced the FSM" — is **wrong**, and one extra run shows
it. Both companions used identical flags except where noted.

**(a) Same C, `--clock-period=1.75`** (the GPU domain's real 571 MHz period, where a 0.85 ns adder
fits comfortably):

| | 0.705 ns | 1.75 ns |
| :- | :- | :- |
| multi-cycle warnings | 32 | **0** |
| FSM states | 81 | **62** |
| latency (cycles) | 11–21 | **9–11** |
| flip-flops | 6 014 | **6 012** |
| total estimated area | 1 298 853 | **1 298 853** (identical) |

Removing every multi-cycle unit removed **2 flip-flops** and changed the area estimate by nothing.
The block is still a 62-state, 9-to-11-cycle machine. **The clock target is not the cause** — it
accounts only for the 11→9 shortening and the 81→62 state count. The FSM is Bambu's structural
answer to this block, not a timing artefact.

**(b) A data-flow rewrite of the same function, 0.705 ns.** To test whether the `switch` was the
culprit, the per-lane `switch` was mechanically replaced by a chain of ternary selects computing
every candidate result and selecting one — the textbook "give HLS a mux, not control flow"
transformation:

| | `switch` (shipped) | ternary chain |
| :- | :- | :- |
| FSM states | **81** | 113 |
| latency (cycles) | 11–21 | 5–22 |
| flip-flops | **6 014** | 8 558 |
| modules instantiated | **678** | 1 661 |
| 2-to-1 mux equivalents | **350** | 588 |
| total estimated area | **1 298 853** | 4 249 005 (**3.3×**) |

The "HLS-friendly" rewrite is **worse on every axis** — 3.3× the estimated area and 42 % more
flip-flops — because Bambu materialises a separate functional unit per ternary arm and shares
nothing, whereas the `switch` lets it bind one FU per operation across the mutually-exclusive
cases. The shipped `switch` version is therefore the better of the two authorings, and this is
recorded as a measurement rather than an intuition. The ternary variant is not committed; it lives
at `/nobackup/hls/scratch/valu_variant/` for as long as that scratch survives.

### What this means for the pilot

The reference is a **purely combinational block with zero flip-flops and one cycle of latency**.
The HLS output is an **81-state FSM with 6 014 flip-flops and 11–21 cycles of latency** — and at a
comfortable clock it is still a 62-state, 9-to-11-cycle, 6 012-flip-flop machine. That is not a
marginal QoR gap; it is a different class of machine, and neither loosening the clock nor rewriting
the C in the recommended data-flow style moves it.

What Bambu *did* get right is the parallelism the spec cares about: eight independent multipliers,
one per lane, no resource sharing across lanes, no DSP inference on an ASIC target. The unroll
survived; the combinationality did not.

**This is the first arithmetic-heavy block measured in this pilot, and the first where the gap is
structural rather than authored.** Both previous blocks were control-dominated and tolerated the
0.705 ns target. The open question this leaves — whether Bambu can be persuaded to emit a
single-state combinational datapath at all (some flag combination around scheduling / chaining /
`--no-chaining`, or a top function small enough to fit one control step), or whether every HLS
block in this project will carry a start/done FSM regardless — is the obvious follow-up, and is
worth a bead before any Stage-2 PPA comparison treats these numbers as HLS's best effort.
