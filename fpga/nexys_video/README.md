# Nexys Video prototype (bead hlrm.2, epic hlrm, GH #245)

Board: Digilent Nexys Video, XC7A200T-1SBG484C. First build is **with GPU**. Pre-board: nothing here has run on hardware.

| File | Role |
|---|---|
| `nexys_video_top.sv` | board top: MMCM, BUFGs, reset sync, IOBUF/IBUF/OBUF pad wrappers, DFT tie-off, `soc_top` |
| `nexys_video_dbg.sv` | JTAG-to-AXI-Lite master -> `rtl/soc/axil_to_apb.sv` -> `soc_top` APB debug port, one ILA |
| `ip.tcl` | creates `jtag_axi_0`, `ila_0` at build time (no IP binaries are checked in) |
| `clkfix.tcl` | re-sources every PMU-gate `BUFGCE.I` from the MMCM output, parallel with the ungated BUFG |
| `nexys_video.xdc` | pins (Digilent master XDC), IO standards, IO timing |
| `nexys_video_cdc.xdc` | XDC translation of the CDC SDC budgets + `ASYNC_REG` |
| `build.sh`, `build.tcl` | Vivado batch flow: synth, opt, place, phys_opt, route, reports, bitstream |
| `boot_uart.hex`, `boot_uart.manifest.json` | boot ROM image = the UART bootloader of `sw/bootloader` built for this board (generated, drift-gated) |
| `Makefile` | `bootimg` (regenerate image + manifest), `bootimg-check` (committed image == fresh build) |
| `nexys_video_cdc_waivers.tcl` | documented `create_waiver` set applied before `report_cdc`; disposition of every finding: `CDC_TRIAGE.md` |
| `CDC_TRIAGE.md` | triage of the Vivado `report_cdc` Critical findings (bead hlrm.3) |
| `sim/ip_stubs.v` | lint-only black boxes for the IP and unisim primitives (never in a Vivado file list) |

## Clocking

One MMCM off the 100 MHz oscillator (VCO 900 MHz): `clk_sys` 50 MHz -> `clk_i`, `clk_cpu` 75 MHz -> `cpu_clk_i`. Both are
outputs of one MMCM, so they are frequency-locked and do **not** exercise an independent-clock crossing. A later stage adds
an Si5351A on a Pmod/FMC clock-capable pin (`docs/FPGA_BOARD_SELECTION.md` section 4) for the real CDC soak.

## Clock gate

`rv32i_clock_gate` has a `FPGA_BUFGCE` arm (Xilinx `BUFGCE`, CE = `en | test_en`). `clkfix.tcl` places each BUFGCE in
parallel with the ungated BUFG (both fed by the MMCM output) instead of cascading BUFG -> BUFGCE. Simulation and the cocotb
`FPGA=1` regression use the stub `rtl/fpga/sim/BUFGCE.v` (behaviourally identical to the existing latch+AND arm).

## Boot image and host loader (beads hlrm.2, hlrm.4)

`boot_rom` is read-only and loaded through `MEM_INIT_FILE`. `nexys_video_top` takes parameter `BOOT_HEX`, forwarded to
`soc_top.MEM_INIT_FILE`; `build.tcl` passes it as a `synth_design -generic` and prints its word count and sha256 (`NV-BOOT`).
The `FPGA` arm of `boot_rom.sv` runs `$readmemh` under the `__pnr__` build, and Vivado turns it into ROM initialisation.

**The image is `boot_uart.hex`, generated, not hand-written.** It is `sw/bootloader`'s `default` variant built with the
board parameters `SRAM_BYTES=65536` (64 KB SRAM, load window `0x2000..0x11E00`) and `-DBL_CPU_HZ=75000000u` (mcycle counts
the 75 MHz CPU clock; the firmware default assumes 50 MHz). Both are `make` variables of the firmware's own Makefile, so no
firmware source is edited for the board. 405 words = 1620 of 4096 bytes.

