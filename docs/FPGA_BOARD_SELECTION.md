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
  yet. Pick it only if fmax turns out to be the problem (the measured Artix-7 fmax, ~74-107 MHz in Vivado, does not trigger that; section 5). Re-checked against the Kintex-7 measurement (section 5, "Measured: Kintex-7"): about 1.7-1.9x faster than Artix-7, which does not change this.
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
| Vivado | **Yes since 2026-10-15** (v2026.1, `/nobackup/FPGA_SW/2026.1/Vivado`, free BASIC licence; installed after this table was first written, the original note was: not on the host, not in `/opt`, `/tools` or the nix store, and not in nixpkgs (proprietary). A free Vivado ML Standard install needed an AMD account download (~100 GB installed; `/nobackup` has ~600 GB free). |
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
Outputs live in `/nobackup/fpga_vivado_fmax/` (not in the repo). The Genesys 2 comparison is the next subsection (bead `hlrm.1`).

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
multipliers went to LUTs and CARRY4 chains, not DSP48E1). All blocks are present in the hierarchy report; the harness was checked and swept nothing away ("Trimming check" below). This does not move the section 1
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

**Cost (CPU-only):** synthesis 4:07 wall / 2.49 GB peak RSS; place and route 10:06 wall / 2.73 GB; both well inside the host limits.

**With the GPU (full SoC), same flow, same targets (`clk_i` 10 ns, `cpu_clk_i` 7 ns), one run: it fits, comfortably.**

| | CPU-only | Full SoC with GPU |
|---|---|---|
| `clk_i` fabric WNS / estimated fmax | -2.085 ns / ~83 MHz | **-3.452 ns / ~74 MHz** (4527 of 56,511 endpoints fail) |
| `cpu_clk_i` CPU WNS / estimated fmax | -2.332 ns / ~107 MHz | **-3.183 ns / ~98 MHz** (6267 of 13,588 fail) |
| Hold WHS (worst) | +0.058 ns | **-0.112 ns, 8 endpoints** (see below) |
| `clk_i` -> `cpu_clk_i` / `cpu_clk_i` -> `clk_i` crossings WNS | -1.444 / -1.052 ns | -1.454 / -1.229 ns |
| Slice LUTs (post-route) | 18,981 (14.2 %) | **40,586 of 133,800 (30.3 %)**: 37,485 logic + 3,101 LUT-RAM |
| Slice registers | 13,206 (4.9 %) | 17,988 (6.7 %), 5 latches |
| Block RAM tiles | 12 (3.3 %) | 28 of 365 (7.7 %): 1 RAMB36 + 54 RAMB18 |
| DSP48E1 | 2 (0.3 %) | 26 of 740 (3.5 %) |
| BUFGCTRL | 6 | 7 of 32 |
| Wall time / peak RSS (synthesis + P&R in one session for the GPU build) | 4:07 + 10:06 / 2.7 GB | 21:23 / 3.28 GB |

- **GPU fit verdict on XC7A200T: fits with a large margin.** 30 % of the LUTs, 8 % of the block RAM, 4 % of the DSPs. That is half of
  the "~62 %" of section 2, which came from yosys LUT counts plus 25 % growth and bring-up margin; today's measured SoC is 30 %, so even
  after +25 % growth and +5 K bring-up logic (both assumed, not measured) the estimate is about 42 %.
- **GPU shared memory went to block RAM in Vivado**: `shared_memory` is 32 RAMB18 (plus 9.6 K LUTs of mux and control around them);
  yosys had chosen LUT-RAM (~5 K LUT sites) for the same RTL. The GPU vector register file went to LUT-RAM (2,816 LUT-RAM sites
  in `gpu_top`). So the Stage 1 "GPU shared-memory RAM style" decision is not forced on this part: Vivado already picks block RAM.
