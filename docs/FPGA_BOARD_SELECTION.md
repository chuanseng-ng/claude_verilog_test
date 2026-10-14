# FPGA board selection (bead `hlrm`, GH #245)

Status: **recommendation, not a purchase decision.** Written 2026-10-14. It builds on the yosys resource counts in
[`FPGA_STAGE0_EVALUATION.md`](FPGA_STAGE0_EVALUATION.md) §2. fmax exists as an ECP5 lower bound and as a real Vivado
Artix-7 result for the CPU-only build (§5, "Measured: ECP5 lower bound" and "Measured: Artix-7 XC7A200T (Vivado 2026.1)"); the
"fits" for the full SoC with GPU stays an estimate unless that subsection says otherwise.

## 1. How much FPGA the design needs

Xilinx 7-series LUT6 counts from yosys 0.62 `synth_xilinx` (Stage 0, measured), plus assumed overheads:

| Build | Today (measured) | + bring-up / debug logic (~5 K, assumed) | + 25 % future RTL growth (assumed) | Device size at <= 70 % LUT use |
|---|---|---|---|---|
| CPU only (no GPU) | 38.6 K | ~44 K | ~55 K | ~78 K |
| Full SoC with GPU | 62.4 K + ~5 K LUT-RAM | ~72 K | ~90 K | ~120-130 K |

- **Bring-up logic** means a debug bridge (JTAG-to-AXI or UART), one or two ILA cores, clocking and an IO wrapper.
  The ~5 K figure is an assumption, not measured.
- **25 % growth** is headroom for future RTL (a larger NPU, more IP, a bigger SRAM), not a planned feature list.
- **70 % LUT** is a common ceiling for routability and timing closure.
- **Margin in our favour:** Vivado typically reports 10-30 % fewer LUTs than yosys (inference, not measured here).
- **GPU shared memory:** 7-series mapped the 16 KB GPU shared memory to LUT-RAM (~5 K LUT sites). Forcing block RAM
  (`ram_style = "block"`) would remove that.
- **Not the limit:** block RAM (~9 RAMB36-eq) and DSP (19-44) are small next to every candidate below.
- **Main SRAM is 4 KB today** (`SRAM_MEM_WORDS = 1024`). Firmware validation may want much more; every candidate has
  enough block RAM for tens to hundreds of KB.

## 2. Candidates, with Singapore price and stock

Prices are distributor snapshots of unknown date, **before Singapore's 9 % GST**. Confirm before ordering.

| Board (FPGA) | LUTs | Full SoC with growth | CPU only with growth | Singapore price and stock |
|---|---|---|---|---|
| **Digilent Nexys Video** (XC7A200T, -1) | 134.6 K | **~62 %, fits** | ~37 % | **S$873.49, 83 in stock** at DigiKey SG (17-week lead time when out); RS SG had 3 |
| Digilent Genesys 2 (XC7K325T, -2) | 203.8 K | ~41 %, fits easily | ~25 % | **S$1,529.99, 46 in stock** at DigiKey SG (18-week lead time); Mouser SG S$1,527.61, 53 in stock |
| AMD Kria KV260 (Zynq UltraScale+ XCK26) | ~117 K | ~72 %, at the limit | ~43 % | No Singapore listing found. DigiKey US US$283.86, 420 in stock (about S$380 at ~1.34 S$/US$, before shipping and GST) |
| Digilent Arty A7-100T (XC7A100T) | 63.4 K | does not fit | ~87 %, too tight | No Singapore listing found. DigiKey US US$299 |
| Radiona ULX3S-85F (Lattice ECP5, open toolchain) | 83.6 K (LUT4) | does not fit | ~60 %, fits | No Singapore distributor. Crowd Supply US$235 + US$18 worldwide shipping |

XCK26 resources (Farnell listing): 256 K system logic cells, 144 block RAM, 64 UltraRAM, 1.2 K DSP.

## 3. Recommendation

**Digilent Nexys Video (XC7A200T).** It is the cheapest board found in stock in Singapore that holds the whole SoC,
GPU included, with room for growth.

- **vs Genesys 2:** more headroom and a faster speed grade, but ~75 % more expensive for margin the design does not need
  yet. Pick it only if fmax turns out to be the problem.
