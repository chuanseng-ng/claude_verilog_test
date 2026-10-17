// nexys_video_top.sv -- Digilent Nexys Video (XC7A200T-1SBG484C) board top for soc_top (bead hlrm.2, GH #245).
//
// FPGA-only file: nothing under rtl/ instantiates it. Vendor primitives (MMCME2_BASE, BUFG, IBUF/IOBUF, IP cores)
// appear ONLY under fpga/. Build: fpga/nexys_video/build.sh (defines FPGA, __pnr__, FPGA_BUFGCE).
//
// CLOCKING (one MMCM, VCO = 100 MHz x 9 = 900 MHz, inside the -1 range 600..1200 MHz):
//   clk_sys = 900/18 = 50 MHz -> soc_top.clk_i      (fabric / bus / peripherals / GPU, PMU-gated copy for the GPU)
//   clk_cpu = 900/12 = 75 MHz -> soc_top.cpu_clk_i  (CPU domain, PMU-gated copy for the CPU)
// Both are outputs of ONE MMCM, so they are frequency-locked: they exercise the async_axi_fifo / apb_cdc_bridge
// structure but NOT an independent-clock crossing. The independent-clock CDC soak (Si5351A, FPGA_BOARD_SELECTION.md
// section 4) is a later stage.
// Each ungated clock goes MMCM -> explicit BUFG. The PMU clock gates are BUFGCE primitives (rv32i_clock_gate,
// FPGA_BUFGCE arm). nexys_video_clkfix.tcl re-sources every BUFGCE.I pin from the MMCM output, IN PARALLEL with the
// ungated BUFG, instead of cascading BUFG -> BUFGCE (a cascade puts the gated domain a full buffer later).
//
// DFT: tied off here (decision hlrm.2 #2): scan_mode/scan_en = 0, scan_clk and TCK held low, TMS high, TRST_N asserted.
//
// DEBUG: Xilinx JTAG-to-AXI (AXI4-Lite) -> axil_to_apb -> soc_top APB debug port, plus two ILAs (nexys_video_dbg.sv).
//
// PIN MAP (Digilent Nexys Video master XDC names where a board resource exists):
//   gpio[7:0]   LEDs (output, read back)   gpio[15:8] slide switches   gpio[20:16] {btnu,btnr,btnl,btnd,btnc}
//   gpio[28:21] Pmod JC[7:0] (IOBUF)       gpio[31:29] unused (read 0)
//   Pmod JA: [3:0] SPI cs_n, mosi, miso, sclk   [7:4] PWM[3:0]
//   Pmod JB: [1:0] I2C scl, sda (IOBUF, internal pull-up; fit external 4.7k for 400 kHz)  [7:2] status_o[5:0]
//   UART: uart_rx_out = FPGA TX into the FT2232 (soc uart_tx_o); uart_tx_in = FPGA RX from the FT2232 (soc uart_rx_i)
module nexys_video_top #(
    // Boot ROM image ($readmemh text, one 32-bit word per line). Passed as a synth_design generic by build.tcl.
    parameter string BOOT_HEX = "",
    // Behavioural SRAM depth in words; 16384 = 64 KB (block RAM via the FPGA arm of sram_controller).
    parameter int unsigned SRAM_WORDS = 16384
) (
    input  logic       clk,          // 100 MHz oscillator, R4 (MRCC)
    input  logic       cpu_resetn,   // active-low push button
    output logic [7:0] led,
    input  logic [7:0] sw,
    input  logic       btnc,
    input  logic       btnd,
    input  logic       btnl,
    input  logic       btnr,
    input  logic       btnu,
    output logic       uart_rx_out,
    input  logic       uart_tx_in,
    output logic       spi_cs_n,
    output logic       spi_mosi,
    input  logic       spi_miso,
    output logic       spi_sclk,
    output logic [3:0] pwm,
    inout  wire        i2c_scl,
    inout  wire        i2c_sda,
    output logic [5:0] status_o,
    inout  wire  [7:0] gpio_pmod
);
    // ---------------------------------------------------------------- clocks
    logic clk_ibuf, mmcm_fb, mmcm_locked;
    logic sys_raw, cpu_raw;      // MMCM outputs, before the BUFGs (the BUFGCE.I pins are re-sourced from these)
    logic clk_sys, clk_cpu;      // global clocks (ungated)

    IBUF u_clk_ibuf (.I(clk), .O(clk_ibuf));

    MMCME2_BASE #(
        .BANDWIDTH        ("OPTIMIZED"),
        .CLKIN1_PERIOD    (10.0),
        .DIVCLK_DIVIDE    (1),
        .CLKFBOUT_MULT_F  (9.0),
        .CLKOUT0_DIVIDE_F (18.0),
        .CLKOUT1_DIVIDE   (12),
        .STARTUP_WAIT     ("FALSE")
    ) u_mmcm (
        .CLKIN1   (clk_ibuf),
        .CLKFBIN  (mmcm_fb),
        .CLKFBOUT (mmcm_fb),
        .CLKOUT0  (sys_raw),
        .CLKOUT1  (cpu_raw),
        .LOCKED   (mmcm_locked),
        .PWRDWN   (1'b0),
        .RST      (1'b0),
        /* verilator lint_off PINCONNECTEMPTY */
        .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
        .CLKOUT4(), .CLKOUT5(), .CLKOUT6()
        /* verilator lint_on PINCONNECTEMPTY */
    );

    (* DONT_TOUCH = "TRUE" *) BUFG u_bufg_sys (.I(sys_raw), .O(clk_sys));
    (* DONT_TOUCH = "TRUE" *) BUFG u_bufg_cpu (.I(cpu_raw), .O(clk_cpu));

    // ---------------------------------------------------------------- resets
    // Asynchronous assert (button or MMCM unlocked), synchronous release in each domain.
    logic rst_async_n, rst_async_n_pin;
    IBUF u_rst_ibuf (.I(cpu_resetn), .O(rst_async_n_pin));
    assign rst_async_n = rst_async_n_pin & mmcm_locked;

    (* ASYNC_REG = "TRUE" *) logic [1:0] sys_rst_q;
    (* ASYNC_REG = "TRUE" *) logic [1:0] cpu_rst_q;
    always_ff @(posedge clk_sys or negedge rst_async_n)
        if (!rst_async_n) sys_rst_q <= 2'b00; else sys_rst_q <= {sys_rst_q[0], 1'b1};
    always_ff @(posedge clk_cpu or negedge rst_async_n)
        if (!rst_async_n) cpu_rst_q <= 2'b00; else cpu_rst_q <= {cpu_rst_q[0], 1'b1};
    logic sys_rst_n, cpu_rst_n;
    assign sys_rst_n = sys_rst_q[1];
    assign cpu_rst_n = cpu_rst_q[1];

    // ---------------------------------------------------------------- GPIO / pad wrappers
    logic [31:0] gpio_out, gpio_oe, gpio_in;
    logic [7:0]  led_q;
    logic [7:0]  pmod_i;
    logic        uart_tx_o, uart_rx_i, spi_miso_i;

    assign led_q = gpio_out[7:0] & gpio_oe[7:0];
    for (genvar i = 0; i < 8; i++) begin : g_led
        OBUF u_led_obuf (.I(led_q[i]), .O(led[i]));
    end
    logic [7:0] sw_i;
    for (genvar i = 0; i < 8; i++) begin : g_sw
        IBUF u_sw_ibuf (.I(sw[i]), .O(sw_i[i]));
    end
    logic btnc_i, btnd_i, btnl_i, btnr_i, btnu_i;
    IBUF u_btnc (.I(btnc), .O(btnc_i));
    IBUF u_btnd (.I(btnd), .O(btnd_i));
    IBUF u_btnl (.I(btnl), .O(btnl_i));
    IBUF u_btnr (.I(btnr), .O(btnr_i));
    IBUF u_btnu (.I(btnu), .O(btnu_i));
    for (genvar i = 0; i < 8; i++) begin : g_pmod
        IOBUF u_pmod_iobuf (.IO(gpio_pmod[i]), .I(gpio_out[21+i]), .T(~gpio_oe[21+i]), .O(pmod_i[i]));
    end
    assign gpio_in = {3'b000, pmod_i, btnu_i, btnr_i, btnl_i, btnd_i, btnc_i, sw_i, led_q};

    // I2C: open-drain; the controller's *_o is the pad level when *_oe is set.
    logic scl_o, scl_oe, scl_i, sda_o, sda_oe, sda_i;
    IOBUF u_scl (.IO(i2c_scl), .I(scl_o), .T(~scl_oe), .O(scl_i));
    IOBUF u_sda (.IO(i2c_sda), .I(sda_o), .T(~sda_oe), .O(sda_i));

    logic spi_cs_n_o, spi_mosi_o, spi_sclk_o;
    logic [3:0] pwm_o;
    OBUF u_uart_tx (.I(uart_tx_o),  .O(uart_rx_out));
    IBUF u_uart_rx (.I(uart_tx_in), .O(uart_rx_i));
    IBUF u_spi_mi  (.I(spi_miso),   .O(spi_miso_i));
    // SPI and PWM outputs are combinational off the peripheral state (PWM compare, SPI FSM decode): 8.4 ns of logic plus
    // ~3.7 ns of clock insertion against a 10 ns output budget failed by up to -2.3 ns (measured, nv5). One output flop per
    // pad, placed in the IOB, makes the pad path a clk->Q + OBUF. All seven pads move together (one clk_sys of delay), so
    // the SPI cs_n/mosi/sclk phase relation is unchanged; the serial rates are far below clk_sys.
    /* verilator lint_off PROCASSINIT */
    (* IOB = "TRUE" *) logic [6:0] pad_q = 7'b100_0000;   // power-up: cs_n high, everything else low (FPGA-only file)
    /* verilator lint_on PROCASSINIT */
    always_ff @(posedge clk_sys) pad_q <= {spi_cs_n_o, spi_mosi_o, spi_sclk_o, pwm_o};
    OBUF u_spi_cs (.I(pad_q[6]), .O(spi_cs_n));
    OBUF u_spi_mo (.I(pad_q[5]), .O(spi_mosi));
    OBUF u_spi_sc (.I(pad_q[4]), .O(spi_sclk));
    for (genvar i = 0; i < 4; i++) begin : g_pwm
        OBUF u_pwm_obuf (.I(pad_q[i]), .O(pwm[i]));
    end

    // ---------------------------------------------------------------- debug path
    logic [11:0] apb_paddr;
    logic        apb_psel, apb_penable, apb_pwrite;
    logic [31:0] apb_pwdata, apb_prdata;
    logic        apb_pready, apb_pslverr;
    logic        commit_valid;
    logic [31:0] commit_pc, commit_insn;
    logic        wdt_rst_req, gpu_irq, pll_locked, cpu_pll_locked;

    nexys_video_dbg u_dbg (
        .clk_sys_i        (clk_sys),
        .rst_sys_n_i      (sys_rst_n),
        .clk_cpu_i        (clk_cpu),
        .apb_paddr_o      (apb_paddr),
        .apb_psel_o       (apb_psel),
        .apb_penable_o    (apb_penable),
        .apb_pwrite_o     (apb_pwrite),
        .apb_pwdata_o     (apb_pwdata),
        .apb_prdata_i     (apb_prdata),
        .apb_pready_i     (apb_pready),
        .apb_pslverr_i    (apb_pslverr),
        .uart_tx_i        (uart_tx_o),
        .uart_rx_i        (uart_rx_i),
        .gpu_irq_i        (gpu_irq),
        .wdt_rst_req_i    (wdt_rst_req),
        .pll_locked_i     (pll_locked),
        .cpu_pll_locked_i (cpu_pll_locked),
        .commit_valid_i   (commit_valid),
        .commit_pc_i      (commit_pc),
        .commit_insn_i    (commit_insn)
    );

    // ---------------------------------------------------------------- status pins (Pmod JB[7:2])
    logic [5:0] status_q;
    assign status_q = {sys_rst_n, mmcm_locked, cpu_pll_locked, pll_locked, gpu_irq, wdt_rst_req};
    for (genvar i = 0; i < 6; i++) begin : g_status
        OBUF u_status_obuf (.I(status_q[i]), .O(status_o[i]));
    end

    // ---------------------------------------------------------------- the SoC
    /* verilator lint_off PINCONNECTEMPTY */
    soc_top #(
        .MEM_INIT_FILE  (BOOT_HEX),
        .SRAM_MEM_WORDS (SRAM_WORDS)
    ) u_soc (
        .clk_i            (clk_sys),
        .rst_n_i          (sys_rst_n),
        .cpu_clk_i        (clk_cpu),
        .cpu_rst_n_i      (cpu_rst_n),
        .apb_paddr_i      (apb_paddr),
        .apb_psel_i       (apb_psel),
        .apb_penable_i    (apb_penable),
        .apb_pwrite_i     (apb_pwrite),
        .apb_pwdata_i     (apb_pwdata),
        .apb_prdata_o     (apb_prdata),
        .apb_pready_o     (apb_pready),
        .apb_pslverr_o    (apb_pslverr),
        .uart_tx_o        (uart_tx_o),
        .uart_rx_i        (uart_rx_i),
        .spi_sclk_o       (spi_sclk_o),
        .spi_mosi_o       (spi_mosi_o),
        .spi_miso_i       (spi_miso_i),
        .spi_cs_n_o       (spi_cs_n_o),
        .gpio_out_o       (gpio_out),
        .gpio_oe_o        (gpio_oe),
        .gpio_in_i        (gpio_in),
        .pwm_o            (pwm_o),
        .wdt_rst_req_o    (wdt_rst_req),
        .i2c_scl_o        (scl_o),
        .i2c_scl_oe_o     (scl_oe),
        .i2c_scl_i        (scl_i),
        .i2c_sda_o        (sda_o),
        .i2c_sda_oe_o     (sda_oe),
        .i2c_sda_i        (sda_i),
        .commit_valid_o   (commit_valid),
        .commit_pc_o      (commit_pc),
        .commit_insn_o    (commit_insn),
        .gpu_irq_o        (gpu_irq),
        .pll_locked_o     (pll_locked),
        .cpu_pll_locked_o (cpu_pll_locked),
        // DFT tie-off (decision hlrm.2 #2)
        .scan_mode_i      (1'b0),
        .scan_en_i        (1'b0),
        .scan_rst_ni      (1'b1),
        .scan_clk_i       (1'b0),
        .scan_in_i        ('0),
        .scan_out_o       (),
        .tck_i            (1'b0),
        .tms_i            (1'b1),
        .tdi_i            (1'b0),
        .trst_ni          (1'b0),
        .tdo_o            (),
        .tdo_oe_o         ()
    );
    /* verilator lint_on PINCONNECTEMPTY */
endmodule