- **Timing with the GPU is worse, and the CPU number moved even though the CPU RTL did not.** The fabric limiter is a GPU
  warp-scheduler `warp_done` flop -> DMA `state_q` clock enable (16 levels, 2.79 ns logic + 9.51 ns route = 77 % wire, clock skew
  -0.91 ns); the CPU limiter in this run is EX2 `ex_mem.mem_size` -> I-cache `refill_buf` clock enable (12 levels, 2.0 ns logic + 7.8 ns
  route). The CPU domain gained a worse WNS (-2.33 -> -3.18 ns, ~107 -> ~98 MHz) with identical CPU logic, so **the placement-to-placement
  spread of a single run is of the order of 1 ns (~10 %)**; the honest reading is "fabric ~74-83 MHz, CPU ~98-107 MHz" rather than any
  single figure, and one run per build is all that was done (no seed or target sweep).
- **Hold:** worst -0.112 ns on 8 endpoints (THS -0.49 ns). The worst one is a harness shell flop `in_sr[82]` (`gpio_in_i[31]`) -> the
  GPIO input synchroniser, with 1.52 ns of clock skew: the shell flop sits behind a plain `clk_i` BUFG while the synchroniser sits
  behind the `core_clk` LUT + BUFG (extra insertion delay). The SDC's `set_false_path -hold -from [all_inputs]` was **not**
  translated, so this is a harness / pad-hold artifact; the other seven endpoints were not individually inspected. It does show a
  real structural point: a LUT in the clock path adds about 1.5 ns of insertion delay against a direct BUFG.
- **Clock gating / latches:** 5 `LDCE` (the CPU, GPU and TCK clock-gate enables and the two clock-switch latches); every LUT-driven clock net again became a BUFG (the GPU gated clock is its own BUFG with 5,462 pins); 8 x TIMING-14
  (Critical Warning) instead of 5; no combinational loops.

**Trimming check (is Vivado's 2x-smaller LUT count and 2-vs-19 DSP real, or did logic disappear?) - verdict: no material trimming;
the numbers are valid for the design as written.** Evidence, all measured unless marked inference:
1. **Harness did not trim anything.** `soc_top` synthesised alone, out of context (`vivado_fmax.sh ... ooc`: no harness, every port
   kept, nothing tied off) gives CPU-only **18,687 LUT / 12,957 FF / 12 BRAM tiles / 2 DSP** and with GPU **40,017 LUT / 17,763 FF /
   28 BRAM tiles / 26 DSP**. The in-context runs (18,700 / 13,239 and 40,038 / 18,046) differ by exactly the harness shells
   (+282 / +283 FF, +13 / +21 LUT). The 6-pin harness neither created constants nor orphaned outputs.
2. **Removal messages are small and behaviour-preserving.** Synthesis log, CPU-only: 37 flops "unused, removed" (31 are the
   high bits of the NPU requantiser product register, absorbed into the DSP48E1 P register, per the `DSP Report` lines), 7 unused CSR
   registers (`rv32i_csr_file`: two trimmed from 32 to 4 bits), 92 flops with a constant-0 input propagated (59 in `u_crypto`),
   and >=100 duplicate registers merged (Synth 8-3886 hit its 100-message print limit; the printed ones are pipeline duplicates such as
   `id_ex_reg.rs2_addr[4:0]` == `instruction[24:20]`). `opt_design` then removed **192 cells in total** and propagated no constants.
   Nothing block-sized is removed.
3. **Every block is present with its state.** Flip-flops per block, Vivado (post-synthesis hierarchy) vs yosys (the same sv2v netlist,
   non-flattened `synth_xilinx`, one instance per module assumed): CPU 4,717 vs 6,284 (-25 %, the merged duplicates), CRYPTO 2,799 vs 3,007,
   NPU 1,076 vs 1,011, DMA 801 vs 545, I2C 374 vs 620, GPIO 288 vs 290, PWM 260 vs 288, SPI 205 vs 323 (other peripherals not tabulated); SoC total 12,957 vs 14,079 (-8 %). A trimmed block would have lost its flops; none did. (Per-block **LUT**
   counts cannot be compared the same way: with `flatten_hierarchy rebuilt` Vivado attributes LUTs by pre-optimisation names, so for example
   the APB read-mux LUTs of CRYPTO appear under `u_axil_apb_bridge`. Only the totals are meaningful.)
4. **The DSP gap is a mapping choice.** The only multipliers Vivado put in DSP48E1 are the NPU requantiser product (`prod_d_w` =
   32 x 17 -> 2 cascaded DSPs: `DSP Report ... (PCIN>>17)+A*B`). The 16 INT8 x INT8 PE multipliers in `npu_mac_array`
   (`16'(w_q) * 16'($signed(a))`, i.e. 8-bit operands behind a sign extension) went to LUT fabric plus a 12-CARRY4 chain, which is the
   fabric-fmax limiting path above and the reason the NPU costs 1,977 LUTs. yosys put the same 16 + 3 (requantiser) multipliers, plus one in
   `i2c_controller` (not traced), into 19 DSP48E1. Vivado clearly does infer DSPs for wide multiplies: the GPU adds 24 DSP48E1 in
   Vivado (26 - 2) against 25 in yosys (44 - 19).
5. **Where the 2x LUT gap comes from is only partly shown.** Shown: S-boxes of AES went to 8 RAMB18 ROMs in Vivado while yosys
   `proc_rom` made them logic; duplicates merged (-1.1 K FF and their LUTs); wide-mux packing (640 F7
   + 130 F8 vs 3,271 + 872 in yosys). Inference only, not isolated per cause: Vivado's LUT6 packing and cross-boundary optimisation
   versus ABC's `synth_xilinx` result (yosys's own non-flattened run is **bigger** than its flattened one, 15.9 K + 5.1 K INV LUTs for the CPU
   alone, so 38.5 K is itself a flatten-dependent figure). The GPU increment is similar in both tools (+21.3 K LUT in Vivado, +23.8 K in
   yosys), so the gap is in the common base, not the GPU.