- **vs KV260:** cheapest by far; its ARM processor could load firmware and act as a debug host, and its UltraRAM could
  hold a much larger SoC SRAM. But the full SoC sits at the 70 % ceiling once it grows, PL pin access for the peripherals
  is limited, and no Singapore stock was found.
- **Arty A7-100T and ULX3S-85F:** CPU-only boards. The Arty has no room to grow; the ULX3S is the only fully open
  toolchain option.
- **Tools:** Nexys Video's XC7A200T is covered by the free Vivado ML Standard edition (verify at download time).

## 4. Second clock source (add-on)

Testing the CDC crossings properly needs two **independent** clocks; two outputs of one MMCM are frequency-locked and
do not exercise an asynchronous crossing (`FPGA_STAGE0_EVALUATION.md` §7, decision 9.5). None of the candidates was
confirmed to have a second user oscillator, so plan on an add-on.

No Digilent-branded programmable-oscillator Pmod was found. Options:

| Option | What | Price (snapshot) | Notes |
|---|---|---|---|
| **A. Adafruit Si5351A breakout (#2045)** (recommended) | I2C-programmable clock generator, 3 outputs, 8 kHz to 150+ MHz, own 25 MHz crystal, 3.3 V regulator, level-shifted I2C | about £7.70-7.90 (The Pi Hut), €12.95 (Bits & Parts), A$14.60 (Core Electronics); no Singapore listing found | Not Pmod form factor: wire it to a Pmod header (jumpers or a Pmod breakout). Its own crystal makes its outputs independent of the board oscillator. It can be programmed by the SoC's own I2C controller or a small FPGA-side init block. Headers need soldering on some clones. |
| B. Fixed canned oscillator on a Pmod breakout | A DIP/SMD crystal oscillator on a Pmod prototyping/breakout board | a few dollars | Cheapest; one fixed frequency per part; hand assembly. |
| C. Maxim DS1086LPMB1 | Pmod-format programmable oscillator board | unknown | Listed in a 2012 Maxim collateral PDF; likely obsolete, availability unconfirmed. |

**Clock-capable pins matter.** A clock entering the FPGA on a non-clock-capable pin cannot reach an MMCM/BUFG on the
dedicated route; Vivado then needs `CLOCK_DEDICATED_ROUTE FALSE`, which adds skew and jitter (usually acceptable for a
CDC soak clock, not for a performance clock). For Nexys Video, a Digilent forum thread (user-reported, **unverified**)
says Pmod JA is single-ended, not clock-capable and limited to <10 MHz, while JB/JC go to differential pairs. Before
buying, check the Nexys Video master XDC / schematic for which Pmod pins land on MRCC/SRCC sites. The board's FMC LPC
connector carries dedicated clock-capable `CLK*_M2C` pins and is the clean alternative if no Pmod pin qualifies.

## 5. Clock-speed sanity check: tool availability (checked 2026-10-14)

| Tool | Available? | Notes |
|---|---|---|
| Vivado | **No** | Not on the host, not in `/opt`, `/tools` or the nix store, and not in nixpkgs (proprietary). A free Vivado ML Standard install needs an AMD account download (~100 GB installed; `/nobackup` has ~600 GB free). |
| nextpnr 0.11.1 (nixpkgs) | Yes, via `nix build nixpkgs#nextpnr` | Architectures: `ecp5`, `ice40`, `nexus`, `generic`, himbaechel `gowin` / `ng-ultra` / `gatemate`. **No Xilinx 7-series** (nextpnr-xilinx / prjxray are not in nixpkgs). |
| trellis (ECP5 database) | Yes, nixpkgs `trellis` | Needed by `nextpnr-ecp5`. |
| openFPGALoader 1.1.1 | Yes, nixpkgs | Board programming only. |
| yosys | 0.69 in nixpkgs; Stage 0 used 0.62 from the nix store | Neither is in the project flake (`FPGA_STAGE0_EVALUATION.md` §1). |

Consequences:
- A **real post-route fmax for the recommended Artix-7** needs Vivado.
- With open tools available today, the only post-route timing is **nextpnr-ecp5 on an LFE5U-85F**. ECP5 is a slower
  family than Artix-7, so that figure is a lower bound for Artix-7, and only the CPU-only build fits.

### Measured: ECP5 lower bound (2026-10-14, CPU-only build, post place-and-route)

**Read this as a LOWER BOUND for the recommended Artix-7 (XC7A200T), not an estimate of it.** ECP5 is a slower family
than Artix-7. It was run because it is the only post-route timing the open tools can give today (decision on bead `hlrm`:
"ECP5 lower bound now, Vivado later"). No Xilinx timing exists yet.

**Result (nextpnr-ecp5, LFE5U-85F-6BG381C, CPU-only SoC, `--freq 60`, 3 seeds, post-route "Max frequency"):**

| Clock domain (what it clocks) | Seed 1 | Seed 2 | Seed 3 | Min .. max |
|---|---|---|---|---|
| `cpu_gated_clk` (CPU core, caches, CPU-side CDC; ASIC target 1282 MHz) | 47.95 | 51.66 | 48.33 | **47.95 .. 51.66 MHz** |
| `core_clk` (bus, peripherals, CRYPTO, NPU, DMA, SRAM; ASIC target 571 MHz) | 47.35 | 52.88 | 55.22 | **47.35 .. 55.22 MHz** |
| `cpu_core_clk` (ungated CPU-domain sync/reset logic, 174 FFs) | 132.03 | 148.06 | 122.80 | 122.80 .. 148.06 |
| `tck_i` (JTAG/DFT) | 101.32 | 122.22 | 109.05 | 101.32 .. 122.22 |
| `clk_i` (harness shell, 290 FFs) | 229.25 | 223.56 | 231.86 | (harness, not SoC) |

Both SoC domains **failed** the 60 MHz target in all three seeds, so the two numbers that matter are the achieved
Fmax of the two big domains: about **48-52 MHz (CPU)** and **47-55 MHz (fabric)**. Seed spread is about +-5 MHz. Only
one target (60 MHz) was run for the three seeds; the placer is timing-driven toward the target, so a different target would
move the numbers (not measured). Against the ASIC clocks this is a prototype scale factor of roughly 25x (CPU, 1282 MHz)
and 10-12x (fabric, 571 MHz). It sits in the upper half of the Stage 0 depth-proxy bracket (ECP5 no-GPU, 38-61 MHz;
`FPGA_STAGE0_EVALUATION.md` 2.5), which that proxy had labelled "order of magnitude only".

**Critical paths (post-route, copied from the nextpnr reports; module from the sv2v source line of the start flop):**

| Domain | Path (seed 1) | Shape | Seeds 2 and 3 |
|---|---|---|---|
| `cpu_gated_clk` | `rv32i_core` `mem_trap_entry_r` flop (hazard unit) -> `stall_ex1_ex2` -> `flush_ex1a_ex1b` -> `ex1b_comb` -> pipeline-register input mux | 11 LUT levels, 3.12 ns logic + 17.73 ns routing (85 % routing) | Same start flop; endpoint is the `u_icache.valid_array` bit reset (12 levels, 3.78 ns logic + 15.58 / 16.91 ns routing) |
| `core_clk` | `axil_to_apb` `apb_paddr` flop -> APB decode -> UART register bank write -> sync-reset pin of a UART `apb4_register_bank` flop | 11 LUT levels, 3.57 ns logic + 17.56 ns routing (83 % routing) | Seed 2: CRYPTO `aes128_core` S-box (`sub_bytes`) cone, 15 levels, 4.18 + 14.73 ns. Seed 3: I2C `apb4_register_bank` clock-divider -> `i2c_bit_engine.tick_q`, 22 levels (carry chain), 7.82 + 10.29 ns |

Reading: the CPU limiter is the **trap / stall / flush control cone** (the high-fanout control class the ASIC work also
fought), not the ALU, forwarding mux, cache tag compare or NPU MAC. The fabric limiter is **not one path**: three seeds gave three
different modules (UART bank, AES, I2C), all within ~8 MHz of each other, i.e. a flat wall of many near-critical paths. Both are
~85 % wire delay on a design this size, so seed noise is large and a vendor tool's placer may do better or worse.

**Utilisation (identical in every seed, `85k` device):** TRELLIS_COMB 39,004 / 83,640 (**46 %**; 34,290 logic LUT4 + 3,582
carry + 272 RAM + 136 RAMW), TRELLIS_FF 14,639 (**17 %**), DP16KD 17 / 208 (8 %), MULT18X18D 19 / 156 (12 %), DCCA (global
clock buffers) 5 / 56, TRELLIS_IO 6 / 365. Routing completed in every run (no unrouted nets); nextpnr's router1 reports no
congestion map, so "no congestion problem" is inferred from completion, not measured. The harness adds +118 LUT4 and +290 FF to
the Stage 0 count (34,172 / 14,349).

**Method:** `tools/fpga/stage0_pnr_ecp5.sh` (sv2v with `--define=FPGA --define=__pnr__` -> yosys 0.62 `synth_ecp5 -flatten
-run :check`, the Stage 0 settings, now with iopad insertion -> `nextpnr-ecp5 --85k --package CABGA381 --speed 6 --freq 60
--seed N --timing-allow-fail --ignore-loops`). Summaries via `tools/fpga/stage0_pnr_report.py`. Outputs in
`/nobackup/fpga_ecp5_fmax/` (not in the repo). Versions, all from nix: nextpnr 0.11.1
`/nix/store/z9dl8x2hkcnwa71b9fwjsqxdhgx7q4xc-nextpnr-0.11.1`, prjtrellis `trellis-unstable-2025-01-30`
`/nix/store/y7jvwg7amb7nk951clb1sl4k055wrnfc-trellis-unstable-2025-01-30` (database `lgnv5k4789pidnpsw9pwsf9vv84k3066`),
yosys 0.62 and sv2v 0.0.13.1 as in Stage 0. Nothing installed outside nix; `flake.nix` untouched.
Cost: yosys 3:29 / 1.7 GB; nextpnr 8:25 (seed 1, quiet host), 42:14 (seed 2) and 19:07 (seed 3) with other jobs loading the
host (load average ~13), peak RSS 1.33-1.35 GB each.

**What the harness cut** (`tools/fpga/ecp5_timing_harness.sv`; the core RTL is unchanged): `soc_top` has 292 port bits
(103 in, 189 out) against 205 user IO on CABGA381, so it cannot be pinned. The 99 non-clock inputs come from one
serial shift register on a single pin, the 189 outputs are registered and XOR-folded into one pin (so no output cone is
optimised away); `clk_i`, `cpu_clk_i`, `scan_clk_i`, `tck_i` stay real pins. **Not timed:** every pad-level path (input to
register, register to output), IO standards, banks, pin placement (nextpnr placed the six IO freely, no LPF). The shells add ~300 FFs
(2 %).

**How the gated clock and the clock tree were treated (caveats that matter):**
- Nothing here is a real clock tree. `core_clk` is `clk_i` through the `dft_clk_mux` **LUT**, `cpu_core_clk` is `cpu_clk_i`
  through a LUT, and `cpu_gated_clk` is the behavioural latch + AND `rv32i_clock_gate` (Stage 0 option D, unchanged). nextpnr
  promoted all five clock nets to global clocks (5 DCCA) and timed each as its own domain; it derives the LUT delay
  (0.24 ns) into the clock-to-clock relation. It does **not** time the latch enable path.
- yosys maps the four latches (`u_cpu_cg`, `u_tck_cg` clock gates; `dft_clk_switch` `en_a_q` / `en_b_q`) as LUT feedback, i.e. four
  combinational loops. **nextpnr refuses to run without `--ignore-loops`** ("Timing analysis failed due to combinational loops");
  the loops are therefore cut, not analysed. A LUT-feedback latch as a clock gate is unproven in hardware; the real prototype
  needs one of the §6 gating options of `FPGA_STAGE0_EVALUATION.md`.
- `--freq 60` applied to **every** domain; the ASIC's different per-domain targets are not expressed.
- **Cross-domain paths are timed as synchronous** paths at the 60 MHz relation. The #94 SDC (`set_clock_groups -asynchronous`,
  `set_max_delay -datapath_only`) is **not translated**; the CDC FIFOs and bridges are timed like ordinary logic. The worst
  cross-domain figures nextpnr printed (44.99 / 47.49 / 51.89 MHz in seeds 1 / 2 / 3: `tck_i` falling edge -> `core_clk`, a JTAG/DFT
  path, and in seed 3 a harness shift-register flop -> `core_clk` reset fanout) are in the same band as the domain Fmax and are
  not separate limiters. The relations between the two main SoC domains (`core_clk` <-> `cpu_gated_clk`) printed only max-delay
  values (seed 1: 2.77 ns and 1.84 ns), no failing frequency.
