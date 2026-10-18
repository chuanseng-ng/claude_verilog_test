## nexys_video.xdc -- pins, IO standards and IO timing for nexys_video_top (bead hlrm.2).
## Pin locations and standards are taken from the Digilent Nexys-Video-Master.xdc (Rev. A); names follow the top's ports.
## Board resources keep their Digilent port names (clk, cpu_resetn, led, sw, btn*, uart_*); Pmod pins are named by function.

set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property CFGBVS VCCO [current_design]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 4 [current_design]
set_property CONFIG_MODE SPIx4 [current_design]

## 100 MHz oscillator (MRCC). The MMCM outputs are derived clocks and are named by Vivado.
set_property -dict { PACKAGE_PIN R4 IOSTANDARD LVCMOS33 } [get_ports clk]
create_clock -name sys_clk_pin -period 10.000 -waveform {0 5} [get_ports clk]

## CPU RESET button (active low) and the slow human inputs
set_property -dict { PACKAGE_PIN G4 IOSTANDARD LVCMOS15 } [get_ports cpu_resetn]

set_property -dict { PACKAGE_PIN T14 IOSTANDARD LVCMOS25 } [get_ports {led[0]}]
set_property -dict { PACKAGE_PIN T15 IOSTANDARD LVCMOS25 } [get_ports {led[1]}]
set_property -dict { PACKAGE_PIN T16 IOSTANDARD LVCMOS25 } [get_ports {led[2]}]
set_property -dict { PACKAGE_PIN U16 IOSTANDARD LVCMOS25 } [get_ports {led[3]}]
set_property -dict { PACKAGE_PIN V15 IOSTANDARD LVCMOS25 } [get_ports {led[4]}]
set_property -dict { PACKAGE_PIN W16 IOSTANDARD LVCMOS25 } [get_ports {led[5]}]
set_property -dict { PACKAGE_PIN W15 IOSTANDARD LVCMOS25 } [get_ports {led[6]}]
set_property -dict { PACKAGE_PIN Y13 IOSTANDARD LVCMOS25 } [get_ports {led[7]}]

set_property -dict { PACKAGE_PIN E22 IOSTANDARD LVCMOS12 } [get_ports {sw[0]}]
set_property -dict { PACKAGE_PIN F21 IOSTANDARD LVCMOS12 } [get_ports {sw[1]}]
set_property -dict { PACKAGE_PIN G21 IOSTANDARD LVCMOS12 } [get_ports {sw[2]}]
set_property -dict { PACKAGE_PIN G22 IOSTANDARD LVCMOS12 } [get_ports {sw[3]}]
set_property -dict { PACKAGE_PIN H17 IOSTANDARD LVCMOS12 } [get_ports {sw[4]}]
set_property -dict { PACKAGE_PIN J16 IOSTANDARD LVCMOS12 } [get_ports {sw[5]}]
set_property -dict { PACKAGE_PIN K13 IOSTANDARD LVCMOS12 } [get_ports {sw[6]}]
set_property -dict { PACKAGE_PIN M17 IOSTANDARD LVCMOS12 } [get_ports {sw[7]}]

set_property -dict { PACKAGE_PIN B22 IOSTANDARD LVCMOS12 } [get_ports btnc]
set_property -dict { PACKAGE_PIN D22 IOSTANDARD LVCMOS12 } [get_ports btnd]
set_property -dict { PACKAGE_PIN C22 IOSTANDARD LVCMOS12 } [get_ports btnl]
set_property -dict { PACKAGE_PIN D14 IOSTANDARD LVCMOS12 } [get_ports btnr]
set_property -dict { PACKAGE_PIN F15 IOSTANDARD LVCMOS12 } [get_ports btnu]

## USB-UART (FT2232HQ). uart_rx_out is the FPGA transmit line, uart_tx_in the FPGA receive line (board naming).
set_property -dict { PACKAGE_PIN AA19 IOSTANDARD LVCMOS33 } [get_ports uart_rx_out]
set_property -dict { PACKAGE_PIN V18  IOSTANDARD LVCMOS33 } [get_ports uart_tx_in]