Consequence: the utilisation and fmax numbers above stand. The LUT ratio should be read as "Vivado needs roughly half to two thirds of the
LUTs yosys reports for this RTL", not as a bound for other RTL.

**What the measurement changes in this document:**
- Section 1's "Vivado typically 10-30 % fewer LUTs than yosys (inference)" is replaced by a measurement: **~51 % fewer for CPU-only
  (18,981 vs 38,554) and ~35 % fewer for the full SoC (40,586 LUT + LUT-RAM vs 62,353 logic LUT + ~5 K LUT-RAM sites)**. The yosys-based
  sizing in sections 1 and 2 is therefore conservative by about 2x for LUTs, and the "fits" column above is pessimistic.
- Section 2's "Arty A7-100T does not fit the full SoC" is **no longer true on LUTs alone**: 40.6 K of 63.4 K is ~64 % today, and
  ~80 % with the 25 % growth, so it fits today, with no room for bring-up logic and growth (plus the other limits not measured here:
  its pins; its 135 block RAM tiles and 240 DSPs would cover the 28 and 26 used here, from the device data sheet, not checked in Vivado). The recommendation below does not change, because
  the user wants growth headroom and debug logic, and the Nexys Video still has ~2x the LUTs for a price that was already
  decided to be acceptable; it is noted as an alternative only if cost dominates.
- Timing: on both Artix-7 builds the prototype clocks are **~74-107 MHz**, a 7-17x scale factor against the ASIC targets. That is
  fast enough for firmware validation and the CDC soak, and well above the ECP5 lower bound; it does **not** need the Genesys 2's
  faster speed grade, so the "pick it only if fmax turns out to be the problem" condition of section 3 is not triggered by this
  measurement.

**NOT verified in the Artix-7 numbers:** any other speed grade or part (Kintex-7 / Genesys 2 is measured in the next subsection); a sweep of clock targets
or seeds (one run per build, ~1 ns spread observed); post-route simulation; power; pad-level timing and hold (harness shells only);
`phys_opt_design` after routing and any non-default directive (a longer-effort flow may do better); the effect of removing the
behavioural clock gate; the other 7 hold endpoints (not inspected); any run on hardware.

### Measured: Kintex-7 XC7K325T-2 (Vivado 2026.1), the Genesys 2 part (bead `hlrm.1`)

