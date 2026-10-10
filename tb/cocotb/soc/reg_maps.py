"""
reg_maps.py -- the DOCUMENTED register maps the register-walk (reg_walk.py) checks against
(bead claude_verilog_test-7ovx).

Source of truth: docs/design/MEMORY_MAP.md and each module's header comment (register table,
reset values, RO / W1C / W1P / WO classification).  The values here are transcribed from those
documents, NOT read back from the RTL's RESET_VAL / WMASK parameters: a walk that took its
expectations from the RTL it checks could never disagree with it.  A mismatch is therefore
either an RTL bug, a documentation bug, or a transcription error here -- all three are worth a
bead, and the walk reports it instead of adapting.

Every register of every peripheral appears, including the ones the walk does not touch: an
excluded register carries `skip=<reason>` so the exclusion is visible in the test log and in
review, never an unlisted gap.  Reasons use the same few categories throughout:
  FIFO push     a write enqueues data into a FIFO (a later read-back would disagree)
  aperture      a write loads a key / data / weight aperture whose effect is the contract
  command       a write is a command pulse (START, CMD, FEED): side effects by definition
  Everything excluded is covered by the owning peripheral's own suite.

`drive` removes a SIDE-EFFECT BIT from the walked patterns while still walking the rest of its
register (e.g. a watchdog enable, a crypto/NPU START, a PMU power-mode request): the bit is never
driven to 1, so it must read back 0 -- which also proves a W1P bit "reads 0".
"""

from __future__ import annotations

from reg_walk import M32, Reg

RW, RO = "rw", "ro"

# Absolute SoC addresses of each peripheral window (rtl/soc/soc_periph_map_pkg.sv,
# docs/design/MEMORY_MAP.md).
SOC_BASE = {
    "uart": 0x2000_2000,
    "spi": 0x2000_3000,
    "timer": 0x2000_4000,
    "irq": 0x2000_6000,
    "pll1": 0x2000_7000,
    "pmu": 0x2000_8000,
    "pll2": 0x2000_9000,
    "gpio": 0x2000_A000,
    "pwm": 0x2000_B000,
    "wdt": 0x2000_C000,
    "trng": 0x2000_D000,
    "i2c": 0x2000_E000,
    "crypto": 0x2000_F000,
    "npu": 0x2001_0000,
}


def _w(i: int) -> int:
    return 4 * i


# ---------------------------------------------------------------------------------------------
# Timer (rtl/periph/timer.sv header)
# ---------------------------------------------------------------------------------------------
TIMER = [
    # COUNTER is HW-written and runs once CTRL.enable is set, so it is checked strictly (== 0,
    # disabled) in the first pass -- before CTRL is walked -- and not re-read afterwards.
    Reg("TMR_COUNTER", _w(0), reset=0, wmask=0, recheck=False),
    Reg("TMR_COMPARE", _w(1), reset=M32, wmask=M32),
    Reg("TMR_CTRL", _w(2), reset=0, wmask=0x7),            # [0]enable [1]irq_en [2]auto_clear
    Reg("TMR_PRESCALE", _w(3), reset=0, wmask=0xFFFF),
]

# ---------------------------------------------------------------------------------------------
# UART (uart_controller.sv header)
# ---------------------------------------------------------------------------------------------
UART = [
    Reg("UART_TX", _w(0), kind="wo0",
        skip="FIFO push: a write enqueues a TX byte (test_uart owns the TX path)"),
    Reg("UART_RX", _w(1), reset=0, wmask=0),               # RO; a read pops, an empty pop is a no-op
    Reg("UART_STATUS", _w(2), reset=0x0C, wmask=0),        # tx_empty(2) | rx_empty(3) when idle
    Reg("UART_CTRL", _w(3), reset=0, wmask=0x1F),
    Reg("UART_BAUD", _w(4), reset=0, wmask=0xFFFF),
]

# ---------------------------------------------------------------------------------------------
# SPI (spi_controller.sv header)
# ---------------------------------------------------------------------------------------------
SPI = [
    Reg("SPI_TX", _w(0), kind="wo0",
        skip="FIFO push: a write enqueues a TX byte (test_spi owns the transfer path)"),
    Reg("SPI_RX", _w(1), reset=0, wmask=0),
    Reg("SPI_STATUS", _w(2), reset=0x0C, wmask=0),         # tx_empty(2) | rx_empty(3)
    Reg("SPI_CTRL", _w(3), reset=0, wmask=0x1F),
    Reg("SPI_CLK_DIV", _w(4), reset=0, wmask=0xFFFF),
    Reg("SPI_CS_CTRL", _w(5), reset=1, wmask=0x1),
]