## Pmod JA: SPI on JA1..JA4 (pins 1-4 of the connector), PWM on JA7..JA10
set_property -dict { PACKAGE_PIN AB22 IOSTANDARD LVCMOS33 } [get_ports spi_cs_n]
set_property -dict { PACKAGE_PIN AB21 IOSTANDARD LVCMOS33 } [get_ports spi_mosi]
set_property -dict { PACKAGE_PIN AB20 IOSTANDARD LVCMOS33 } [get_ports spi_miso]
set_property -dict { PACKAGE_PIN AB18 IOSTANDARD LVCMOS33 } [get_ports spi_sclk]
set_property -dict { PACKAGE_PIN Y21  IOSTANDARD LVCMOS33 } [get_ports {pwm[0]}]
set_property -dict { PACKAGE_PIN AA21 IOSTANDARD LVCMOS33 } [get_ports {pwm[1]}]
set_property -dict { PACKAGE_PIN AA20 IOSTANDARD LVCMOS33 } [get_ports {pwm[2]}]
set_property -dict { PACKAGE_PIN AA18 IOSTANDARD LVCMOS33 } [get_ports {pwm[3]}]

## Pmod JB: I2C on JB1/JB2 (internal pull-ups; fit external 4.7k for 400 kHz), status on the other six pins
set_property -dict { PACKAGE_PIN V9 IOSTANDARD LVCMOS33 PULLUP true } [get_ports i2c_scl]
set_property -dict { PACKAGE_PIN V8 IOSTANDARD LVCMOS33 PULLUP true } [get_ports i2c_sda]
set_property -dict { PACKAGE_PIN V7 IOSTANDARD LVCMOS33 } [get_ports {status_o[0]}]
set_property -dict { PACKAGE_PIN W7 IOSTANDARD LVCMOS33 } [get_ports {status_o[1]}]
set_property -dict { PACKAGE_PIN W9 IOSTANDARD LVCMOS33 } [get_ports {status_o[2]}]
set_property -dict { PACKAGE_PIN Y9 IOSTANDARD LVCMOS33 } [get_ports {status_o[3]}]
set_property -dict { PACKAGE_PIN Y8 IOSTANDARD LVCMOS33 } [get_ports {status_o[4]}]
set_property -dict { PACKAGE_PIN Y7 IOSTANDARD LVCMOS33 } [get_ports {status_o[5]}]

## Pmod JC: gpio[28:21]
set_property -dict { PACKAGE_PIN Y6  IOSTANDARD LVCMOS33 } [get_ports {gpio_pmod[0]}]
set_property -dict { PACKAGE_PIN AA6 IOSTANDARD LVCMOS33 } [get_ports {gpio_pmod[1]}]
set_property -dict { PACKAGE_PIN AA8 IOSTANDARD LVCMOS33 } [get_ports {gpio_pmod[2]}]
set_property -dict { PACKAGE_PIN AB8 IOSTANDARD LVCMOS33 } [get_ports {gpio_pmod[3]}]
set_property -dict { PACKAGE_PIN R6  IOSTANDARD LVCMOS33 } [get_ports {gpio_pmod[4]}]
set_property -dict { PACKAGE_PIN T6  IOSTANDARD LVCMOS33 } [get_ports {gpio_pmod[5]}]
set_property -dict { PACKAGE_PIN AB7 IOSTANDARD LVCMOS33 } [get_ports {gpio_pmod[6]}]
set_property -dict { PACKAGE_PIN AB6 IOSTANDARD LVCMOS33 } [get_ports {gpio_pmod[7]}]

## ---------------------------------------------------------------- IO timing
## Human-speed and asynchronous pins (reset button, switches, buttons, LEDs, status, UART, I2C open-drain, Pmod GPIO) are
## cut: they are re-synchronised inside the SoC (cdc_sync per GPIO pin, uart/i2c input synchronisers) or are level
## indicators. SPI and PWM are fabric-launched/captured on the system clock with a loose 10 ns external budget: the serial
## rates are <= a few MHz, so this reports the pad skew and hold margin without pretending to be a board-level analysis.
set nv_sys [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]]
set_false_path -from [get_ports {cpu_resetn sw[*] btnc btnd btnl btnr btnu uart_tx_in i2c_scl i2c_sda gpio_pmod[*]}]
set_false_path -to   [get_ports {led[*] status_o[*] uart_rx_out i2c_scl i2c_sda gpio_pmod[*]}]
set_input_delay  -clock $nv_sys -max 10.0 [get_ports spi_miso]
set_input_delay  -clock $nv_sys -min 0.0  [get_ports spi_miso]
set_output_delay -clock $nv_sys -max 10.0 [get_ports {spi_cs_n spi_mosi spi_sclk pwm[*]}]
set_output_delay -clock $nv_sys -min -2.0 [get_ports {spi_cs_n spi_mosi spi_sclk pwm[*]}]