- No hold analysis exists in nextpnr; no hold number is produced.

**With the GPU:** one attempt (seed 1, same flow and harness) **did not place**. Packing reported 84,953 LUT4 (101 %) and 85,909
TRELLIS_COMB of 83,640 (**102 %**; 67,369 logic LUT4 + 4,888 carry + 8,464 RAM LUT4 = 80 % of the RAM-capable sites), 19,202 FF
(22 %), 49 DP16KD, and the placer stopped with "ERROR: Unable to find legal placement for all cells, design is probably at
utilisation limit" (about 2 min of nextpnr). So the with-GPU build does not fit an LFE5U-85F, consistent with the Stage 0
sizing, and it has **no** timing number. No Artix-7 conclusion follows from this (that device is larger).

**Not verified:** any Xilinx/Vivado timing (the Artix-7 figure is unmeasured; ECP5 -> Artix-7 speed-up is not quantified here);
a different `--freq` target or `router2`; post-synthesis simulation of the netlist; a real clock gate; pad timing; power; hold.

### Measured: Artix-7 XC7A200T (Vivado 2026.1)

Real vendor result for the recommended part: **Vivado v2026.1 (lin64, Build 6511674), `xc7a200tsbg484-1`, free BASIC licence**,
post-route, non-project batch flow. Reproduce with `tools/fpga/vivado_fmax.sh` (+ `vivado_fmax.tcl`,
`vivado_fmax_constraints.tcl`, `vivado_fmax_report.py`); `VIVADO_SETTINGS` must point at the install's `settings64.sh`.
Outputs live in `/nobackup/fpga_vivado_fmax/` (not in the repo). The Genesys 2 comparison is not part of this run (Kintex-7
is not installed; tracked as bead `hlrm.1`).

