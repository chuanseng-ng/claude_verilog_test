# tools/formal/Makefile — EQY sv2v-vs-RTL equivalence targets (bead claude_verilog_test-q7n).
#
# Mirrors the sim/Makefile / pnr/Makefile convention: a design-flow Makefile
# that lives next to the flow it drives, not in the repo-root setup-only
# Makefile. See README.md for what is and is not proven by these targets.

.PHONY: eqy-tier1 eqy-tier2 eqy-tier3 eqy-tier4 eqy-tier5 eqy-all eqy-negative-control

eqy-tier1:
	./run_eqy.sh --tier 1

eqy-tier2:
	./run_eqy.sh --tier 2

eqy-tier3:
	./run_eqy.sh --tier 3

# Tier 4 uses the Synlig plugin (Surelog/UHDM frontend) instead of Yosys's
# native -sv frontend -- see README.md and modules.json for why. Same
# ./run_eqy.sh entrypoint; frontend selection is per-module in modules.json.
# Three of the five tier-4 modules PASS; dma_engine and the two register banks
# carry expected_status=FAIL (root-caused to two Synlig-side artifacts, README),
# so this target exits non-zero by design -- read the summary, not the code.
eqy-tier4:
	-./run_eqy.sh --tier 4

# Tier 5 is DIAGNOSTIC, not sign-off: shrunk-parameter and constant-folded
# variants of the two register banks that isolate WHY their tier-4 runs FAIL.
# Two of the six entries are expected to fail, so this also exits non-zero.
eqy-tier5:
	-./run_eqy.sh --tier 5

eqy-all:
	-./run_eqy.sh --all

# Negative control: inject each module's declared gold-side mutation and
# require eqy to CATCH it. Verdicts are INVERTED (a raw FAIL is a PASS here),
# so this target exiting 0 means "the harness demonstrably discriminates" --
# on both frontends, yosys-sv and Synlig. Modules with no declared mutation
# report SKIP, never PASS. A harness that cannot fail is not a harness.
eqy-negative-control:
	./run_eqy.sh --negative-control --module rv32i_clock_gate --module cdc_2ff_sync \
	             --module async_axi_fifo --module axil_to_apb --module boot_rom