```bash
nix develop <repo>#bench --command make -C fpga/nexys_video bootimg         # regenerate boot_uart.hex + manifest
nix develop <repo>#bench --command make -C fpga/nexys_video bootimg-check   # committed hex == fresh build (byte for byte)
python3 tools/fpga/boot_image.py check                                      # no toolchain: sources/params/hex vs manifest (CI)
```

Drift gate: `boot_uart.manifest.json` records the sha256 of every file that feeds the image (bootloader sources, linker script
template, firmware Makefile, `bin2hex.py`), the build parameters, the toolchain and the hex hash. `tools/fpga/boot_image.py
check` runs in the `qa-checks` CI job (no RISC-V toolchain there) and in `build.sh` before Vivado starts, so a bootloader edit
without `make bootimg`, or a hand-edited hex, cannot reach a bitstream. A boot-image-only change needs a new synthesis (the ROM
is part of the bitstream); patching the INIT bits of the routed checkpoint with `updatemem` is a possible speed-up, not done.
`NV_BOOT_HEX=/abs/other.hex build.sh ...` still builds a different image (and skips the gate).

### Loading a program (host side)

After configuring the FPGA the CPU runs the bootloader from ROM, prints `UBL1` and waits for frames on the FT2232 UART
(`uart_rx_out` is the FPGA transmit line). SRAM is empty after configuration, so the bootloader waits forever by default.

```bash
python3 tools/fw/uart_load.py /dev/ttyUSB1 --info                       # ping: version, block size, load window
python3 tools/fw/uart_load.py /dev/ttyUSB1 firmware.elf                 # load segments, CRC-verify each, jump to the ELF entry
python3 tools/fw/uart_load.py /dev/ttyUSB1 firmware.bin --addr 0x2000   # flat binary
```

The Nexys Video FT2232 enumerates two ports; the UART is the second one (usually `/dev/ttyUSB1`). Firmware must be linked into
the window `--info` reports (`0x2000..0x11E00`, i.e. a 64 KB SRAM layout, not `sw/bench/rv32i.ld`'s default). Reset the board
(CPU_RESET button) to get back to the bootloader.

**8N2 on the host (bead shm5, RTL finding, not fixed here).** `uart_controller`'s receiver mis-frames the 8th or so back-to-back
8N1 byte (it re-aligns one oversample tick late after every byte). The bootloader is unchanged and correct; the *host* must send
two stop bits. `uart_load.py` does that by default (`--stopbits 2`), at a 10 % throughput cost (11 bit times per byte, about
10.5 KB/s at 115200 baud). Do not use a terminal program or `--stopbits 1` to talk to the bootloader until shm5 is fixed in RTL;
the target's transmit side is plain 8N1 and reads fine with any terminal. The FT2232 supports 2 stop bits. Not measured on a
board (none available): simulation covers the same sequence in `make -C tb/cocotb/soc soc_uart_boot`.

## Pins

`gpio[7:0]` LEDs, `gpio[15:8]` switches, `gpio[20:16]` buttons, `gpio[28:21]` Pmod JC. Pmod JA: SPI `cs_n/mosi/miso/sclk`
on pins 1-4, PWM on pins 7-10. Pmod JB: I2C on pins 1-2 (internal pull-up only; fit external pull-ups), status LEDs/probes
on the rest. UART: `uart_rx_out` is the FPGA transmit line.

## Debug

`open_hw_manager`, connect, program the bitstream. `hw_axi_1` (the JTAG-to-AXI master) reads/writes the CPU debug APB space
(12-bit address): this is the CPU debug port, not the peripheral map. The single ILA `ila_0` (75 MHz CPU clock; the free Vivado licence allows one ILA core) probes the APB debug bus, UART, IRQ and lock flags (system domain, oversampled) and the commit valid/PC/instruction.

## DFT

Tied off at the top: `scan_mode/scan_en = 0`, `scan_rst_n = 1`, `scan_clk`/`tck` = 0, `tms` = 1, `trst_n` = 0 (TAP held in
reset). Escalation path if Vivado reports TIMING-14 on the DFT clock muxes after constant propagation: an `FPGA`-define
bypass of `dft_clk_mux`/`dft_rst_mux`/`dft_clk_switch`. See the build report for the count.