**Result, CPU-only build (no GPU; the Sky130 tie-off replaces `rtl/gpu`), clock targets `clk_i` 10 ns (100 MHz) and `cpu_clk_i` 7 ns (143 MHz), one run:**

| Domain (ASIC target) | Target | WNS (setup) | TNS / failing endpoints | WHS (hold) | Estimated fmax = 1/(T - WNS) | Limiting path |
|---|---|---|---|---|---|---|
| `clk_i` = `core_clk` fabric: bus, peripherals, CRYPTO, NPU, DMA, SRAM (571 MHz) | 10.0 ns | **-2.085 ns** | -1152 ns / 1824 of 23,568 | +0.058 ns | **~83 MHz** | NPU MAC array: a PE weight register -> `acc_q` of column 2; 19 levels (12 CARRY4, 4 LUT2, 2 LUT4, 1 LUT3), 6.67 ns logic + 5.40 ns route |
| `cpu_clk_i` = gated CPU core (1282 MHz) | 7.0 ns | **-2.332 ns** | -3867 ns / 4839 of 13,583 | +0.117 ns | **~107 MHz** | `rv32i_core` EX2 `ex_mem.pc` -> EX1a/EX1b `alu_result` (ALU carry chain); second family: the same flop -> `u_csr` `mcycle`/`minstret` clock enables; 14 levels (6-7 CARRY4, 5 LUT6), 3.77 ns logic + 5.51 ns route |
| `tck_i` (JTAG TAP) | 10.0 ns | +0.000 ns (latch borrowing) | 0 | +0.160 ns | not limited (>= 100 MHz) | TAP `serial_o` -> clock-gate / clock-switch latch D |

