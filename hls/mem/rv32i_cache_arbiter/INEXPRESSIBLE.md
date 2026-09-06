# `rv32i_cache_arbiter` is outside Bambu's expressible domain

**Verdict: no C was authored for this block, and none should be.** GH #119 bead `2ft`.

This is a **result of the pilot, not a concession in it.** GH #119 asks how HLS output compares to
hand-written RTL. For this block the answer is not a worse PPA number — it is that the flow cannot
express the block at all. That is a stronger and more useful finding than a measurement would have
been, and it is why no C++ was written rather than forced.

Everything below is reproducible on this machine with the pinned tool
(`nix develop .#hls`, PandA 2024.10, rev `c2ba6936ca2ed63137095fea0b630a1c66e20e63-main`).

---

## What the block is

`rtl/mem/rv32i_cache_arbiter.sv` (222 lines) multiplexes **three incoming requesters** onto one
AXI4 master: I-cache read, D-cache read (refill), D-cache write (writeback). Its defining
behaviour:

- a **grant** is held for the duration of an AXI burst — read grants release on `RLAST`, write
  grants on the `B` response;
- priority D$-write > D$-read > I$-read, evaluated continuously;
- it is **permanently reactive**. It is never "called". It has no arguments, no return value, and
  no notion of completing.

## Why Bambu cannot express it

### 1. Bambu emits AXI *masters* only — verified, not inferred

The interface mode is set by a `#pragma HLS interface ... mode = <m>` pragma parsed by Bambu's
clang plugin. Asking for a slave is rejected outright:

```
$ bambu probe_slave.c --top-fname=probe --generate-interface=INFER ...
probe_slave.c:2:34: error: Invalid HLS interface mode
#pragma HLS interface port = req mode = s_axilite
```

The accepted mode names are compiled into the shipped plugin, and `m_axi` is there while nothing
AXI-slave-shaped is:

```
$ strings usr/gcc_plugins/clang16_plugin_ASTAnalyzer.so | grep -xE 'm_axi|axis|array|handshake|acknowledge|ovalid'
acknowledge
array
axis
handshake
m_axi
ovalid

$ strings usr/gcc_plugins/clang16_plugin_ASTAnalyzer.so | grep -iE 's_axi|axi.*slave'   # no output
$ strings usr/bin/bambu                              | grep -xE 's_axi|s_axilite'        # no output
```

And an AXI master is only ever produced as a **side-effect of dereferencing a pointer** — it is
Bambu's memory-access mechanism. There is no way to ask for AXI channels as an interface the
design *responds to*.

### 2. Every design is wrapped in a start/done handshake

`--generate-interface` accepts exactly three values (`bambu --help`):

```
MINIMAL  -  minimal interface (default)
INFER    -  top function is built with an hardware interface inferred from ...
WB4      -  WishBone 4 interface
```

Under `MINIMAL` and `INFER` the top module always carries `clock`, `reset`, `start_port`,
`done_port`. That is not a default to be switched off — it is the C execution model made
structural: a C function is *invoked*, computes, and *returns*. All three designs built in this
pilot show it (`gate_b`, `memory_coalescer`, `rv32i_hazard_unit`).

The arbiter has no invocation to map onto. "Call the arbiter" is not a meaningful operation.

### 3. The one slave-shaped option, WB4, does not help — checked rather than assumed

`--generate-interface=WB4` genuinely does produce a slave port, so it deserves a direct answer
instead of being ignored. Probed:

```
$ bambu probe_wb4.c --top-fname=probe_wb4 --generate-interface=WB4 ...
module probe_wb4_wb4_interface(clock, reset, irq,
    dat_im, ack_im, cyc_om, stb_om, we_om, addr_om, dat_om, sel_om,   // master side
    cyc_is, stb_is, we_is, addr_is, dat_is, sel_is, dat_os, ack_os);  // slave side
```

The slave side is a **memory-mapped control** interface: write the arguments, start the function,
poll for completion, read the result. It is Wishbone rather than AXI, and more decisively it is
still wrapped around a *function invocation*. It gives no way to express three independent
incoming AXI channel sets, per-burst grant retention, or `RLAST`-terminated release.

### 4. What a forced attempt would actually measure

The only way to produce something with the arbiter's port list would be to hand-write a
SystemVerilog shim containing the grant register, the priority encoder, the burst-hold logic and
the response routing — i.e. **the entire design** — wrapped around an HLS core that contributed
nothing. The comparison would then be hand-RTL versus hand-RTL, reported as though it were
hand-RTL versus HLS.

The two blocks that *were* measured (`memory_coalescer`, `rv32i_hazard_unit`) both have wire-only
shims precisely so their numbers mean something. A shim that holds the design under test would
invert that. It would not be a weak result; it would be a false one.

---

## What this does to the evaluation document's argument

`docs/CPP_TO_RTL_HLS_EVALUATION.md` currently argues, from literature, that hand-RTL beats HLS on
"control-heavy, timing-critical, cycle-accurate microarchitecture… crossbar arbitration/handshake".
This block upgrades that claim for one named case:

> not "HLS produces worse arbitration logic" but **"HLS cannot express bus arbitration in this
> class at all"** — no pragma, no interface mode, and no amount of pragma tuning changes it,
> because the obstacle is the C execution model rather than the scheduler.

That is a categorical limit, and unlike a PPA number it does not need re-measuring when the tool
version changes — only re-checking that the interface-mode list still lacks a slave.

## Scope of the claim, stated honestly

- It is about **Bambu 2024.10**, the tool this pilot pinned. Another HLS tool with a genuine
  AXI-slave interface mode, or a future Bambu that adds one, would need re-testing.
- It is about **this class of block**: permanently-reactive multi-channel bus arbitration. It says
  nothing about datapath accelerators, which is exactly the domain the evaluation document already
  reserves for HLS.
- It is **not** a claim that the arbiter is hard to write in C. The algorithm is trivial. The
  obstacle is entirely the interface.

## What was built instead

The block had **no standalone unit test** — `soc_all` only reached it indirectly through full-SoC
traffic. That gap was worth closing on its own merits, independently of #119, so this bead
delivered `tb/cocotb/mem/test_cache_arbiter.py` and the `mem_cache_arbiter` target in
`sim/Makefile` covering burst grant-hold to `RLAST`, the D$-write > D$-read > I$-read priority,
write-grant release on `B` (not `wlast`), read-data routing isolation, and the one-cycle
AR-forwarding delay out of `GRANT_NONE`.