# ---------------------------------------------------------------------------------------------
# Interrupt controller (interrupt_controller.sv header); N_SOURCES = 5 standalone, 12 in soc_top.
# ---------------------------------------------------------------------------------------------
def irq_regs(n_sources: int) -> list:
    m = (1 << n_sources) - 1
    return [
        Reg("IRQ_STATUS", _w(0), reset=0, wmask=0),
        Reg("IRQ_MASK", _w(1), reset=0, wmask=m),
        Reg("IRQ_PENDING_MASKED", _w(2), reset=0, wmask=0),
    ]


# ---------------------------------------------------------------------------------------------
# GPIO (gpio_controller.sv header, MEMORY_MAP.md "GPIO Registers"); 32 pins.
# ---------------------------------------------------------------------------------------------
GPIO = [
    Reg("GPIO_DATA_IN", _w(0), reset=0, wmask=0),          # pins driven low by the testbench
    Reg("GPIO_DATA_OUT", _w(1), reset=0, wmask=M32),
    Reg("GPIO_DIR", _w(2), reset=0, wmask=M32),
    Reg("GPIO_IRQ_EN", _w(3), reset=0, wmask=M32),
    Reg("GPIO_IRQ_TYPE", _w(4), reset=0, wmask=M32),
    Reg("GPIO_IRQ_POL", _w(5), reset=0, wmask=M32),
    # Edge-sticky / level-live (MEMORY_MAP.md): with TYPE/POL being walked, the live level bits
    # and any latched edge change by design, so STAT is not compared.  Its RO-ness is covered by
    # the other 31 registers' cross-talk checks and by test_gpio's W1C tests.
    Reg("GPIO_IRQ_STAT", _w(6), reset=0, wmask=0, live=M32),
    Reg("GPIO_IRQ_CLR", _w(7), reset=0, wmask=0, kind="w1c"),  # W1C, always reads 0
]

# ---------------------------------------------------------------------------------------------
# PWM (pwm_controller.sv header, MEMORY_MAP.md "PWM Registers"); 4 channels.
# ---------------------------------------------------------------------------------------------
PWM = [
    Reg("PWM_CTRL", _w(0), reset=0, wmask=0xFF),           # [3:0] enable, [7:4] polarity
    Reg("PWM_PERIOD", _w(1), reset=0, wmask=0xFFFF),
    Reg("PWM_PRESCALE", _w(2), reset=0, wmask=0xFFFF),
    Reg("PWM_DUTY01", _w(3), reset=0, wmask=M32),
    Reg("PWM_DUTY23", _w(4), reset=0, wmask=M32),
    Reg("PWM_IRQ_EN", _w(5), reset=0, wmask=0xF),
    Reg("PWM_IRQ_STAT", _w(6), reset=0, wmask=0),          # sticky wrap; 0 while no channel wrapped
    Reg("PWM_IRQ_CLR", _w(7), reset=0, wmask=0, kind="w1c"),
]

# ---------------------------------------------------------------------------------------------
# Watchdog (watchdog_timer.sv header, MEMORY_MAP.md "WDT Registers")
# ---------------------------------------------------------------------------------------------
WDT = [
    # CTRL[0] (enable) is never driven: enabling starts a down-counter that barks, bites and
    # (RST_EN) can reset the SoC -- test_wdt / test_soc_wdt own that.  [1] RST_EN and [2] window
    # enable are stored, inert while the dog is disabled, and walked.
    Reg("WDT_CTRL", _w(0), reset=0, wmask=0x7, drive=M32 & ~0x1),
    Reg("WDT_RELOAD", _w(1), reset=0, wmask=M32),
    Reg("WDT_COUNT", _w(2), reset=0, wmask=0),             # RO live down-counter, idle (disabled) = 0
    Reg("WDT_WINDOW", _w(3), reset=0, wmask=M32),
    Reg("WDT_FEED", _w(4), kind="wo0",
        skip="command: 0x5A5A_C0DE with pstrb==F feeds the dog (test_wdt owns the feed protocol)"),
    Reg("WDT_PRESCALE", _w(5), reset=0, wmask=0xFFFF),
    Reg("WDT_STATUS", _w(6), reset=0, wmask=0),            # sticky bark/bite/window, none yet
    Reg("WDT_IRQ_CLR", _w(7), reset=0, wmask=0, kind="w1c"),
]

