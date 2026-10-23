# sim_portability.mk -- let the cocotb Makefiles in this repo drive Synopsys VCS and Cadence
# Xcelium (xrun) as well as Verilator.
#
# Included by tb/cocotb/soc/Makefile, tb/cocotb/cpu/Makefile and sim/Makefile, immediately BEFORE
# their `include $(shell cocotb-config --makefiles)/Makefile.sim`.  It only defines variables (no
# targets, so it can never change a Makefile's default goal).
#
# INVARIANT: with SIM=verilator (the default, and what CI runs) this file changes nothing the
# including Makefile does.  It defines one identity helper (`sp_lint`) and leaves every other
# variable alone; `make -n` output of every target is byte-identical with and without the include
# (checked with `cmp -s`, see the commit that introduced this file).
#
# Inputs the including Makefile may set BEFORE the include (all optional):
#   SIM_PORT_KEYED_BUILD=1  give each distinct build recipe its own SIM_BUILD dir, keyed by content
#                           (the soc Makefile's scheme; the Verilator key lives in that Makefile).
#   SIM_PORT_DEFINES        `+define+` names that the Makefile adds only inside its `ifeq ($(SIM),verilator)`
#                           block but that the RTL needs under every simulator (e.g. SIMULATION).
# Inputs from the caller's command line:
#   SIM_RESULTS_IN_BUILD=1  write cocotb's results.xml to $(SIM_BUILD)/results__<MODULE>.xml instead of the
#                           shared ./results.xml.  Needed to run several targets of one directory
#                           concurrently, and to keep each build point's verdict (several soc targets
#                           run two build points back to back; ./results.xml keeps only the last).
#   VCS_LINT_FLAGS          default +lint=TFIPC-L (port-connection width/type mismatches become warnings).
#   VCS_EXTRA_COMPILE       extra raw vcs compile flags (e.g. -kdb for Verdi).
#
# What it does when SIM is vcs or xcelium
# ---------------------------------------
#  * EXTRA_ARGS and COMPILE_ARGS are translated, never forwarded raw (VCS and xrun reject or silently
#    misread most Verilator flags):
#        -G<P>=<v>        -> VCS   -pvalue+<TOPLEVEL>.<P>=<v>      Xcelium  -defparam <TOPLEVEL>.<P>=<v>
#                            (a quoted string value such as -GMEM_INIT_FILE=\"path\" is kept as written)
#        -D<X> / +define+ -> +define+<X>                          (native to both)
#        -I<d> / +incdir+ -> +incdir+<d>                          (native to both)
#        -W*  --*  -O*  -j*  and the value-taking Verilator flags (-CFLAGS, --output-split, ...)
#                         -> dropped (Verilator-only: lint switches, tracing, coverage, optimisation)
#        anything else (e.g. `-y dir`, a native +plusarg) -> passed through untouched.
#    The result goes into COMPILE_ARGS.  EXTRA_ARGS is UNDEFINED afterwards: it arrives from the sub-make
#    command line, where cocotb's own `EXTRA_ARGS += ...` (VCS: -full64, Xcelium: the whole
#    -top/-xmlibdirpath/-licqueue block) would otherwise be silently ignored, and cocotb's VCS rule
#    also hands EXTRA_ARGS to the simv run line, where -pvalue/-defparam do not belong.
#  * Xcelium gets -nocopyright, -nohistory and a per-build log (-l $(SIM_BUILD)/xrun.log) so concurrent
#    builds in one directory do not trample xrun.log / xrun.history.
#  * `$(call sp_lint,<lint targets>)` is empty, so a `foo: foo_lint` prerequisite becomes a no-op:
#    Verilator --lint-only has no VCS/xrun equivalent run here; compile cleanliness is judged from the
#    VCS/xrun compile logs instead (every warning triaged by hand, see the bring-up report).
#  * COVERAGE=1 is refused (Verilator coverage flags have no meaning here; vcs/xrun coverage is a
#    separate, not yet wired, step).
#  * SIM_BUILD is keyed by SIM so Verilator, VCS and Xcelium objects can never collide.

ifeq ($(SIM),verilator)

# Verilator: keep the lint prerequisites exactly as written.
sp_lint = $(1)

else ifneq ($(filter vcs xcelium,$(SIM)),)

sp_lint =

ifdef COVERAGE
  $(error COVERAGE=1 is Verilator-only for now (SIM=$(SIM)); vcs/xcelium coverage is not wired into sim_portability.mk yet)
endif

sp_empty :=
sp_space := $(sp_empty) $(sp_empty)

# --- argument translation -----------------------------------------------------------------------
# Verilator flags that take their value as the NEXT word.  Each "flag value" pair is first fused to
# "flag=value" so the single-token filters below drop the pair as a unit.
SP_VAL_FLAGS := --output-split --output-split-cfuncs --output-split-ctrace --coverage-max-width \
                -CFLAGS -LDFLAGS --top-module --top -o --prefix --timescale -Mdir --x-assign --x-initial \
                --threads --trace-depth
SP_DROP := -W% --% -O% -j% -CFLAGS=% -LDFLAGS=% -Mdir=% -o=%

# $(call sp_merge1,<string>,<flag>) -> <string> with the word "<flag>" glued to its successor.
sp_merge1 = $(strip $(subst $(sp_space)$(2)$(sp_space),$(sp_space)$(2)=,$(sp_space)$(1)$(sp_space)))
# $(call sp_fold,<string>,<flag list>)
sp_fold = $(if $(2),$(call sp_fold,$(call sp_merge1,$(1),$(firstword $(2))),$(wordlist 2,$(words $(2)),$(2))),$(1))