Read as: **Artix-7 -1, CPU-only SoC: about 83 MHz fabric and about 107 MHz CPU after a full place-and-route**, against about 48-55
MHz on the ECP5 lower bound (so the lower bound was about 1.7x pessimistic for the fabric and about 2x for the CPU) and the Stage 0
depth-proxy bracket of 58-99 MHz (`FPGA_STAGE0_EVALUATION.md` 2.5; the measured fabric number sits inside it, the CPU one just
above it). Prototype scale factor vs the ASIC clocks: about 7x (fabric, 571 -> ~83 MHz) and about 12x (CPU, 1282 -> ~107 MHz).
**Both domains missed their target, so the estimate is what the router achieved while still trying; a `WNS >= 0` domain would
only have given a lower bound** (in an earlier 10 ns/10 ns run the CPU domain met timing at +0.033 ns, i.e. it stopped
optimising at 100 MHz; the 7 ns target is what exposed ~107 MHz). Only one target per domain was run in the reported
configuration, so the sensitivity of the estimate to the target is not measured. Single run, no seed sweep.

**Cross-domain crossings (reported separately, bounded by the translated CDC budgets, see below):** `clk_i` -> `cpu_clk_i`
WNS -1.444 ns (153 of 1258 endpoints fail) and `cpu_clk_i` -> `clk_i` WNS -1.052 ns (15 of 506), both against a
`set_max_delay -datapath_only 0.9 x destination period` bound (6.3 ns and 9.0 ns). This is the ASIC check-SDC budget applied
literally; it is tighter than a plain asynchronous cut, and with a 7 ns CPU clock the budget for crossings into the CPU domain is
only 6.3 ns. Not separate limiters of the two domain numbers; they are listed so nothing is hidden.

