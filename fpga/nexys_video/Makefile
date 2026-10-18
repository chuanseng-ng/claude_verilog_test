# Makefile -- boot image for the Nexys Video prototype (bead hlrm.4).
#
#   nix develop <repo>#bench --command make -C fpga/nexys_video bootimg         # rebuild boot_uart.hex + manifest from sw/bootloader
#   nix develop <repo>#bench --command make -C fpga/nexys_video bootimg-check   # committed image == a fresh build? (needs the RISC-V toolchain)
#   python3 tools/fpga/boot_image.py check                                      # toolchain-free staleness gate (what CI runs)
#
# The image is sw/bootloader's `default` variant built for this board: the board SRAM is 64 KB (SRAM_WORDS = 16384, so the load
# window is 0x2000..0x11E00) and the CPU runs at 75 MHz, which is the clock mcycle counts (the firmware default assumes 50 MHz).
# Both are build parameters of the firmware's own Makefile; no firmware source is edited for the board. Keep PARAMS in
# tools/fpga/boot_image.py equal to SRAM_BYTES / EXTRA_DEFS here.

ROOT       := $(abspath ../..)
BLDIR      := $(ROOT)/sw/bootloader
OUT        ?= $(or $(TMPDIR),/tmp)/nv_bootimg_build
SRAM_BYTES := 65536
EXTRA_DEFS := -DBL_CPU_HZ=75000000u
BLMAKE      = $(MAKE) -C $(BLDIR) BUILD=$(OUT) SRAM_BYTES=$(SRAM_BYTES) EXTRA_DEFS='$(EXTRA_DEFS)'

.PHONY: bootimg bootimg-check clean-bootimg
bootimg:
	rm -rf $(OUT)
	$(BLMAKE) $(OUT)/default/uart_boot.hex
	python3 $(ROOT)/tools/fpga/boot_image.py write --hex $(OUT)/default/uart_boot.hex --bin $(OUT)/default/uart_boot.bin

bootimg-check:
	rm -rf $(OUT)
	$(BLMAKE) $(OUT)/default/uart_boot.hex
	python3 $(ROOT)/tools/fpga/boot_image.py verify --hex $(OUT)/default/uart_boot.hex

clean-bootimg:
	rm -rf $(OUT)