Same flow as the Artix-7 run above, only the part changed: **`xc7k325tffg900-2`**, Vivado v2026.1, same RTL (origin/main
`7875da3`; no RTL change since the Artix-7 run, only bead notes), same harness, same filelist, same constraints script, same
flow (`opt_design`, `place_design`, `phys_opt_design`, `route_design`, default directives), `maxThreads 4`. `tools/fpga/vivado_fmax.*`
needed **no change**: the part was already the `VFMAX_PART` variable and the Artix-7 default is untouched. Invocation:
`VFMAX_PART=xc7k325tffg900-2 VFMAX_PERIOD_CPU=7 vivado_fmax.sh . <out> {nogpu|gpu} ... 10` (CPU-only: `synth` then `impl`; with GPU:
`both`, as for Artix-7). Outputs in `/nobackup/fpga_vivado_fmax_k7/` (not in the repo). Every figure below is [M] (read from the Vivado
reports of this session) unless marked [A] (assumed / inferred) or [R] (read from another document).

**Step 1: like-for-like targets (`clk_i` 10 ns, `cpu_clk_i` 7 ns), one run per build. Result: the Kintex-7 met every constraint, so
these are lower bounds, not achieved fmax** (the placer stops optimising once the target is met; the Artix-7 run missed all four, so
its figures were what the router achieved while still trying).

| Build / domain | Artix-7 -1 WNS [R] (est. fmax) | Kintex-7 -2 WNS (lower bound 1/(T-WNS)) | WNS swing |
|---|---|---|---|
| CPU-only, `clk_i` fabric | -2.085 ns (~83 MHz) | **+1.411 ns** (>= 116 MHz) | +3.50 ns |
| CPU-only, `cpu_clk_i` | -2.332 ns (~107 MHz) | **+0.088 ns** (>= 145 MHz; the reported WNS is the clock-gate enable latch, borrowing; the worst register-to-register path has +0.748 ns, >= 160 MHz) | +2.42 ns (>= 3.08 ns on the register path) |
| With GPU, `clk_i` fabric | -3.452 ns (~74 MHz) | **+0.367 ns** (>= 104 MHz) | +3.82 ns |
| With GPU, `cpu_clk_i` | -3.183 ns (~98 MHz) | **+0.102 ns** (>= 145 MHz, same latch endpoint) | +3.29 ns |

**Step 2 (an addition to the brief, needed because step 1 saturated): tighter targets, `clk_i` 7 ns (143 MHz) and `cpu_clk_i` 5 ns
(200 MHz)**, implementation only on the same synthesis checkpoints (so only the constraint changes), one run per build. This is
what measures an achieved fmax, the same way the Artix-7 7 ns CPU target did. It is a different target pair from the Artix-7 run, so
it is **not** a strict like-for-like; step 1 is the strict one.

| Build / domain | Target | WNS / failing endpoints | Estimated fmax = 1/(T-WNS) | Limiting path (start -> end; logic) |
|---|---|---|---|---|
| CPU-only, `clk_i` fabric | 7.0 ns | **+0.245 ns**, 0 of 23,444 (met) | **>= 148 MHz** (lower bound; true limit not reached) | NPU MAC: `ain_q` -> column-3 `acc_q`, 20 levels (13 CARRY4, 5 LUT2), 3.21 ns logic + 3.57 ns route |
| CPU-only, `cpu_clk_i` | 5.0 ns | **-0.566 ns**, 1807 of 13,589 | **~180 MHz** | `u_cpu_pmu_rst_sync` flop -> synchronous-reset pin of `id_ex_reg` (`rs2_data`, `csr_op`...), 4 levels (LUT3/5/6/6), 0.40 ns logic + 3.71 ns route, clock skew -1.12 ns: a **reset-distribution** path, not the ALU path that limited Artix-7 |
| With GPU, `clk_i` fabric | 7.0 ns | **-0.955 ns**, 269 of 56,540 | **~126 MHz** | GPU warp scheduler `rr_ptr` -> `u_gif_adapter` `ar_addr_q`, 16 levels (9 LUT6, 1 MUXF7), 1.07 ns logic + 5.65 ns route, skew -1.10 ns |
| With GPU, `cpu_clk_i` | 5.0 ns | **-0.257 ns**, 243 of 13,607 | **~190 MHz** | `ex1c_ex1b_reg` `pc` -> `u_csr` `mhpmcounter4` clock enable, 16 levels (8 CARRY4, 4 LUT6), 1.34 ns logic + 3.58 ns route |

