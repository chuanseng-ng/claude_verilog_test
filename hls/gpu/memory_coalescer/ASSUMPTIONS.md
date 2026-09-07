# `memory_coalescer.c` — assumptions made where the spec was silent

GH #119 "NL → C → RTL" pilot. This file is a **measured output of the experiment**, not
paperwork: it records every point at which the natural-language specification did not
determine the implementation, and what was chosen instead.

The spec I was given is reproduced at the top of `memory_coalescer.c`. I did not read
`rtl/gpu/memory_coalescer.sv` or anything else under `rtl/`.

---

## A. Functional gaps in the spec

### A1. `rdata_o` for a lane that never issues a read → **driven to 0**

The spec calls `rdata_o[8][31:0]` "per-lane read results" and stops there. It never says
what a masked-off lane should present, nor what any lane should present during a **store**
(`we_i = 1`), where no read data exists at all.

**Chosen:** all 8 outputs are pre-cleared to 0; only lanes that actually issue an AR/R pair
overwrite theirs. So a masked-off lane reads 0, and every lane reads 0 during a store.

**Why:** a defined constant needs no extra state (the alternative, "hold the last value",
requires an enable-gated register per lane and makes the block's output depend on request
history). It is deterministic for an equivalence testbench, and it cannot be mistaken for
stale data left over from a previous warp instruction. The risk of the alternative — a
consumer accidentally reading a stale lane and it *looking* plausible — is worse than the
risk of this one.

**Confidence this matches the reference RTL: low-medium.** This is a genuine coin-flip and
a likely source of an equivalence-check mismatch if the hand-written RTL holds instead.

### A2. `mask_i == 0` (no active lane) → **zero transactions, immediate `done_o`**

The spec's FSM begins `IDLE -> find first active lane` and never defines the case where
there is no such lane.

**Chosen:** the lane loop body never fires, no AXI transaction is issued, and the function
returns immediately — i.e. `IDLE -> DONE`, with `done_o` pulsed as usual.

**Why:** it is the only reading consistent with "one AXI transaction per **active** lane"
(zero active lanes ⇒ zero transactions), and any other choice (stall, or issue a dummy
transaction) would either deadlock the warp scheduler waiting for a `done_o` that never
arrives, or put a bogus address on the bus.

**Confidence: high.**

### A3. `we_i` is per-**request**, not per-lane → **any non-zero `we` means store**

The interface has one `we_i` bit for the whole request, matching a VLD/VST opcode, so a
request is entirely loads or entirely stores. Mixed load/store within a single request is
not representable and is not attempted.

Sub-assumption: `we` arrives as a 32-bit word on the Bambu interface. The spec says `we` is
"0 or 1", but I test it for **truth** (`if(we)`) rather than for equality with 1, so a
wrapper that drives `0xFFFFFFFF` or a sign-extended flag still behaves as a store rather
than silently turning into a load. Same for `mask`: only bits 0..7 are examined
(`(mask >> lane) & 1`), so bits 8..31 are ignored rather than being an error.

**Confidence: high** on the per-request reading; the "any non-zero" widening is a defensive
choice the spec neither requires nor forbids.

### A4. Misaligned addresses → **silently truncated to the containing word**

The spec says addresses are 32-bit **byte** addresses and transfers are 32-bit single
beats, but says nothing about what happens if an address is not 4-byte aligned. Crucially,
it also says "Phase 4 has no fault model" and that all error responses are ignored — so
there is **no channel on which a misalignment could be reported** even if it were detected.

**Chosen:** every address is treated as naturally aligned; `mem[addr >> 2]` drops the low
two bits. A misaligned address accesses the word that contains it.

**Why:** detecting it would cost hardware and produce a signal with nowhere to go. This
also matches the project-wide "naturally aligned accesses only" convention stated in
`CLAUDE.md` for the CPU.

**Side effect worth flagging:** Bambu still printed
`Code has LOADs or STOREs with unaligned accesses` for this source. That is Bambu reasoning
about a runtime-variable pointer, not a real misalignment — the generated master derives
`ARSIZE`/`AWSIZE` from `clog2(32 >> 3) = 2`, i.e. a correct 4-byte access.

### A5. Error responses (`rresp`, `bresp`) → **nothing written, by construction**

The spec explicitly requires them to be accepted and ignored. There is no C-level code for
this because a C pointer dereference **has no error return**: Bambu's generated AXI master
already asserts `BREADY`/`RREADY` and discards the response codes. This was the one place
where the spec's requirement and the HLS abstraction happened to coincide exactly — nothing
could be written even if I wanted to.

