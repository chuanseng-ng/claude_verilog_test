# Makefile — build SoC cache benchmarks for the RV32I SoC (Phase 5 M10).
#
# Run inside the nix bench devshell:
#   nix develop ~/Downloads/Github/claude_verilog_test#bench --command make -C sw/bench
#
# Outputs per program <p>: build/<p>.elf, build/<p>.bin, build/<p>.hex (SRAM image,
# loaded at 0x2000) plus the shared build/trampoline.hex (ROM image at 0x1000).
# build/<p>.sym lists symbol addresses so the harness can resolve __result /
# BENCH_SCRATCH_ADDR placement.

CROSS   ?= riscv32-none-elf-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
OBJDUMP := $(CROSS)objdump
NM      := $(CROSS)nm

ARCH    := -march=rv32i_zicsr -mabi=ilp32   # CPU is RV32I + Zicsr (Phase 2); csrr needs zicsr
# Freestanding bare-metal; -O2 for representative code; keep frame for clarity.
CFLAGS  := $(ARCH) -O2 -ffreestanding -nostdlib -fno-builtin -Wall -Wextra \
           -ffunction-sections -fdata-sections -I.
LDFLAGS := $(ARCH) -nostdlib -nostartfiles -Wl,--gc-sections -Wl,-T,rv32i.ld

BUILD   := build
CRT0    := crt0.S

# Benchmark programs = every .c here except headers. Add dhrystone.c/coremark.c/
# sweep.c (A3) and they build automatically.
PROGS   := $(patsubst %.c,%,$(wildcard *.c))
HEXES   := $(addprefix $(BUILD)/,$(addsuffix .hex,$(PROGS)))

.PHONY: all clean
all: $(BUILD)/trampoline.hex $(HEXES)

# Keep .elf/.bin — the cocotb harness resolves symbol addresses from the .elf.
.PRECIOUS: $(BUILD)/%.elf $(BUILD)/%.bin
.SECONDARY:

$(BUILD):
	mkdir -p $(BUILD)

# ROM trampoline (standalone, no crt0/linker map — 2 instructions at 0x1000).
$(BUILD)/trampoline.elf: trampoline.S | $(BUILD)
	$(CC) $(ARCH) -nostdlib -nostartfiles -Wl,-Ttext=0x1000 -o $@ $<

$(BUILD)/%.hex: $(BUILD)/%.bin
	python3 bin2hex.py $< > $@

$(BUILD)/%.bin: $(BUILD)/%.elf
	$(OBJCOPY) -O binary $< $@

# Each benchmark links crt0 + program with the SRAM linker map.
$(BUILD)/%.elf: %.c $(CRT0) rv32i.ld bench.h | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(CRT0) $<
	$(NM) -n $@ > $(BUILD)/$*.sym
	$(OBJDUMP) -d $@ > $(BUILD)/$*.dis

clean:
	rm -rf $(BUILD)