**Utilisation (post-route, `xc7a200tsbg484-1`):** Slice LUTs 18,981 of 133,800 available (**14.2 %**; 18,696 logic + 285
LUT-RAM), Slice registers 13,206 of 267,600 (4.9 %, 4 of them latches), F7 / F8 muxes 640 / 130, block RAM tiles 12 of 365 (3.3 %:
1 RAMB36 + 22 RAMB18), DSP48E1 2 of 740 (0.3 %), bonded IOB 6 of 285, BUFGCTRL 6 of 32. (The post-route report lists 133,800
LUTs available against 134,600 in the part query and the synthesis report; the reason was not investigated.) **Versus yosys Stage 0** (CPU-only, 38,554 LUT1-6, 14,079
FF, 9 RAMB36-equivalents, 19 DSP48E1): Vivado used **about 0.49x the LUTs** (the "10-30 % fewer" assumption in section 1 was too
conservative: it is ~51 % fewer here), about the same flops, 12 vs ~9 block-RAM tiles and 2 vs 19 DSPs (the 4x4 INT8 NPU
multipliers went to LUTs and CARRY4 chains, not DSP48E1). All blocks are present in the hierarchy report (CPU 7.9 K LUT, CRYPTO
3.0 K, NPU 2.0 K, bus 2.5 K, DMA 0.9 K, I2C 0.5 K); nothing was swept away by the harness. This does not move the section 1
sizing for the full SoC (that depends on the GPU, see below), but it removes the "38.6 K LUTs, 70 % rule" worry for the CPU-only build
on this part: it uses 14 %.

**Method (what was and was not done):**
- Vivado's own SystemVerilog frontend read the RTL directly (`read_verilog -sv`, one call per file, `synth_design
  -verilog_define FPGA -verilog_define __pnr__`, default `flatten_hierarchy rebuilt`); the sv2v output was **not** needed. File list =
  the Stage 0 list. One deviation, no committed RTL change: Vivado 2026.1 rejects the `input logic x` ports of the Sky130 GPU tie-off
  `pnr/sky130/soc/gpu_top_tieoff.sv` under its own `` `default_nettype none `` ([Synth 8-6735], Verilator / sv2v / yosys accept it), so
  the flow reads a copy of that one file with the directive line removed. The tie-off only exists in the no-GPU build.
- IO: the existing `tools/fpga/ecp5_timing_harness.sv` is vendor-neutral and was used **unchanged** (4 clock pins, `din`, `dout`; 99
  inputs from one shift register, 189 outputs folded into one pin). In-context synthesis, `opt_design`, `place_design`,
  `phys_opt_design`, `route_design`, default directives, 4 threads. Pad-level paths, IO standards and pin placement are **not**
  timed (Vivado placed the 6 pins itself, no XDC pin constraints). The harness shells add ~300 FFs.