### A6. Write byte-enables → **`WSTRB` always all-ones**

All accesses are full 32-bit `unsigned` words, so every write beat has `WSTRB = 4'b1111`.
The spec's VST is word-granular and offers no sub-word or masked-store operation, so no
partial-word path exists. Confirmed in the output: `m_axi_gmem_wstrb` is 4 bits wide.

---

## B. Gaps created by the HLS abstraction, not by the spec

### B1. Lane ordering is a *scheduling* property I cannot assert in C

The spec's central behavioural requirement — "one AXI transaction per active lane **in
lane-index order**" — is not expressible in C. C guarantees program order only where a
dependence exists; a scheduler is free to reorder independent loads.

**Chosen:** rely on structure, and deliberately add **no** unroll/pipeline pragma. Ordering
is carried by (a) the single `gmem` bundle, which gives exactly one AXI-master functional
unit that every access must serialise through, and (b) the fact that the addresses are
runtime values Bambu cannot disambiguate, so it must preserve program order.

**Measured outcome:** Bambu *did* fully unroll the loop — the datapath has 8
`ui_pointer_plus_expr_FU` address adders and 8 `read_cond_FU` branch units, one per lane —
but kept them as a **sequential chain of 8 conditional blocks** (47 FSM states, 33 control
steps). That is the specified lane-0→lane-7 walk; unrolling here is a scheduling detail,
not a behavioural change.

**This is fragile and I want it on the record:** the ordering guarantee lives in the
generated Verilog, not in the C, and is not protected by any assertion. A change to the
flag set in `hls/bambu.mk` could silently break it.

### B2. `start_i` / `done_o` are not authored, they are inferred

The C function models exactly **one** request. Bambu's start/done handshake supplies the
pulse semantics: invocation is `start_i`, return is `done_o`. Bambu reported
`Done port is registered`, which gives the single-cycle `done_o` pulse the spec asks for.
I did not, and could not, write the `DONE -> IDLE` transition — it is generated.

### B3. The AR/R and AW/W/B channel sequencing is not authored either

The spec's state machine (`AR -> R`, `AW -> W -> B`) is entirely produced by Bambu from the
`m_axi` pragma. The C source only determines *which* lanes are touched, *in what order*,
and *load vs store*. So the part of the spec that reads most like RTL is the part with no
corresponding C at all. Verified in the output that the generated master matches the spec's
hard requirement: `assign m_axi_arlen = 0;` and `assign m_axi_awlen = 0;`.

### B4. Bambu adds two ports the spec's interface does not mention

- **`mem` (32-bit input)** — the gmem base pointer, a consequence of
  `offset = direct`. The integrating wrapper must tie it to 0 for `mem[addr >> 2]` to yield
  AXI byte address `addr`, as the brief states.
- **`cache_reset` (input)** — an artefact of Bambu's AXI master. Not part of the specified
  interface; the shim will have to tie it off.

These are not spec ambiguities; they are interface residue that the adapting shim must
absorb. Recording them because they are a real cost of the HLS route.

### B5. Local arrays vs. the required scalar parameters

The brief requires the 8 lanes as individual scalar parameters. Inside the function I
immediately gather them into `addr[8]` / `wdata[8]` local arrays and scatter `rdata[8]` back
out. This is permitted ("only the *parameters* are constrained") and was verified not to
create BRAM ports: the generated netlist has **no** `_address0` / `_ce0` / `_we0` / `_d0` /
`_q0` signals anywhere.

---

## C. What I did *not* assume

- I did not implement any address **merging / coalescing**. The spec pins the Phase 4
  default at `GPU_ENABLE_COALESCE = 0`, i.e. one transaction per active lane with no
  merging. Two lanes hitting the same word therefore produce two transactions. This is what
  the spec asks for, even though the block is named "coalescer".
- I did not add an outstanding-transaction / pipelining optimisation. The spec's FSM is
  explicitly one-request-at-a-time (`R` completes before the next lane starts), and
  overlapping AR requests would violate "AR -> R -> next lane".
- I did not add any fault, timeout, or bus-error handling — the spec forbids a fault model.

---

## D. Honest summary of risk

The most likely place this diverges from the hand-written RTL is **A1** (`rdata_o` on
inactive/store lanes), which the spec simply does not determine. The most fragile part of
the implementation is **B1** (lane ordering held by the scheduler, not by the source).
Everything else in section A is either forced by the spec or a defensive widening that
cannot change specified behaviour.
