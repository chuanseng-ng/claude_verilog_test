# hls/bambu.mk — single source of truth for the Bambu HLS flag set (GH #119).
#
# Included by hls/Makefile; kept separate so every block's recipe provably uses
# the SAME flags. The pilot compares HLS output against hand-RTL, so a flag that
# differs between blocks would silently invalidate the comparison.
#
# Every flag below is load-bearing. Do not trim without reading the note:
#
#   --generate-interface=INFER   The `#pragma HLS interface` lines are SILENTLY
#                                INERT under the default MINIMAL. Without this
#                                you get BRAM-style ports instead of the AXI
#                                master, and no error.
#   --compiler=I386_CLANG16      The interface pragmas are parsed by Bambu's
#                                clang plugin; a GCC front-end never sees them.
#   --device-name=asap7-TC       Bambu bundles a real ASAP7 device model
#                                (asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib — the
#                                same library and corner pnr/asap7/cpu/config.json
#                                uses). Sets the operation-delay model used by
#                                scheduling, so it changes the emitted RTL.
#   --clock-period=0.705         ns. Matches pnr/asap7/template/config.json's
#                                CLOCK_PERIOD. Stage 2 must use the same value
#                                for BOTH arms or the PPA comparison is void.
#   --reset-type=async
#   --reset-level=low            Bambu's --reset-type default is `no`, i.e.
#                                registers with NO reset at all. These two make
#                                it async active-low, matching repo convention.
#   --disable-reg-init-value     Bambu's own help flags this for ASIC targets.
#   --no-mixed-design            Without it Bambu may emit VHDL for some library
#                                components, breaking the Verilator-only mandate.
#   -w V                         Verilog output.
#
# NOT used, deliberately: --tb-param-size=<param>:<bytes>. It would size m_axi
# memory spaces for a C-driver testbench, but its own help says it "will disable
# automated top-level function verification" — it makes the equivalence leg
# vacuous. Use an XML testbench instead (see hls/README.md).

BAMBU_FLAGS ?= \
  --generate-interface=INFER \
  --compiler=I386_CLANG16 \
  --device-name=asap7-TC \
  --clock-period=0.705 \
  --reset-type=async \
  --reset-level=low \
  --disable-reg-init-value \
  --no-mixed-design \
  -w V

# Co-simulation against the pinned Verilator (5.048, from the repo flake).
BAMBU_SIM_FLAGS ?= --simulate --simulator=VERILATOR

# Generated Verilog is NOT committed. It is large, machine-written, and
# regenerable; only its sha256 is tracked, so Stage 2 can prove it measured the
# same bits Stage 1 verified.
HLS_OUT ?= /nobackup/hls/out

REPO_ROOT_MK := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
WRAP_BAMBU   := $(REPO_ROOT_MK)/tools/eda/wrap-bambu.sh