SP_RAW_EXTRA   := $(EXTRA_ARGS)
SP_RAW_COMPILE := $(COMPILE_ARGS)
SP_IN := $(call sp_fold,$(SP_RAW_EXTRA) $(SP_RAW_COMPILE),$(SP_VAL_FLAGS))

SP_DEFS := $(filter +define+%,$(SP_IN)) $(patsubst -D%,+define+%,$(filter -D%,$(SP_IN))) \
           $(addprefix +define+,$(SIM_PORT_DEFINES))
SP_INCS := $(filter +incdir+%,$(SP_IN)) $(patsubst -I%,+incdir+%,$(filter -I%,$(SP_IN)))
SP_GS   := $(filter -G%,$(SP_IN))
SP_REST := $(filter-out $(SP_DROP) -G% -I% -D% +define+% +incdir+%,$(SP_IN))

ifeq ($(SIM),vcs)
  VCS_LINT_FLAGS ?= +lint=TFIPC-L
  # A string value arrives as \"text\" (the backslashes survive make; sh would eat them).  VCS only accepts
  # -pvalue+top.P=\"text\" with the backslashes intact on its argv, so escape them for the recipe's sh.
  SP_PARAMS := $(patsubst -G%,-pvalue+$(TOPLEVEL).%,$(subst \",\\\",$(SP_GS)))
  # (-sverilog / -timescale / -full64 come from cocotb's own VCS makefile)
  SP_BASE   := $(VCS_LINT_FLAGS) $(VCS_EXTRA_COMPILE)
else
  # xrun's -defparam silently IGNORES string-typed parameters ("*W,BDDSTR ... ignored"), so parameter
  # overrides go through a generated hierarchical-defparam top (see below) instead of the command line.
  SP_PARAMS :=
  SP_BASE   := -sv -nocopyright -nohistory -top sp_defparams
endif

# Same define can arrive twice (the Makefile's own block plus SIM_PORT_DEFINES): dedupe, keep order.
sp_uniq = $(if $(1),$(firstword $(1)) $(call sp_uniq,$(filter-out $(firstword $(1)),$(wordlist 2,$(words $(1)),$(1)))))

override undefine EXTRA_ARGS
override undefine COMPILE_ARGS
COMPILE_ARGS := $(SP_BASE) $(call sp_uniq,$(SP_DEFS)) $(SP_INCS) $(SP_PARAMS) $(SP_REST)

# --- SIM_BUILD ----------------------------------------------------------------------------------
# (SIM_BUILD given on the command line wins for `:=`, then gets the SIM suffix via override below.)
ifeq ($(SIM_PORT_KEYED_BUILD),1)
  ifeq ($(origin SIM_BUILD),command line)
    # An explicit SIM_BUILD (e.g. check-exit-propagation) is respected, only tagged with the simulator.
    override SIM_BUILD := $(patsubst %_$(SIM),%,$(SIM_BUILD))_$(SIM)
  else ifneq ($(filter command line environment override,$(origin MODULE)),)
    SP_KEY_MATERIAL := $(strip sim=$(SIM) home=$(VCS_HOME)$(XCELIUM_HOME) top=$(TOPLEVEL) \
                       sources=$(VERILOG_SOURCES) compile=$(COMPILE_ARGS) params=$(SP_GS))
    SP_KEY := $(shell printf '%s' '$(subst ','\'',$(SP_KEY_MATERIAL))' | sha256sum | cut -c1-16)
    SIM_BUILD := $(SIM_BUILD_ROOT)/sim_build_$(SIM)_$(TOPLEVEL)_$(SP_KEY)
  endif
else
  override SIM_BUILD := $(patsubst %_$(SIM),%,$(or $(SIM_BUILD),$(SIM_BUILD_ROOT)/sim_build))_$(SIM)
endif

ifeq ($(SIM),xcelium)
  # Generated override module: one hierarchical defparam per -G<P>=<v> (string values keep their quotes).
  ifneq ($(SP_GS),)
    SP_DEFPARAM_SV := $(SIM_BUILD)/sp_defparams.sv
    SP_MKDIR := $(shell mkdir -p $(SIM_BUILD))
    $(file >$(SP_DEFPARAM_SV),module sp_defparams;)
    $(foreach g,$(SP_GS),$(file >>$(SP_DEFPARAM_SV),  defparam $(TOPLEVEL).$(subst \",",$(patsubst -G%,%,$(g)));))
    $(file >>$(SP_DEFPARAM_SV),endmodule)
    override VERILOG_SOURCES += $(SP_DEFPARAM_SV)
  else
    # keep `-top sp_defparams` valid when there is nothing to override
    SP_DEFPARAM_SV := $(SIM_BUILD)/sp_defparams.sv
    SP_MKDIR := $(shell mkdir -p $(SIM_BUILD))
    $(file >$(SP_DEFPARAM_SV),module sp_defparams; endmodule)
    override VERILOG_SOURCES += $(SP_DEFPARAM_SV)
  endif
  # Per-build log + history so concurrent builds in one directory do not trample xrun.log.
  COMPILE_ARGS += -l $(SIM_BUILD)/xrun.log
endif

ifeq ($(SIM_RESULTS_IN_BUILD),1)
  export COCOTB_RESULTS_FILE := $(SIM_BUILD)/results__$(subst /,_,$(subst $(sp_space),_,$(MODULE))).xml
endif

# The Verilator block normally sets this; the p6t8 results check and the shard helpers use it.
SIM_PYTHON3 ?= $(shell command -v python3)

else

sp_lint = $(1)
$(warning sim_portability.mk: SIM=$(SIM) is not verilator/vcs/xcelium -- nothing translated)

endif