- Clocks: `create_clock` on `clk_i`, `cpu_clk_i`, `scan_clk_i`, `tck_i`; no generated clocks (Vivado propagates the port clock through
  the DFT clock-mux LUT and the clock-gate AND).
- Translated from `phase5_soc_multiclock{,_check}.sdc` (the run prints one `VFMAX-CDC TRANSLATED / CUT / MISS` line per
  exception; `report_exceptions` is saved): domain-wide `set_max_delay -datapath_only 0.9 x destination period` both ways
  (Vivado form of the check SDC; `set_clock_groups -asynchronous` would override and cut these); the 0.5 x destination-period
  gray-pointer budgets on all 10 pointer crossings of the five `u_cpu_axi_cdc` channel FIFOs (directions as in the check SDC:
  aw/w/ar written in the CPU domain, b/r the other way); the `u_apb_pll2_cdc` / `u_apb_dbg_cdc` `req_q` / `ack_q` level
  crossings and `u_cpu_clk_dis_sync` (all bound, 1-2 flops each); `set_false_path` to the 18 async set/clear pins of the
  `cdc_reset_sync` flops; `scan_clk_i` physically exclusive with the two functional clocks.
- **Functional mode** (needed, and found the hard way): the SDC resolves the DFT clock muxes with `set_case_analysis` on the
  `scan_mode_i` / `scan_en_i` ports. In the harness those are flops and the mux is a LUT, so in a first run `tck_i` and
  `scan_clk_i` propagated into `core_clk` and timed every functional flop three times (a bogus `tck_i` WNS of -2.85 ns came from a TAP
  falling-edge flop into a CRYPTO register). Fix: `set_clock_sense -stop_propagation` for `tck_i` and `scan_clk_i` at the one LUT
  that merges them into `core_clk`; `tck_i` stays async to the functional clocks, so TCK -> functional crossings are **cut**.
- Harness-shell cuts, so no fake path is timed: `in_sr` flops that model SDC-false-pathed ports (`rst_n_i`, `cpu_rst_n_i`, `apb_*`,
  `uart_rx_i`, `spi_miso_i`, the DFT inputs) and the `in_sr` -> CPU-domain and CPU-domain -> output-shell crossings are
  `set_false_path`, as the SDC false-paths the port equivalents. `gpio_in_i` / `i2c_*_i` shell flops keep their `clk_i` launch.
- **Not translated:** port `set_input_delay` / `set_output_delay`, the SRAM `-hold` false paths, the GPU / CPU-APB `set_multicycle_path`
  (they exist for ASIC hard-macro boundaries; here CPU and GPU are plain RTL), clock uncertainty / latency / transition (the ASIC clock-tree
  model; Vivado computes its own), `set_case_analysis` itself (replaced by the clock-sense stop above), and any hold exception.

**Clock gate and DFT latches (kept behavioural, as Stage 0 option D):**
- Vivado inferred 4 latches (`LDCE`, 3 with inverted `G`): the `u_cpu_cg` and `u_tck_cg` clock-gate enables and the two
  `dft_clk_switch` `en_a_q` / `en_b_q` (the third GPU gate does not exist in the CPU-only build). No combinational loop exists
  (`check_timing` loops = 0, latch loops = 0), unlike the four loops yosys/nextpnr had to cut with `--ignore-loops`.
- Every LUT-driven clock net was **promoted to a global buffer**: `core_clk` (the DFT clock-mux LUT) -> one BUFG with 8,071 clock pins,
  `cpu_gated_clk` (latch + AND, as a LUT) -> one BUFG with 4,808 pins, `cpu_core_clk` -> one BUFG with 58 pins, plus the three port clocks;
  6 BUFGCTRL of 32 in total. So the gated clock is **not** a fabric-routed net: it is a LUT feeding a BUFG, the LUT sits in the clock
  path (extra insertion delay, included in Vivado's skew numbers; measured worst-path clock skew on the CPU critical path is -0.05
  ns), and the gate is **not** a BUFGCE/glitch-free clock enable in hardware.
- `report_methodology`: 5 x **TIMING-14 "LUT on the clock tree" (Critical Warning)** (the DFT muxes and the gate), 17 x LUTAR-1 (LUT drives
  an async reset), 13 x SYNTH-6, TIMING-9 / TIMING-10 once each (unknown CDC logic / missing synchroniser property), LATCH-1 advisory.
  They are warnings about the structure, not timing failures.