(Step-1 critical paths, for the record: CPU-only `clk_i` worst is `u_pll_sub` stub `locked_q` -> SHA `w_q` reset pin, 2 levels, 7.4 ns
of routing, +1.411 ns slack; with GPU it is a GPU scheduler flop (`rr_ptr`) -> DMA `state_q` clock-enable path, the same family that limited Artix-7 (17 levels, 1.48 ns
logic + 6.98 ns route, skew -0.93 ns); `cpu_clk_i` is the clock-gate enable latch in both, then `mem_wb_reg.pc` -> `u_csr` `mcause`
clock enable (15 levels, 7 CARRY4) at +0.748 ns CPU-only.)

**Prototype scale factor** (ASIC 571 MHz fabric / 1282 MHz CPU), using the step-2 numbers: fabric ~126 MHz with GPU (4.5x) and
>= 148 MHz CPU-only (<= 3.9x); CPU ~190 MHz with GPU (6.7x) and ~180 MHz CPU-only (7.1x). Artix-7 was 7-17x.

**Kintex-7 vs Artix-7, does the difference exceed the ~1 ns run-to-run spread?** Yes, on every comparison, with the caveat that the
spread was observed on Artix-7 only and is not re-measured here (one run per build and target on Kintex-7 as well).
- Strict like-for-like (step 1, same 10/7 ns targets): the WNS swing is **+2.4 to +3.8 ns** (>= 3.1 ns on the CPU register path),
  i.e. 2.4x to 3.8x the 1 ns spread, and it flips all four domains from failing to meeting timing.
- Achieved periods (step 2 against the Artix-7 estimates): with GPU, fabric 8.0 ns vs 13.5 ns (-5.5 ns, 1.7x) and CPU 5.3 ns vs 10.2 ns
  (-4.9 ns, 1.9x); CPU-only, fabric <= 6.8 ns vs 12.1 ns (>= 5.3 ns, >= 1.8x) and CPU 5.6 ns vs 9.3 ns (-3.8 ns, 1.7x). Because the Kintex-7
  targets were tighter and tighter targets push the placer harder, a part of this gap may be the target, not the device [A]; the strict
  step-1 swing does not have that issue.
- Reading: **Kintex-7 -2 is roughly 1.7x to 1.9x faster than Artix-7 -1 on this design** (fabric ~126 MHz+ vs ~74-83 MHz, CPU ~180-190 MHz vs
  ~98-107 MHz), and its fabric limiter moves around (NPU MAC, GPU scheduler -> bus) just as on Artix-7. Single runs, so read the
  ratio as 1.7-1.9x +/- the placement spread, not as a precise factor.

**Utilisation (post-route, `xc7k325tffg900-2`, step-1 runs; step-2 within +/-2 % of these):**

| | CPU-only | With GPU |
|---|---|---|
| Slice LUTs | 18,375 of 203,800 (**9.0 %**; 18,090 logic + 285 LUT-RAM) | 39,518 (**19.4 %**; 36,417 logic + 3,101 LUT-RAM) |
| Slice registers | 13,143 (3.2 %), 4 latches | 17,950 (4.4 %), 5 latches |
| Block RAM tiles | 12 of 445 (2.7 %) | 28 (6.3 %): 1 RAMB36 + 54 RAMB18 |
| DSP48E1 | 2 of 840 (0.2 %) | 26 (3.1 %) |
| BUFGCTRL | 6 of 32 | 7 of 32 |
| Artix-7 for reference [R] | 18,981 LUT (14.2 %), 13.2 K FF, 12 BRAM, 2 DSP | 40,586 LUT (30.3 %), 18.0 K FF, 28 BRAM, 26 DSP |

The mapping is the same as on Artix-7 (same block RAM, DSP and register counts; LUT count 3 % lower CPU-only and 3 % lower with GPU, a
packing difference between the two device families [A]). The Kintex-7 simply has 1.5x the LUTs.

