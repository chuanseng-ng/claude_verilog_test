# `rv32i_hazard_unit.c` — assumptions made where the spec was silent

GH #119 "NL → C → RTL" pilot, block 2 (CPU arm). This file is a **measured output of the
experiment**, not paperwork: it records every point at which the natural-language
specification did not determine the implementation, and what was chosen instead.

The spec I was given is reproduced at the top of `rv32i_hazard_unit.c`. **I did not read
`rtl/cpu/core/rv32i_hazard_unit.sv` or anything else under `rtl/`.**

Confidence ratings below are my honest estimate of the probability that the choice matches
the hand-written reference, not a measurement.

---

## 0. The one derivation everything else rests on: the stage ↔ register map

The spec is internally cross-wired on purpose (it says so: *"port names keep the `ex1b_`
prefix for backward compatibility"*), so before anything could be written I had to rebuild
the map from the *register* identities rather than the port prefixes. Ordering the six
producer groups by "cycles behind the instruction in EX1a", which the spec states
explicitly for each:

| port group | register | its output sits in | behind EX1a | forwarding tier |
| :--------- | :------- | :----------------- | :---------- | :-------------- |
| `id_ex_*`   | `id_ex`           | EX1a | 0 | (this is the consumer) |
| `ex1b_*`    | `ex1a_ex1b_reg`   | EX1c | 1 | `fwd_*_sel = 2'b11` |
| `ex1c_*`    | `ex1c_ex1b_reg`   | EX1b | 2 | `fwd_*_ex1c` |
| `ex1b2_*`   | `ex1b_ex2_reg_q`  | EX2  | 3 | `fwd_*_ex1b2` |
| `ex_mem_*`  | `ex_mem`          | MEM  | 4 | `fwd_*_sel = 2'b01` |
| `mem_wb_*`  | `mem_wb`          | WB   | 5 | `fwd_*_sel = 2'b10` |

Note the `ex1b_`/`ex1c_` prefixes are swapped relative to the stages they describe. Every
line of the C follows the **right-hand three columns**, never the prefix. Confidence in
this table: **high** — the spec states each group's lag from EX1a directly, and the two
independent priority statements (forwarding order, and the four load-use cases) both come
out consistent under it and inconsistent under any other assignment.

### Flush-output ↔ stage mapping (derived, not stated)

The spec's flush lists name *stages* ("flush EX2, EX1b2, EX1b, EX1c, EX1a, ID, IF") while
the outputs name *registers*. A flush takes effect at the next clock edge, so flushing the
FF between stage X and stage Y injects a bubble into Y and therefore kills the instruction
currently in **X**:

| spec wording | output asserted | FF |
| :----------- | :-------------- | :- |
| flush IF   | `flush_if_id`       | IF→ID |
| flush ID   | `flush_id_ex`       | ID→EX1a |
| flush EX1a | `flush_ex1a_ex1b_o` | EX1a→EX1c *(the port doc names this FF explicitly)* |
| flush EX1c | `flush_ex1c_ex1b_o` | EX1c→EX1b *(likewise)* |
| flush EX1b | `flush_ex1_ex2_o`   | EX1b→EX2 (`ex1b_ex2_reg_q`) |
| flush EX2  | `flush_ex_mem`      | EX2→MEM |

The two ports whose FF the spec names outright (`stall_ex1a_ex1b_o` = "EX1a→EX1c FF",
`stall_ex1c_ex1b_o` = "EX1c→EX1b FF") pin this mapping, and the remaining four follow by
the same rule. Confidence: **high**. The alternative reading — that `flush_X_Y` kills the
instruction *in* stage Y — would leave the 7-name flush list needing 7 outputs when only 6
exist, and would make `flush_ex1a_ex1b_o` mean "flush EX1c", contradicting its own doc
comment.

---

## A. Functional gaps in the spec

### A1. The three forwarding output groups are **mutually exclusive** (one cascade)

The spec describes the tiers *relationally*: `fwd_*_ex1c` "overrides EX2 but not the EX1b
tier", `fwd_*_ex1b2` has "priority between the EX1c and EX2 tiers". That gives one total
order — **EX1b > EX1c > EX1b2 > EX2 > WB > regfile** — but it does not say whether the
hazard unit *reports* only the winner or reports every tier and lets the datapath mux
arbitrate.

**Chosen:** a single strict cascade. At most one of `{sel != 2'b00, ex1c, ex1b2}` is
asserted; when the EX1c or EX1b2 tier wins, `fwd_*_sel` is parked at `2'b00` (regfile).

**Why:** it is the single-`always_comb`-with-`else if` idiom that hand-written RTL almost
always uses; it makes the outputs self-describing (you can read the winner off the ports);
and it is correct under *any* downstream mux priority, whereas the alternative is only
correct if the datapath ranks its mux legs the same way the doc comment claims.

**The alternative:** three independent comparator groups, where `fwd_a_sel` could read
`2'b01` (EX2 matched) while `fwd_a_ex1c` is simultaneously 1. That drives the *same* value
into the ALU — so the two are functionally equivalent in the pipeline — but they differ
bit-for-bit on the losing ports, which a port-level equivalence check will flag.

**Confidence: medium.** This is the single most likely place for a cosmetic (non-functional)
equivalence mismatch. The phrase "overrides EX2" is faintly suggestive of the independent
form, since a cascade would have nothing left to override.

### A2. The EX2 tier (`2'b01`) is suppressed when `ex_mem` holds a **load**

`ex_mem_mem_rd` is an input, but no priority case in the spec mentions a load in MEM, and I
found no other use for it. Its only sensible role is qualifying forwarding: the value in
the `ex_mem` register for a load is the computed **address**, not the loaded data — which
is precisely why the `mem_wb` group is the only producer group with **no `mem_rd` port at
all** (a load's data *is* valid there). Leaving the input unconnected would make it a dead
port, which no hand-written module is likely to declare (it would be lint-flagged).

**Chosen:** `TIER_EX2` requires `ex_mem_reg_wr_en && !ex_mem_mem_rd`. The same gate is
applied one stage earlier in the `_pre` computation, where the producer that *will* be in
`ex_mem` next cycle is the `ex1b2_*` group, so the `_pre` EX2 tier is gated on
`ex1b2_mem_rd`.

**Important caveat:** the load-use interlock (A4) already guarantees a dependent
instruction can never reach EX1a while its producing load is still in `ex_mem`, so this
gate is **unreachable in any legal pipeline state**. It is a genuine don't-care that I
resolved one way and am recording. Random-vector equivalence checking over the raw input
space *will* exercise it; a trace-driven check never will.

**Confidence: medium.** The reasoning ("otherwise the port is unused") is strong, but the
opposite convention — the classic textbook forwarding unit that ignores `mem_rd` entirely
and leans wholly on the interlock — is also very common.

**Deliberately asymmetric:** the EX1b / EX1c / EX1b2 tiers are **not** gated on their
`mem_rd` bits. Those bits already have a defined use (the interlock), so the "unused input"
argument does not apply there, and gating them would be an invention rather than a
deduction. I am flagging the asymmetry because it is arguable.

### A3. x0 gating is on the **producer's** `rd` only

RV32I hardwires `x0`, so a producer with `rd == 0` must never forward and must never cause
a load-use stall. I do **not** additionally test `rs != 0`: `rd != 0` together with
`rd == rs` already implies `rs != 0`, so the extra term is dead logic. Confidence: **high**
(functionally forced; only the gate-level structure could differ).

### A4. The load-use consumer is the instruction in **ID**, checked on both `rs1` and `rs2`

The spec pins cases 5–8 by their outputs, not by naming a stage: *"stall IF,ID; flush
ID→EX1a"* holds the instruction in ID and drops a bubble into EX1a, which only makes sense
if the waiting consumer is the one in ID. (Had the consumer been in EX1a, the vector would
have read "stall IF,ID,EX1a; flush EX1a→EX1c".) `if_id_rs1_addr` / `if_id_rs2_addr` are
therefore the consumer addresses — which is also the only other use those two inputs could
have besides the `_pre` outputs. `rs2` is included unconditionally, which also covers the
store-data operand of an `SW`/`SH`/`SB`.

**Confidence: high.**

### A5. Which producer each of the four `load_use_*` cases watches

The case comments read "load in EX1a / EX1c / EX1b / EX1b2". Under the section-0 table:

| case | comment | producer group | stall # |
| :--- | :------ | :------------- | :------ |
| `load_use_ex1`  | load in EX1a  | `id_ex_mem_rd`  | 1 |
| `load_use_ex1c` | load in EX1c  | `ex1b_mem_rd`   | 2 |
| `load_use_ex1b` | load in EX1b  | `ex1c_mem_rd`   | 3 |
| `load_use_ex2`  | load in EX1b2 | `ex1b2_mem_rd`  | 4 |

The only real ambiguity is the last: "EX1b2" could conceivably have meant `ex_mem`. It does
not, and the timing proves it. Trace a load L in EX1a at cycle 0 with a dependent C in ID:

```
cycle 0  L in EX1a  (id_ex_*)   -> stall #1
cycle 1  L in EX1c  (ex1b_*)    -> stall #2
cycle 2  L in EX1b  (ex1c_*)    -> stall #3
cycle 3  L in EX2   (ex1b2_*)   -> stall #4
cycle 4  L in MEM   (ex_mem_*)  -> no stall; C advances into EX1a
cycle 5  C in EX1a, L in WB     -> forward 2'b10, data is valid
```

Four consecutive producer stages, no gap, and exactly the four stall cycles needed for the
load's data to become forwardable from the *only* tier that can carry it. This
self-consistency is strong enough that I regard it as derived rather than assumed.

**Confidence: high.**

### A6. The interlock is gated on `mem_rd` and `rd != 0`, **not** additionally on `reg_wr_en`

Every real load asserts both; a bubble asserts neither. The extra term is only observable on
an input vector the pipeline cannot produce. Chosen: the classic two-term form.
**Confidence: medium-high** — a purely structural difference if it is wrong.

### A7. `fwd_store_*` is the `rs2` decision on a separate mux → **bit-identical to `fwd_b_*`**

In RV32I the store-data operand is always `rs2`, and this block is only ever told about the
instruction in EX1a, so the store-forward decision is computed from `id_ex_rs2_addr` with
the identical tier priority. The ports are duplicated (rather than the caller just reusing
`fwd_b_*`) because the B-operand mux feeds the ALU — where a store selects the *immediate*,
not `rs2` — while the store-data path needs the forwarded `rs2` value on its own mux.
Consequently all three `fwd_store_*` outputs are **bit-identical to `fwd_b_*`** by
construction.

That redundancy is a little suspicious and is the reason I am flagging it: if the reference
evaluates store forwarding against a different address, or one stage later, or with a
narrower tier set, this will not match. But nothing in the given interface would let it
differ — the block is handed exactly one `rs2` address.

**Confidence: medium-high** on the pairing, with the redundancy as the open question.

### A8. What the `_pre` outputs compute — the exact producer/consumer pairing

The spec says only *"computed using `if_id_rs*_addr` (the consumer in ID) against producer
addresses shifted one stage earlier"*. The consumer in ID **this** cycle is the consumer in
EX1a **next** cycle, and every producer advances one stage too, so each tier is re-sourced
from the group one stage *younger* than the group feeding the live decision:

| tier | live source | `_pre` source | the advance |
| :--- | :---------- | :------------ | :---------- |
| `2'b11` EX1b   | `ex1b_*` (EX1c)  | `id_ex_*` (EX1a)  | EX1a → EX1c |
| `fwd_*_ex1c`   | `ex1c_*` (EX1b)  | `ex1b_*` (EX1c)   | EX1c → EX1b |
| `fwd_*_ex1b2`  | `ex1b2_*` (EX2)  | `ex1c_*` (EX1b)   | EX1b → EX2 |
| `2'b01` EX2    | `ex_mem_*` (MEM) | `ex1b2_*` (EX2)   | EX2 → MEM |
| `2'b10` WB     | `mem_wb_*` (WB)  | `ex_mem_*` (MEM)  | MEM → WB |
| `2'b00` regfile | — | `mem_wb_*` falls off the end | WB retires |

**`mem_wb_*` has no `_pre` role.** The instruction in WB this cycle has committed by the
time the ID instruction reaches EX1a, so a plain register read returns its result. This
presumes the register file is **write-first / internally bypassed within a cycle**, which
the spec never states — but it is the standard arrangement, and it is the only one under
which a 5-tier forwarding network is sufficient at all (otherwise a sixth tier would be
needed and no port exists for it). Confidence in the shift table: **high** (it is the only
shift-by-one that closes); confidence in the write-first regfile: **high** by necessity.

Consumer addresses: `if_id_rs1_addr` → the `fwd_a_*_pre` group, `if_id_rs2_addr` → the
`fwd_b_*_pre` group. There is **no** `fwd_store_*_pre` in the interface, so nothing is
emitted for it; the store-data select is assumed to be generated live in EX1a only.

### A9. `_pre` outputs are **not** squashed by stalls or flushes

The spec says they are "registered by the caller". I compute them unconditionally.
Suppressing them here would double up on the enable/clear the caller already applies to the
ID/EX boundary, and would corrupt the value if the caller does *not* apply one. Leaving
them raw composes correctly in both cases. **Confidence: medium-high.**

### A10. The nine priority cases form a strict `if / else if` chain

The spec's heading is "Priority (highest → lowest)", not "the following contribute". Under
the independent-OR reading, a trap coinciding with `mem_cache_stall` would flush *and*
freeze simultaneously (a frozen register cannot accept a bubble), and `if_cache_stall`
would keep asserting `stall_pc` underneath a trap redirect, defeating the redirect. The
chain also makes the spec's two deliberate orderings meaningful: `mem_trap_redirect`
**outranks** `mem_cache_stall` (a trap must escape a stalled D-cache) while
`ex_pc_redirect` is **outranked** by it (a branch redirect waits for the cache).

**Confidence: high.**

### A11. The exact output vector for each of the nine cases

`—` = 0. Six flush outputs, seven stall outputs. Default (no case active) is all zero.

| # | condition | stall_pc | stall_if_id | stall_id_ex | stall_ex1a_ex1b | stall_ex1c_ex1b | stall_ex1_ex2 | stall_ex_mem | flush_if_id | flush_id_ex | flush_ex1a_ex1b | flush_ex1c_ex1b | flush_ex1_ex2 | flush_ex_mem |
|:-|:-|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 1 | `mem_trap_redirect` | — | — | — | — | — | — | — | **1** | **1** | **1** | **1** | **1** | **1** |
| 2 | `mem_cache_stall`   | **1** | **1** | **1** | **1** | **1** | **1** | **1** | — | — | — | — | — | — |
| 3 | `ex_pc_redirect`    | — | — | — | — | — | — | — | **1** | **1** | **1** | **1** | **1** | **1** |
| 4 | `id_jal_taken`      | — | — | — | — | — | — | — | **1** | — | — | — | — | — |
| 5–8 | `load_use_*`      | **1** | **1** | — | — | — | — | — | — | **1** | — | — | — | — |
| 9 | `if_cache_stall`    | **1** | — | — | — | — | — | — | — | — | — | — | — | — |

Per-row notes:

- **Case 1** — the list "EX2, EX1b2, EX1b, EX1c, EX1a, ID, IF" is seven stage names but
  only six flush outputs exist. **Assumption:** "EX1b2" and "EX2" name the same physical
  slot — the port doc calls `ex1b_ex2_reg_q` "the EX1b2 register" *and* says its output is
  "the instruction in EX2" — so the list collapses onto all six outputs. The PC is **not**
  stalled: the redirect must be free to load the trap vector. There is no `flush_pc` port,
  so "flush IF" is realised by `flush_if_id`. Confidence: **medium-high**; the alternative
  is that `flush_ex_mem` should stay low, which is the one bit I would check first.
- **Case 2** — "global freeze" read as every register including the PC, nothing flushed.
  Confidence: **high**.
- **Case 3** — the spec gives case 3 an output vector *identical* to case 1, so the two are
  distinguishable at this interface only by priority (and by the redirect target, chosen
  outside this block). **Taken literally this also flushes EX2** — the stage the
  redirecting instruction has itself advanced into, since `ex_pc_redirect` is documented as
  "registered from EX1b stage". That would kill a `JAL`/`JALR` before it writes `rd`. I
  implemented the spec as written rather than second-guessing it; **`flush_ex_mem` is the
  single bit most likely to differ from the reference here.** Confidence in the row as a
  whole: **medium**; in `flush_ex_mem` specifically: **low-medium**.
- **Case 4** — "flush IF only" = `flush_if_id` alone; the JAL sits in ID and survives, only
  the sequentially-fetched instruction behind it dies. Confidence: **high**.
- **Cases 5–8** — hold the consumer in ID (`stall_if_id`) and hold the PC with it
  (`stall_pc`), bubble into EX1a (`flush_id_ex`), and let EX1a and everything downstream
  advance so the load can drain toward WB. `stall_id_ex` stays **low** — stalling it would
  freeze the load in place and deadlock. Confidence: **high**.
  The four cases are listed at four distinct priority levels but produce identical vectors
  and are indistinguishable at the interface, so the C ORs them into one term. This is a
  code-shape difference only; the logic is the same.
- **Case 9** — "stall PC only", taken literally: `stall_if_id` is **not** asserted and no
  bubble is injected. That is only safe if the fetch stage presents an explicitly
  invalid/NOP instruction during an I-cache miss, which is outside this block's interface
  (there is no `if_valid` input to tell us otherwise). Many designs would also assert
  `flush_if_id` here — but doing so would silently discard a validly fetched instruction if
  the fetch unit *does* hold its own output, so the literal reading is the safer of the
  two. Confidence: **medium**; this is a real spec gap, not a preference.

### A12. Upper bits of the address ports are ignored; booleans are tested for truth

Register addresses are 5-bit, but every input arrives as a 32-bit word on the Bambu
interface, so each address is masked with `0x1F` before use. Control inputs
(`*_mem_rd`, `*_reg_wr_en`, the redirects, the cache stalls) are tested for **truth**, not
for equality with 1, so a wrapper that drives `0xFFFFFFFF` or a sign-extended flag still
behaves correctly. Both are defensive widenings the spec neither requires nor forbids; no
fault channel exists on which a malformed input could be reported anyway.

---

## B. Gaps created by the HLS abstraction, not by the spec

### B1. The block is **not** combinational in the generated RTL — this is the headline gap

The spec describes a pure combinational function, and the C models one (no state, no
clock, no reset, no memory). Bambu nonetheless produced a **9-state FSM taking 6 to 9
cycles**, with a `clock`/`reset`/`start_port`/`done_port` handshake and **50 flip-flops**,
none of which the reference has.

Worse than the latency itself: the latency is **data-dependent** (min 6, max 9). A hazard
unit whose stall/flush verdict arrives a variable number of cycles after its inputs cannot
be dropped into a pipeline at all. Any integrating shim would have to either accept a
multi-cycle bubble or re-time the whole pipeline around it.

**I checked whether my authoring style caused it.** The natural transliteration of
"Priority (highest → lowest)" is a C `if / else if` chain, which could plausibly have become
FSM branches. I rebuilt the stall/flush section branch-free (pure boolean arithmetic,
mutually-exclusive terms OR'd together) and re-ran with identical flags: **9 states, 6–9
cycles, 11 control steps — bit-for-bit the same schedule**, and area moved only 1 785 912 vs
1 791 535 (0.3 %). So the FSM is *not* an artefact of the priority-chain idiom; it is
Bambu's scheduling of a wide 32-bit comparison network against a 0.705 ns clock. The
readable version was kept. This is the pilot's most important structural finding for this
block.

### B2. Bambu refused to inline `static` helper functions, and the run **failed** because of it

The three pieces of repeated logic (the 5-tier cascade, the tier→select decode, the
load-use predicate) were first written as ordinary `static` C functions — five call sites
for the cascade alone. Bambu answered:

```
Required never inline for function fwd_tier
Constraining function fwd_tier with 1 resources
Internally allocated memory: 80
error -> clock constraint too tight: BRAMs for this device cannot run so fast...
        (ARRAY_1D_STD_DISTRAM_NN_SDS: 0.81285553 > 0.70499999)
```

It turned `fwd_tier` into a *shared single-resource submodule* and allocated an 80-byte
distributed RAM to pass its eleven arguments — which then failed the 0.705 ns constraint and
aborted the whole run. **`__attribute__((always_inline))` did not change the decision**
(the "Required never inline" line was emitted verbatim again).

The fix was to demote all three helpers to **preprocessor macros**. That is a real cost of
the HLS route worth recording: at this clock period, ordinary C function decomposition is
not available, so the source must be written in a less structured style than a C programmer
would choose. It also fails *loudly*, which is the good case — compare the silent failures
catalogued in `hls/README.md`.

### B3. All ports are 32 bits wide; the spec's are 1 and 2 bits

Because every parameter is `unsigned` (mandated by the brief — an array parameter would
decay into a BRAM port group), the generated module has 26 × `input [31:0]` and 28 ×
`output [31:0]`. The reference's `[4:0]` addresses, `[1:0]` selects and 1-bit controls are
all widened. The internal masking (A12) makes this harmless, but the adapting shim must
zero-extend every input and truncate every output, and a naive gate-count comparison
against the hand RTL will be badly skewed by the 54 × 32 = 1 728 boundary bits.

### B4. `clock`, `reset`, `start_port`, `done_port` are interface residue

None of the four appears in the specified interface. They are Bambu's generated handshake.
For a block the spec defines as combinational, the shim must tie `start_port` high and
ignore `done_port` — which, given B1, is only valid if the consumer tolerates the 6–9 cycle
settling window. I could not author these away; there is no C construct for "this function
is combinational".

### B5. Port-shape check — clean

Verified in the generated `rv32i_hazard_unit.v`: all 26 inputs are plain scalar inputs, all
28 outputs are plain scalar outputs, and there is **not one** `_address0` / `_ce0` / `_we0`
/ `_d0` / `_q0` signal anywhere in the 336 KB file (grep count: 0). No memory interface of
any kind was inferred, which is the requirement the first (function-based) attempt failed.

---

## C. What I did *not* assume

- I did **not** invent a `flush_pc` or a `stall_mem_wb`. The spec lists exactly seven stall
  and six flush outputs and I drove exactly those.
- I did **not** add a `fwd_store_*_pre` group. The spec's `_pre` list contains only the A
  and B operands, so the store-data select is generated live in EX1a only.
- I did **not** add a sixth forwarding tier for `mem_wb` in the `_pre` computation. Under
  the shift-by-one rule that producer has retired to the register file (A8).
- I did **not** add branch prediction, an early-branch-resolution path, a WAW/WAR check
  (in-order pipeline, none needed), CSR-hazard handling, or FENCE.I interlocking. None is
  in the spec's nine cases, and inventing hazards is the failure mode that would most
  quietly break a real pipeline.
- I did **not** make the four `load_use_*` cases externally distinguishable. They are
  internal terms; the spec exposes no port that separates them.

---

## D. Honest summary of risk

Ranked by how likely each is to show up as an equivalence-check failure:

1. **A11 case 3, `flush_ex_mem`** — the spec literally says `ex_pc_redirect` flushes EX2,
   but that stage holds the redirecting instruction itself. One bit; genuinely 50/50.
2. **A1** — cascade vs. independent comparators. Functionally equivalent, bit-different on
   the losing ports; would fire on a large fraction of random vectors.
3. **A2** — the `ex_mem_mem_rd` gate on the EX2 tier. Unreachable in a legal pipeline
   state, so it will fail *only* under random-vector checking, never under a trace.
4. **A11 case 9** — "stall PC only" taken literally, with no `flush_if_id`.
5. **A7** — `fwd_store_*` being bit-identical to `fwd_b_*`.

The structural risk is entirely **B1**: even a perfectly matching truth table is not a
drop-in replacement while the generated block takes 6–9 clock cycles to produce a verdict
that the reference produces combinationally. For this block, the NL → C → RTL route
reproduces the *function* far more readily than the *timing shape*.
