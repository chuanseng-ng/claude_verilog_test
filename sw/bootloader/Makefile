# Makefile -- build the UART boot-ROM bootloader (bead hlrm.2) and its test payload.
#
#   nix develop <repo>#bench --command make -C sw/bootloader            # build all variants
#   nix develop <repo>#bench --command make -C sw/bootloader prebuilt    # refresh prebuilt/ (committed)
#   nix develop <repo>#bench --command make -C sw/bootloader check       # prebuilt/ == fresh build?
#
# Variants (each gets build/<v>/uart_boot.{elf,bin,hex,dis,sym}):
#   default   50 MHz / 115200 (FPGA plan).  This is the image for boot_rom MEM_INIT_FILE.
#   asic40    40 MHz / 115200 (Sky130 SoC, 25 ns period).
#   sim       cocotb build: UART divisor 5, 1 MHz "CPU clock" so timeouts are short in simulation.
#   sim_auto  sim + 5 ms auto-boot window.
# Override anything in bl_config.h with e.g.  make EXTRA_DEFS='-DBL_BAUD=57600 -DBL_SRAM_BYTES=65536'

CROSS   ?= riscv32-none-elf-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
OBJDUMP := $(CROSS)objdump
NM      := $(CROSS)nm
SIZE    := $(CROSS)size

# CPU is RV32I + Zicsr, no M extension.
ARCH    := -march=rv32i_zicsr -mabi=ilp32
CFLAGS  := $(ARCH) -Os -ffreestanding -nostdlib -fno-builtin -fno-tree-loop-distribute-patterns \
           -mno-relax -msmall-data-limit=0 -fno-pic -ffunction-sections -fdata-sections \
           -Wall -Wextra -Werror -I.
# No -lgcc on purpose: the bootloader must not need __mulsi3/__udivsi3 (the link fails if it does).
LDFLAGS := $(ARCH) -nostdlib -nostartfiles -Wl,--gc-sections

BUILD   := build
HEX     := python3 ../bench/bin2hex.py
ROM_LIMIT := 4096

VARIANTS := default asic40 sim sim_auto
DEFS_default  :=
DEFS_asic40   := -DBL_UART_CLK_HZ=40000000u -DBL_CPU_HZ=40000000u
DEFS_sim      := -DBL_UART_DIV=5u -DBL_CPU_HZ=1000000u
DEFS_sim_auto := $(DEFS_sim) -DBL_AUTOBOOT_MS=5u

# Linker-script constants derived from the SRAM geometry (keep in sync with bl_config.h).
SRAM_BASE  := 0x2000
SRAM_BYTES ?= 4096
RAM_BYTES  := 512
RAM_BASE   := $(shell printf "0x%x" $$(($(SRAM_BASE) + $(SRAM_BYTES) - $(RAM_BYTES))))

.PHONY: all prebuilt check clean size
all: $(foreach v,$(VARIANTS),$(BUILD)/$(v)/uart_boot.hex) $(BUILD)/testprog.hex size

.SECONDARY:
.PRECIOUS: $(BUILD)/%.bin

$(BUILD)/%/bootloader.ld: bootloader.ld.in Makefile
	mkdir -p $(dir $@)
	sed -e 's/@RAM_BASE@/$(RAM_BASE)/' \
	    -e 's/@RAM_BYTES@/$(RAM_BYTES)/' $< > $@

$(BUILD)/%/uart_boot.elf: uart_boot.c crt0.S bl_config.h uart_boot_proto.h $(BUILD)/%/bootloader.ld
	$(CC) $(CFLAGS) $(DEFS_$*) $(EXTRA_DEFS) -DBL_SRAM_BYTES=$(SRAM_BYTES)u $(LDFLAGS) \
	    -Wl,-T,$(BUILD)/$*/bootloader.ld -Wl,-Map,$(BUILD)/$*/uart_boot.map -o $@ crt0.S uart_boot.c
	$(NM) -n $@ > $(BUILD)/$*/uart_boot.sym
	$(OBJDUMP) -d $@ > $(BUILD)/$*/uart_boot.dis

$(BUILD)/testprog.elf: testprog.c testprog_table.inc crt0.S testprog.ld
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) -Wl,-T,testprog.ld -o $@ crt0.S testprog.c
	$(OBJDUMP) -d $@ > $(BUILD)/testprog.dis

$(BUILD)/%.bin: $(BUILD)/%.elf
	$(OBJCOPY) -O binary $< $@

$(BUILD)/%.hex: $(BUILD)/%.bin
	$(HEX) $< > $@

size: $(foreach v,$(VARIANTS),$(BUILD)/$(v)/uart_boot.bin)
	@for v in $(VARIANTS); do \
	  n=$$(stat -c %s $(BUILD)/$$v/uart_boot.bin); \
	  echo "$$v: ROM image $$n of $(ROM_LIMIT) bytes"; \
	  test $$n -le $(ROM_LIMIT) || { echo "ERROR: $$v exceeds the 4 KB boot ROM"; exit 1; }; \
	done

# prebuilt/ is what the cocotb tests and the FPGA flow (MEM_INIT_FILE) consume, so they need no toolchain.
prebuilt: all
	mkdir -p prebuilt
	for v in $(VARIANTS); do cp $(BUILD)/$$v/uart_boot.hex prebuilt/uart_boot_$$v.hex; done
	cp $(BUILD)/testprog.hex prebuilt/testprog.hex
	cp $(BUILD)/testprog.bin prebuilt/testprog.bin
	cp $(BUILD)/testprog.elf prebuilt/testprog.elf

check: all
	@for v in $(VARIANTS); do cmp -s $(BUILD)/$$v/uart_boot.hex prebuilt/uart_boot_$$v.hex \
	    || { echo "prebuilt/uart_boot_$$v.hex is STALE: run make prebuilt"; exit 1; }; done
	@cmp -s $(BUILD)/testprog.bin prebuilt/testprog.bin || { echo "prebuilt/testprog.bin is STALE"; exit 1; }
	@echo "prebuilt/ matches a fresh build"

clean:
	rm -rf $(BUILD)
