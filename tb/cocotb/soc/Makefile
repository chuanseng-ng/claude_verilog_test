# Makefile for SoC cocotb tests (Phase 5 / M3)
# Crossbar unit tests: routing, arbitration, concurrency, backpressure, burst.

TOPLEVEL_LANG ?= verilog
SIM ?= verilator

# Absolute paths so the Makefile works whether invoked from sim/ or here.
SOC_DIR  := $(shell pwd)
PROJ_ROOT := $(abspath $(SOC_DIR)/../../..)
RTL      := $(PROJ_ROOT)/rtl
TB       := $(PROJ_ROOT)/tb/cocotb
SIM_DIR  := $(PROJ_ROOT)/sim

# bfm/ lives in tb/cocotb (TB); slave model lives in this directory.
export PYTHONPATH := $(TB):$(SOC_DIR):$(PYTHONPATH)

# Per-DUT source lists.  The default build is the crossbar (preserves prior
# `make` behaviour); the register_bank / axil_interconnect targets override
# VERILOG_SOURCES + MODULE + TOPLEVEL on the recursive make.
XBAR_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_addr_map_pkg.sv \
	$(RTL)/soc/axi4_crossbar.sv \
	$(SOC_DIR)/tb_axi4_crossbar.sv

REGBANK_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(SOC_DIR)/tb_axi_lite_register_bank.sv

AXIL_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_periph_map_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/soc/axi_lite_interconnect.sv \
	$(SOC_DIR)/tb_axi_lite_interconnect.sv

VERILOG_SOURCES = $(XBAR_SOURCES)

ifeq ($(SIM),verilator)
	COMPILE_ARGS += -Wno-fatal
	COMPILE_ARGS += -Wno-WIDTH
	COMPILE_ARGS += -Wno-CASEINCOMPLETE
	COMPILE_ARGS += -Wno-TIMESCALEMOD
	COMPILE_ARGS += -Wno-UNOPTFLAT
	COMPILE_ARGS += --timescale 1ns/1ps
	COMPILE_ARGS += --public-flat-rw
	COMPILE_ARGS += --no-timing
	# Override PYTHON3: nix verilator hardcodes nix Python 3.11 but PYTHONHOME=/usr
	# points to Python 3.10 stdlib — mismatch crashes verilator_includer.
	BUILD_ARGS += PYTHON3=/usr/bin/python3
	# Override CXX/LINK: nix verilator generates clang++ commands but only g++
	# is available outside nix's clang environment.  cxx_shim.sh wraps g++ and
	# strips clang-only flags.
	BUILD_ARGS += CXX=$(SIM_DIR)/cxx_shim.sh
	BUILD_ARGS += LINK=$(SIM_DIR)/cxx_shim.sh
ifneq ($(wildcard /nix/store),)
	# Nix environment: nix ld.so cannot find system libs when cocotb dlopen's
	# libpython3.10.so.1.0.  Create a compat dir with symlinks to system libs.
	NIX_COMPAT_DIR := /tmp/cocotb_nix_compat
	SIM_CMD_PREFIX := mkdir -p $(NIX_COMPAT_DIR) && \
	  for _lib in libexpat.so.1 libz.so.1 libbz2.so.1.0 liblzma.so.5 libffi.so.8; do \
	    _src=$$(ldconfig -p 2>/dev/null | grep "^	$$_lib " | awk '{print $$NF}' | head -1); \
	    [ -n "$$_src" ] && ln -sf "$$_src" $(NIX_COMPAT_DIR)/$$_lib 2>/dev/null || true; \
	  done && \
	  export LD_LIBRARY_PATH=$(NIX_COMPAT_DIR):$${LD_LIBRARY_PATH} &&
endif
endif

MODULE   ?= test_crossbar
TOPLEVEL ?= tb_axi4_crossbar

# Suppress reduced-log noise to keep output readable.
export COCOTB_REDUCED_LOG_FMT=1

include $(shell cocotb-config --makefiles)/Makefile.sim

.PHONY: crossbar register_bank axil_interconnect soc_all
crossbar:
	$(MAKE) MODULE=test_crossbar TOPLEVEL=tb_axi4_crossbar

register_bank:
	$(MAKE) MODULE=test_register_bank TOPLEVEL=tb_axi_lite_register_bank \
		VERILOG_SOURCES="$(REGBANK_SOURCES)"

axil_interconnect:
	$(MAKE) MODULE=test_axil_interconnect TOPLEVEL=tb_axi_lite_interconnect \
		VERILOG_SOURCES="$(AXIL_SOURCES)"

# Run every SoC unit test (crossbar + register bank + AXI-Lite interconnect).
soc_all:
	$(MAKE) clean && $(MAKE) crossbar
	$(MAKE) clean && $(MAKE) register_bank
	$(MAKE) clean && $(MAKE) axil_interconnect
