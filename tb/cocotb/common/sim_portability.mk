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
#  * COVERAGE=1: SIM=vcs instruments with `-cm line+cond+fsm+tgl+branch+assert` (section "VCS code
#    coverage" at the end of this file); SIM=xcelium REFUSES it (no imc on the host to merge/report
#    with -- a collected-but-unreportable database is worse than a clear error).
#  * SIM_BUILD is keyed by SIM so Verilator, VCS and Xcelium objects can never collide.

ifeq ($(SIM),verilator)

# Verilator: keep the lint prerequisites exactly as written.
sp_lint = $(1)

else ifneq ($(filter vcs xcelium,$(SIM)),)

sp_lint =

# sim/Makefile never sets this; cocotb's Makefile.xcelium refuses to run without it.
TOPLEVEL_LANG ?= verilog

ifdef COVERAGE
  ifneq ($(SIM),vcs)
    $(error COVERAGE=1 is not wired for SIM=$(SIM): only SIM=verilator (--coverage-*) and SIM=vcs (-cm ...) collect coverage; Xcelium coverage needs imc to merge and report, which is not installed on this host)
  endif
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
# Verilator's -I is BOTH the `include path and a module-library search dir (it finds <module>.sv/.v there).
# Some source lists in the soc Makefile are incomplete and only work because of that (e.g. rv32i_clock_gate.sv
# is missing from SOC_BOOT_SOURCES), so -I also becomes -y; a genuinely missing module still errors.
SP_INCS := $(filter +incdir+%,$(SP_IN)) $(patsubst -I%,+incdir+%,$(filter -I%,$(SP_IN))) \
           $(foreach d,$(patsubst -I%,%,$(filter -I%,$(SP_IN))),-y $(d)) $(if $(filter -I%,$(SP_IN)),+libext+.sv+.v)
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
  # Numeric overrides DO go on the command line (-defparam): a hierarchical defparam is applied after the
  # wrapper's own parameter-dependent typedefs are resolved, so e.g. tb_apb_interconnect's
  # `typedef ... [N_SLAVES]` kept N_SLAVES's default and failed elaboration (TYCMPAT).
  SP_GS_STR := $(foreach g,$(SP_GS),$(if $(findstring \",$(g)),$(g)))
  SP_GS_NUM := $(filter-out $(SP_GS_STR),$(SP_GS))
  SP_PARAMS := $(foreach g,$(SP_GS_NUM),-defparam $(TOPLEVEL).$(patsubst -G%,%,$(g)))
  SP_BASE   := -sv -nocopyright -nohistory -top sp_defparams
endif

# Same define can arrive twice (the Makefile's own block plus SIM_PORT_DEFINES): dedupe, keep order.
sp_uniq = $(if $(1),$(firstword $(1)) $(call sp_uniq,$(filter-out $(firstword $(1)),$(wordlist 2,$(words $(1)),$(1)))))

override undefine EXTRA_ARGS
override undefine COMPILE_ARGS
COMPILE_ARGS := $(SP_BASE) $(call sp_uniq,$(SP_DEFS)) $(SP_INCS) $(SP_PARAMS) $(SP_REST)

# --- VCS code coverage (compile side) -----------------------------------------------------------
# Metrics: line, condition, FSM, toggle, branch, SVA assertion.  Everything is in COMPILE_ARGS, so it is
# part of the SIM_BUILD content key below and an instrumented model can never share a build dir with a
# plain one (the stale-simv false-pass class of PR #142).  The scope file (-cm_hier) is generated here at
# parse time; see the runtime half at the end of this file.
ifeq ($(SIM)$(if $(COVERAGE),-cov),vcs-cov)
  VCS_COV_METRICS ?= line+cond+fsm+tgl+branch+assert
  SP_COV_DIR := $(abspath $(or $(COV_DIR),$(or $(SIM_BUILD_ROOT),.)/coverage))
  SP_COV_REPO := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../../..)
  ifeq ($(wildcard $(SP_COV_REPO)/rtl/soc),)
    $(error sim_portability.mk: cannot find rtl/ under $(SP_COV_REPO) for the VCS coverage scope)
  endif
  # Scope = the rtl/ files this build actually compiles: its VERILOG_SOURCES plus whatever the -I/-y
  # library lookup can pull in (a module found only through -y, e.g. rv32i_clock_gate.sv, is RTL too).
  # Testbench wrappers (tb_*), cocotb glue and the behavioural simulation models under sim/ are not
  # listed, so they are excluded at COMPILE time (a leading +filelist rule excludes everything else),
  # not by filtering the report afterwards.  Listing only files this build uses keeps VCS from warning
  # (VCM-HFUFF) about every unused rtl/ file.  The list is content-addressed (name carries a hash of
  # it), so builds with different sources never share or race on a file.
  define sp_nl


  endef
  SP_COV_FILES := $(sort $(filter $(SP_COV_REPO)/rtl/%,$(abspath $(VERILOG_SOURCES) \
                    $(foreach d,$(patsubst -I%,%,$(filter -I%,$(SP_IN))),$(wildcard $(d)/*.sv $(d)/*.v)))))
  SP_COV_H := $(shell printf '%s' '$(SP_COV_FILES)' | sha256sum | cut -c1-8)
  SP_COV_RTL_LIST := $(SP_COV_DIR)/vcs_cov_scope_$(SP_COV_H).f
  SP_COV_HIER := $(SP_COV_DIR)/vcs_cov_scope_$(SP_COV_H).cfg
  SP_COV_MKDIR := $(shell mkdir -p $(SP_COV_DIR))
  $(if $(wildcard $(SP_COV_RTL_LIST)),,$(file >$(SP_COV_RTL_LIST),$(subst $(sp_space),$(sp_nl),$(SP_COV_FILES))))
  $(if $(wildcard $(SP_COV_HIER)),,$(file >$(SP_COV_HIER),// generated by sim_portability.mk: coverage scope = rtl/ files of this build$(sp_nl)+filelist $(SP_COV_RTL_LIST)))
  COMPILE_ARGS += -cm $(VCS_COV_METRICS) -cm_hier $(SP_COV_HIER) -cm_libs yv
endif

# --- SIM_BUILD ----------------------------------------------------------------------------------
# (SIM_BUILD given on the command line wins for `:=`, then gets the SIM suffix via override below.)
ifeq ($(SIM_PORT_KEYED_BUILD),1)
  ifeq ($(origin SIM_BUILD),command line)
    # An explicit SIM_BUILD (e.g. check-exit-propagation) is respected, only tagged with the simulator.
    override SIM_BUILD := $(patsubst %_$(SIM),%,$(patsubst %_cov,%,$(SIM_BUILD)))_$(SIM)$(if $(COVERAGE),_cov)
  else ifneq ($(filter command line environment override,$(origin MODULE)),)
    SP_KEY_MATERIAL := $(strip sim=$(SIM) home=$(VCS_HOME)$(XCELIUM_HOME) top=$(TOPLEVEL) \
                       sources=$(VERILOG_SOURCES) compile=$(COMPILE_ARGS) params=$(SP_GS))
    SP_KEY := $(shell printf '%s' '$(subst ','\'',$(SP_KEY_MATERIAL))' | sha256sum | cut -c1-16)
    SIM_BUILD := $(SIM_BUILD_ROOT)/sim_build_$(SIM)_$(TOPLEVEL)_$(SP_KEY)$(if $(COVERAGE),_cov)
  endif
else
  override SIM_BUILD := $(patsubst %_$(SIM),%,$(patsubst %_cov,%,$(or $(SIM_BUILD),$(SIM_BUILD_ROOT)/sim_build)))_$(SIM)$(if $(COVERAGE),_cov)
endif

ifeq ($(SIM)$(if $(strip $(SIM_BUILD)),,-nobuild),xcelium)
  # Generated override module: one hierarchical defparam per -G<P>=<v> (string values keep their quotes).
  ifneq ($(SP_GS_STR),)
    SP_DEFPARAM_SV := $(SIM_BUILD)/sp_defparams.sv
    SP_MKDIR := $(shell mkdir -p $(SIM_BUILD))
    $(file >$(SP_DEFPARAM_SV),module sp_defparams;)
    $(foreach g,$(SP_GS_STR),$(file >>$(SP_DEFPARAM_SV),  defparam $(TOPLEVEL).$(subst \",",$(patsubst -G%,%,$(g)));))
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

# --- VCS code coverage (run side) ---------------------------------------------------------------
# Every simulation runs with the SAME -cm metrics as the compile, into the build's own simv.vdb
# (-cm_dir; the compile wrote the static design there) under a UNIQUE -cm_name:
#     <build dir>__<MODULE>[__tc<TESTCASE hash>]__<hash of the abs build dir>
# MODULE is in the name because suites that share a build dir (soc_integration_batch, the soc_top
# chains of tools/eda/regress_specs.py) share one simv.vdb, and the hash of the build dir keeps names
# unique when per-job vdbs from different SIM_BUILD_ROOTs are merged by one urg call.  Two simulations
# with the same -cm_name in one vdb would OVERWRITE silently.  -cm_dir/-cm_name are run-only options, so
# they go in SIM_ARGS (cocotb puts SIM_ARGS on the simv line only; PLUSARGS/EXTRA_ARGS also reach the
# compile line).  Merge + report: tools/eda/vcs_coverage.py (urg).
ifeq ($(SIM)$(if $(COVERAGE),-cov),vcs-cov)
  SP_COV_VDB := $(abspath $(SIM_BUILD))/simv.vdb
  SP_COV_TCHASH := $(if $(TESTCASE),__tc$(shell printf '%s' '$(TESTCASE)' | sha256sum | cut -c1-8))
  SP_COV_BHASH := $(shell printf '%s' '$(abspath $(SIM_BUILD))' | sha256sum | cut -c1-6)
  sp_comma := ,
  SP_COV_NAME := $(subst $(sp_comma),_,$(subst $(sp_space),_,$(subst /,_,$(notdir $(SIM_BUILD))__$(MODULE)$(SP_COV_TCHASH)__$(SP_COV_BHASH))))
  override SIM_ARGS += -cm $(VCS_COV_METRICS) -cm_dir $(SP_COV_VDB) -cm_name $(SP_COV_NAME)
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
