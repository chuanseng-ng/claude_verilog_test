# tools/formal/Makefile — EQY sv2v-vs-RTL equivalence targets (bead claude_verilog_test-q7n).
#
# Mirrors the sim/Makefile / pnr/Makefile convention: a design-flow Makefile
# that lives next to the flow it drives, not in the repo-root setup-only
# Makefile. See README.md for what is and is not proven by these targets.

.PHONY: eqy-tier1 eqy-tier2 eqy-tier3 eqy-all

eqy-tier1:
	./run_eqy.sh --tier 1

eqy-tier2:
	./run_eqy.sh --tier 2

eqy-tier3:
	./run_eqy.sh --tier 3

eqy-all:
	./run_eqy.sh --all