# ---------------------------------------------------------------------------------------------
# TRNG (trng.sv header, MEMORY_MAP.md "TRNG Registers"); LFSR build => STATUS[3] INSECURE = 1.
# ---------------------------------------------------------------------------------------------
TRNG = [
    # CTRL[0] (enable) is never driven: it starts entropy production, fills the FIFO and samples
    # SEED at the 0->1 edge (test_trng owns that).  [1] IRQ enable and [5:2] threshold are walked.
    Reg("TRNG_CTRL", _w(0), reset=0, wmask=0x3F, drive=M32 & ~0x1),
    Reg("TRNG_STATUS", _w(1), reset=0x8, wmask=0),
    Reg("TRNG_DATA", _w(2), reset=0, wmask=0),             # RO, read pops; empty pop is a no-op
    Reg("TRNG_SEED", _w(3), reset=0xACE1_2345, wmask=M32),
    Reg("TRNG_IRQ_CLR", _w(4), reset=0, wmask=0, kind="w1c"),
    Reg("TRNG_RSVD5", _w(5), reset=0, wmask=0, kind="rsvd"),
    Reg("TRNG_RSVD6", _w(6), reset=0, wmask=0, kind="rsvd"),
    Reg("TRNG_RSVD7", _w(7), reset=0, wmask=0, kind="rsvd"),
]

# ---------------------------------------------------------------------------------------------
# I2C (i2c_controller.sv header, MEMORY_MAP.md "I2C Registers")
# ---------------------------------------------------------------------------------------------
I2C = [
    Reg("I2C_CTRL", _w(0), reset=0, wmask=0x0F03),         # [0]EN [1]LOOPBACK [11:8]RX_THR
    # SCL/SDA sensed levels ([5],[6]) follow the external pad, so they are live.
    Reg("I2C_STATUS", _w(1), reset=0x60, wmask=0, live=0x60),
    Reg("I2C_CLKDIV", _w(2), reset=0x00FF, wmask=0xFFFF),
    Reg("I2C_ADDR", _w(3), reset=0, wmask=0xFF),
    Reg("I2C_TX_DATA", _w(4), kind="wo0",
        skip="FIFO push: a write with pstrb[0] pushes a TX byte (test_i2c owns the data path)"),
    Reg("I2C_RX_DATA", _w(5), reset=0, wmask=0),
    Reg("I2C_CMD", _w(6), kind="w1p",
        skip="command: a write with pstrb[0] starts one bus command (test_i2c owns the engine)"),
    Reg("I2C_FIFO_STAT", _w(7), reset=0x0A00, wmask=0),    # tx_empty(9) | rx_empty(11)
    Reg("I2C_TIMEOUT", _w(8), reset=0xFFFF, wmask=0xFFFF),
    Reg("I2C_IRQ_EN", _w(9), reset=0, wmask=0x1F),
    Reg("I2C_IRQ_STAT", _w(10), reset=0, wmask=0),
    Reg("I2C_IRQ_CLR", _w(11), reset=0, wmask=0, kind="w1c"),
]

# ---------------------------------------------------------------------------------------------
# CRYPTO (crypto_accel.sv header, MEMORY_MAP.md "CRYPTO Registers"); 32 words.
# ---------------------------------------------------------------------------------------------
_AP_KEY = "aperture: key words load the shadow key and latch key_valid for good"
_AP_DIN = "aperture: DIN words load the message shadow (write order is the contract)"
CRYPTO = (
    # CTRL[2] START is W1P: never driven (an illegal/legal start is an operation, test_crypto
    # owns it); it must read 0.  [1:0] mode, [3] irq_en, [4] SHA_CONT are walked.
    [Reg("CRYPTO_CTRL", _w(0), reset=0, wmask=0x1B, drive=M32 & ~0x4),
     Reg("CRYPTO_STATUS", _w(1), reset=0, wmask=0)]
    + [Reg(f"CRYPTO_KEY{i}", _w(2 + i), kind="wo0", skip=_AP_KEY) for i in range(4)]
    + [Reg(f"CRYPTO_IV{i}", _w(6 + i), reset=0, wmask=M32) for i in range(4)]
    + [Reg(f"CRYPTO_DIN{i}", _w(10 + i), kind="wo0", skip=_AP_DIN) for i in range(4)]
    + [Reg(f"CRYPTO_DOUT{i}", _w(14 + i), reset=0, wmask=0) for i in range(4)]
    + [Reg(f"CRYPTO_DIGEST{i}", _w(18 + i), reset=0, wmask=0) for i in range(8)]
    + [Reg("CRYPTO_IRQ_STAT", _w(26), reset=0, wmask=0),
       Reg("CRYPTO_IRQ_CLR", _w(27), reset=0, wmask=0, kind="w1c")]
    + [Reg(f"CRYPTO_RSVD{i}", _w(i), reset=0, wmask=0, kind="rsvd") for i in range(28, 32)]
)

