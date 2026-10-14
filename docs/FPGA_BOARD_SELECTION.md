# FPGA board selection (bead `hlrm`, GH #245)

Status: **recommendation, not a purchase decision.** Written 2026-10-14. It builds on the yosys resource counts in
[`FPGA_STAGE0_EVALUATION.md`](FPGA_STAGE0_EVALUATION.md) §2. Neither fmax nor a vendor-tool synthesis has been measured,
so every "fits" below is an estimate.

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

## 6. Open decisions

1. Board (recommendation: Nexys Video).
2. Clock-speed sanity check: install Vivado ML Standard (needs the user's AMD account), run the open-tool ECP5 lower
   bound now, or both.
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