- The enable latch **is timed**: `u_cpu_cg/en_latch_reg/D` is a `cpu_clk_i` fall-edge latch endpoint with 0.000 ns slack **by time
  borrowing** (2.058 ns borrowed of a 3.5 ns half period, source `u_cpu_clk_dis_sync` through one LUT4). It did not limit either domain.
- The *effect of gating on the reported numbers* was **not isolated** (no run with the gate removed, which would need an RTL arm; that
  is the open clock-gating decision). The evidence for "small" is that the CPU critical path starts and ends on gated flops with
  skew of -0.05 ns and positive hold slack (+0.117 ns); the evidence against being fully clean is TIMING-14.

**Cost:** synthesis 4:07 wall / 2.49 GB peak RSS; place and route (this run) 10:06 wall / 2.73 GB; both well inside the host limits.


1. Board (recommendation: Nexys Video).
2. Clock-speed sanity check: done for the CPU-only build. ECP5 lower bound ~48-52 MHz CPU, ~47-55 MHz fabric; Artix-7
   XC7A200T-1 in Vivado 2026.1 ~107 MHz CPU, ~83 MHz fabric (above). Kintex-7 / Genesys 2 comparison: bead `hlrm.1`.
3. Second clock source (recommendation: Si5351A breakout), after confirming clock-capable pins on the chosen board.
4. The Stage 1 decisions already recorded on bead `hlrm`: GPU shared-memory RAM style, clock-gating strategy, strip DFT
   on the prototype, IO wrapper and `boot_rom` image owner.

## Sources

- [DigiKey SG – Nexys Video 410-316](https://www.digikey.sg/en/products/detail/digilent-inc/410-316/5456481)
- [RS Singapore – Nexys Video](https://sg.rs-online.com/web/p/fpga-development-tools/1346477)
- [DigiKey SG – Genesys 2 410-300](https://www.digikey.sg/en/products/detail/digilent-inc/410-300/5730862)
- [Mouser SG – programmable logic dev tools](https://www.mouser.sg/c/semiconductors/engineering-development-tools/programmable-logic-ic-development-tools?pg=8)
- [element14 SG – Genesys 2](https://sg.element14.com/digilent/410-300/dev-board-fpga/dp/2528808)
- [FPGA Developer – Genesys 2](https://boards.fpgadeveloper.com/boards/Genesys-2)
- [DigiKey US – SK-KV260-G](https://www.digikey.com/en/products/detail/amd/SK-KV260-G/13985269)
- [Farnell – SK-KV260-G-ED (XCK26 resources)](https://fr.farnell.com/amd/sk-kv260-g-ed/kit-de-dem-64-bits-arm-cortex/dp/4719664)
- [DigiKey US – Arty A7-100T](https://www.digikey.com/en/products/detail/digilent-inc/410-319-1/9445912)
- [Crowd Supply – ULX3S](https://crowdsupply.com/radiona/ulx3s)
- [Adafruit – Si5351A breakout overview](https://learn.adafruit.com/adafruit-si5351-clock-generator-breakout/overview)
- [The Pi Hut – Adafruit Si5351A](https://thepihut.com/products/adafruit-si5351a-clock-generator-breakout-board-8khz-to-160mhz)
- [Bits & Parts – Adafruit 2045](https://www.bitsandparts.nl/en/Clock-generator-Si5351A-Breakout-8KHz-to-160MHz-Adafruit-2045-p100227)
- [Core Electronics – Adafruit 2045](https://core-electronics.com.au/adafruit-si5351a-clock-generator-breakout-board-8khz-to-160mhz.html)
- [Maxim analog essentials (DS1086LPMB1)](https://wcm-cce.cldnet.analog.com/media/en/news-marketing-collateral/solutions-bulletins-brochures/maxim-analog-essentials-collection.pdf)
- [Digilent forum – Nexys Video Pmod connectors](https://forum.digilent.com/topic/17773-nexys-video-pmod-connectors/)
- [Nexys Video reference manual](https://reference.digilentinc.com/programmable-logic/nexys-video/reference-manual)