# ---------------------------------------------------------------------------------------------
# NPU (npu_top.sv header, MEMORY_MAP.md "NPU Registers"); 16 words.
# ---------------------------------------------------------------------------------------------
NPU = (
    # CTRL[2] START is W1P: never driven, must read 0.  [0] RELU_EN and [3] IRQ_EN are walked.
    [Reg("NPU_CTRL", _w(0), reset=0, wmask=0x9, drive=M32 & ~0x4),
     Reg("NPU_STATUS", _w(1), reset=0x8, wmask=0),          # ain_empty
     Reg("NPU_WADDR", _w(2), reset=0, wmask=0x3FF),
     Reg("NPU_WDATA", _w(3), kind="wo0",
         skip="aperture: a write stores 4 weights at SRAM[WADDR] and auto-increments WADDR"),
     Reg("NPU_TILEBASE", _w(4), reset=0, wmask=0x3FF),
     Reg("NPU_KLEN", _w(5), reset=0, wmask=0x3F),
     Reg("NPU_SCALE", _w(6), reset=0, wmask=0x1F_FFFF),
     Reg("NPU_AIN", _w(7), kind="wo0", skip="FIFO push: a write enqueues an activation word"),
     Reg("NPU_AOUT", _w(8), reset=0, wmask=0),              # RO; read pops, empty pop is a no-op
     Reg("NPU_IRQ_STAT", _w(9), reset=0, wmask=0),
     Reg("NPU_IRQ_CLR", _w(10), reset=0, wmask=0, kind="w1c")]
    + [Reg(f"NPU_RSVD{i}", _w(i), reset=0, wmask=0, kind="rsvd") for i in range(11, 16)]
)

# ---------------------------------------------------------------------------------------------
# PMU (pmu.sv header)
# ---------------------------------------------------------------------------------------------
PMU = [
    # CTRL[1:0] is the power-mode request: any non-zero mode walks a power-down sequence of the
    # CPU and/or GPU domain (test_pmu / test_soc_pmu_multiclock / test_soc_integration own that).
    # The mode field is never driven to non-zero; the other 30 bits are not SW-writable and must
    # stay 0 under all-ones writes.
    Reg("PMU_CTRL", _w(0), reset=0, wmask=0x3, drive=M32 & ~0x3),
    Reg("PMU_STATUS", _w(1), reset=0x3, wmask=0),          # cpu_domain_on | gpu_domain_on
    Reg("PMU_DOMAIN_EN", _w(2), reset=0x33, wmask=0),      # clk_en / rst_n of both domains
]

# ---------------------------------------------------------------------------------------------
# PLL config (pll_apb_regs.sv header): CONTROL / STATUS / RSVD.
# ---------------------------------------------------------------------------------------------
PLL = [
    # CONTROL[0] pll_enable is set-only (GH #89 anti-brick): wmask excludes it, so writing 0 to
    # the register must leave it at 1 -- the walk's zero patterns are exactly that check.
    Reg("PLL_CONTROL", _w(0), reset=0x1, wmask=0x3F0),
    Reg("PLL_STATUS", _w(1), reset=0, wmask=0, live=0x1),  # [0] locked mirrors pll_locked_i
    Reg("PLL_RSVD", _w(2), reset=0, wmask=0, kind="rsvd"),
]

# name -> (register list, first unmapped word index) for the unmapped-window probe.
BANKS = {
    "timer": (TIMER, 4),
    "uart": (UART, 5),
    "spi": (SPI, 6),
    "gpio": (GPIO, 8),
    "pwm": (PWM, 8),
    "wdt": (WDT, 8),
    "trng": (TRNG, 8),
    "i2c": (I2C, 12),
    "crypto": (CRYPTO, 32),
    "npu": (NPU, 16),
    "pmu": (PMU, 3),
    "pll": (PLL, 3),
}

# Registers that receive the FULL pattern set at SoC level (32-bit-wide, so every data bit of the
# fabric buses sees both edges).  Everything else gets the short set -- the SoC walk is slow
# (~100 clocks per access through the CDC bridges and the AXI-Lite ring).
SOC_FULL = {
    "TMR_COMPARE", "GPIO_DATA_OUT", "PWM_DUTY01", "WDT_RELOAD", "TRNG_SEED", "CRYPTO_IV0",
}


def off(regs, name: str) -> int:
    """Byte offset of register `name` in a register list."""
    for r in regs:
        if r.name == name:
            return r.offset
    raise KeyError(name)