**Hold:** CPU-only is clean in both steps (WHS +0.061 / +0.066 ns on `clk_i`, +0.088 / +0.094 ns on `cpu_clk_i`). **With GPU it is
not, and this one is not a harness-shell artifact:** step 1 `clk_i` WHS **-0.312 ns on 118 endpoints** (THS -13.9 ns); step 2 **-0.206 ns on
203 endpoints** (THS -19.9 ns). The worst endpoints are internal bus-to-GPU registers (`u_axil_ic` / `u_periph_bridge` / `u_sram`
`buf_data_q` -> `u_gpu` `ar_addr_q`, `aw_addr_q`, `if_id_q`), with **+0.92 to +1.10 ns of clock skew** (destination later than source).
Cause [A, not isolated]: the GPU clock is the behavioural LUT clock gate promoted to its own BUFG, so its insertion delay is later than
the plain `clk_i` BUFG (8 x TIMING-14 "LUT on the clock tree", the same structural finding as Artix-7, where the skew was about 1.5 ns).
On Artix-7 only 8 endpoints (-0.112 ns) failed hold and the worst was a harness shell flop, so the Kintex-7 hold picture is worse and
different. It does not affect the fmax numbers, but it is a real finding for the clock-gate decision (bead `hlrm.2`): on hardware this
would need a hold fix (balanced clock, a vendor clock-enable primitive instead of a LUT gate, or removing the gate on the prototype), and
the run was not repeated with a post-route `phys_opt_design`, which may or may not close it.

**Cost (all within the host limits; MemAvailable was 12.6-13.9 GB before every job, no OOM, no waiting needed):**

| Job | Wall time | Peak RSS |
|---|---|---|
| CPU-only synthesis | 3:56 | 2.49 GB |
| CPU-only P&R, 10/7 ns | 5:59 | 3.14 GB |
| With GPU, synthesis + P&R in one session, 10/7 ns | 15:08 | 4.07 GB |
| CPU-only P&R, 7/5 ns | 8:31 | 2.83 GB |
| With GPU P&R, 7/5 ns | 12:13 | 3.09 GB |

(Artix-7 for reference [R]: 4:07 + 10:06 CPU-only, 21:23 with GPU. Kintex-7 was faster for the same flow, probably because it met timing
at the first target so the router and `phys_opt` had less to do [A].)

**What this does to the recommendation:** **nothing; section 3 stands (Nexys Video).** Section 3 says to pick the Genesys 2 "only if
fmax turns out to be the problem". Kintex-7 is measurably faster (about 1.7-1.9x), but Artix-7 already gives ~74-107 MHz, a 7-17x
scale factor against the ASIC clocks, which the Artix-7 conclusion above already judged fast enough for firmware validation
and the CDC soak [A, judgement carried over, not re-evaluated], so fmax is not the problem. The Genesys 2 costs about 75 % more
(section 2 [R]) for headroom that was not needed (19 % of its LUTs with the GPU, against 30 % on the XC7A200T; the XC7A200T has
ample margin). The one new input is the GPU-build hold behaviour above, which is a clock-gate design issue, not a part selection issue.

**NOT verified in the Kintex-7 numbers:** a seed sweep or more than one run per build and target (the Artix-7 ~1 ns spread is assumed to
apply, not re-measured); the true fmax of the two domains that still met timing at the tightest target tried (CPU-only fabric
>= 148 MHz); the effect of `phys_opt_design` after routing and non-default directives; fixing or characterising the GPU-build hold
endpoints; pad-level timing, power, any hardware run; the remaining cause analysis for the CPU-only `cpu_clk_i` reset-path limiter
(it is a 1,807-endpoint family, the top three endpoints inspected); the Genesys 2 board itself (pinout, clocks, price) is untouched.

1. Board (recommendation: Nexys Video).
2. Clock-speed sanity check: done for the CPU-only build. ECP5 lower bound ~48-52 MHz CPU, ~47-55 MHz fabric; Artix-7
   XC7A200T-1 in Vivado 2026.1 ~107 MHz CPU, ~83 MHz fabric (above). Kintex-7 XC7K325T-2 (Genesys 2) ~180-190 MHz CPU, ~126 MHz+ fabric (subsection above).
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
