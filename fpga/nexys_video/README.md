# Nexys Video prototype (bead hlrm.2, epic hlrm, GH #245)

Board: Digilent Nexys Video, XC7A200T-1SBG484C. First build is **with GPU**. Pre-board: nothing here has run on hardware.

| File | Role |
|---|---|
| `nexys_video_top.sv` | board top: MMCM, BUFGs, reset sync, IOBUF/IBUF/OBUF pad wrappers, DFT tie-off, `soc_top` |
| `nexys_video_dbg.sv` | JTAG-to-AXI-Lite master -> `rtl/soc/axil_to_apb.sv` -> `soc_top` APB debug port, two ILAs |
| `ip.tcl` | creates `jtag_axi_0`, `ila_sys_0`, `ila_cpu_0` at build time (no IP binaries are checked in) |
| `clkfix.tcl` | re-sources every PMU-gate `BUFGCE.I` from the MMCM output, parallel with the ungated BUFG |
| `nexys_video.xdc` | pins (Digilent master XDC), IO standards, IO timing |
| `nexys_video_cdc.xdc` | XDC translation of the CDC SDC budgets + `ASYNC_REG` |
| `build.sh`, `build.tcl` | Vivado batch flow: synth, opt, place, phys_opt, route, reports, bitstream |
| `boot_placeholder.hex` | placeholder boot ROM image (`jal x0,0` then NOPs) |
| `sim/ip_stubs.v` | lint-only black boxes for the IP and unisim primitives (never in a Vivado file list) |

## Clocking

One MMCM off the 100 MHz oscillator (VCO 900 MHz): `clk_sys` 50 MHz -> `clk_i`, `clk_cpu` 75 MHz -> `cpu_clk_i`. Both are
outputs of one MMCM, so they are frequency-locked and do **not** exercise an independent-clock crossing. A later stage adds
an Si5351A on a Pmod/FMC clock-capable pin (`docs/FPGA_BOARD_SELECTION.md` section 4) for the real CDC soak.

## Clock gate

`rv32i_clock_gate` has a `FPGA_BUFGCE` arm (Xilinx `BUFGCE`, CE = `en | test_en`). `clkfix.tcl` places each BUFGCE in
parallel with the ungated BUFG (both fed by the MMCM output) instead of cascading BUFG -> BUFGCE. Simulation and the cocotb
`FPGA=1` regression use the stub `rtl/fpga/sim/BUFGCE.v` (behaviourally identical to the existing latch+AND arm).

## Boot image hand-off (firmware agent -> this board)

`boot_rom` is read-only and loaded through `MEM_INIT_FILE`. `nexys_video_top` takes parameter `BOOT_HEX`, forwarded to
`soc_top.MEM_INIT_FILE`; `build.tcl` passes `NV_BOOT_HEX` as a `synth_design -generic`. The `FPGA` arm of `boot_rom.sv`
runs `$readmemh` under the `__pnr__` build, and Vivado turns it into ROM initialisation.

1. Firmware builds the UART bootloader to a `$readmemh` text file: one 32-bit word per line, 8 hex digits, word 0 at ROM
   offset 0 (CPU address `0x0000_1000`), at most 1024 words (`MEM_WORDS`, 4 KB).
2. `NV_BOOT_HEX=/abs/path/bootloader.hex fpga/nexys_video/build.sh <out> all <tag>`.
3. The bootloader loads the application into SRAM (`0x0000_2000` upward, 64 KB on this board: `SRAM_WORDS` = 16384).

A boot-image-only change needs a new synthesis (the ROM is part of the bitstream). Patching the INIT bits of the routed
checkpoint with `updatemem` is a possible speed-up and is not done here.

## Pins

`gpio[7:0]` LEDs, `gpio[15:8]` switches, `gpio[20:16]` buttons, `gpio[28:21]` Pmod JC. Pmod JA: SPI `cs_n/mosi/miso/sclk`
on pins 1-4, PWM on pins 7-10. Pmod JB: I2C on pins 1-2 (internal pull-up only; fit external pull-ups), status LEDs/probes
on the rest. UART: `uart_rx_out` is the FPGA transmit line.

## Debug

`open_hw_manager`, connect, program the bitstream. `hw_axi_1` (the JTAG-to-AXI master) reads/writes the CPU debug APB space
(12-bit address): this is the CPU debug port, not the peripheral map. ILA `ila_sys_0` (50 MHz: APB debug bus, UART, IRQ and
lock flags) and `ila_cpu_0` (75 MHz: commit valid/PC/instruction) appear in the hardware manager.

## DFT

Tied off at the top: `scan_mode/scan_en = 0`, `scan_rst_n = 1`, `scan_clk`/`tck` = 0, `tms` = 1, `trst_n` = 0 (TAP held in
reset). Escalation path if Vivado reports TIMING-14 on the DFT clock muxes after constant propagation: an `FPGA`-define
bypass of `dft_clk_mux`/`dft_rst_mux`/`dft_clk_switch`. See the build report for the count.
