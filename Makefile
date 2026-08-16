# Repo-root Makefile — agent/developer tooling setup and verification.
#
# Scope: this file is deliberately NOT a build system for the design. RTL sim
# and lint live in sim/Makefile, physical design in pnr/Makefile, firmware in
# sw/bench/Makefile. What lives here is the per-clone, per-machine setup that
# nothing else owns: output filtering and the EDA MCP session servers.
#
# Why it exists: two of the three setup steps fail *silently* when skipped.
# Without `rtk trust` and the nix transparent_prefixes, every cocotb suite still
# runs — it is just no longer compressed (244 lines instead of 2 per suite), with
# no error to notice. Without the .mcp.json path fix, the MCP servers simply
# never connect. `make setup` makes all three reproducible; `make verify-tooling`
# proves they took effect and exits non-zero if they did not.

REPO_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
PYTHON    ?= python3
RTK       ?= rtk
MCP_JSON  := $(REPO_ROOT)/.mcp.json
SESSION_SERVER := $(REPO_ROOT)/tools/eda/mcp/session_server.py

.DEFAULT_GOAL := help
.PHONY: help setup setup-rtk setup-mcp verify-tooling mcp-status

help:
	@echo "RV32I + GPU-lite SoC — developer tooling Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  make setup          - One-time per clone: rtk trust + rtk transparent_prefixes + .mcp.json paths"
	@echo "  make verify-tooling - Prove the setup took effect (filters, tests, both MCP servers). Fails loudly."
	@echo "  make mcp-status     - Show the configured MCP servers and whether each one handshakes"
	@echo "  make setup-rtk      - Just the rtk half of setup"
	@echo "  make setup-mcp      - Just the .mcp.json half of setup"
	@echo ""
	@echo "Design flows live elsewhere:"
	@echo "  sim/Makefile        - cocotb suites, Verilator lint, Verible"
	@echo "  pnr/Makefile        - synthesis, place & route, STA, sign-off"
	@echo "  sw/bench/Makefile   - bare-metal RISC-V benchmarks"
	@echo ""
	@echo "Background: tools/eda/README.md, and the RTK section of CLAUDE.md"

# ---------------------------------------------------------------- setup

setup: setup-rtk setup-mcp setup-beads
	@echo ""
	@echo "Setup done. Run 'make verify-tooling' to confirm, and restart Claude Code"
	@echo "so it re-reads .mcp.json and picks up the eda-opensta/eda-openroad servers."

setup-beads:
	@echo "==> registering the beads issues.jsonl merge driver (bead b1o)"
	@# .gitattributes names merge=beads-export, but a merge driver's COMMAND
	@# lives in git config, which is per-clone and cannot be committed. Without
	@# this step git silently falls back to the default driver, which is exactly
	@# the stale-row behaviour b1o describes -- and it fails quietly, so
	@# verify-tooling checks it.
	@cd $(REPO_ROOT) && git config merge.beads-export.name \
	  "regenerate .beads/issues.jsonl from the authoritative Dolt DB"
	@cd $(REPO_ROOT) && git config merge.beads-export.driver \
	  "$(REPO_ROOT)/tools/setup/beads_merge_driver.sh %A"
	@echo "  ok: merge.beads-export -> tools/setup/beads_merge_driver.sh"

setup-rtk:
	@echo "==> registering .rtk/filters.toml with rtk"
	@command -v $(RTK) >/dev/null 2>&1 || { \
	  echo "rtk not found in PATH — see the RTK section of CLAUDE.md"; exit 1; }
	@# rtk trust echoes the whole filter file back for review; keep the summary
	@# lines only. Capture first and check rtk's own status BEFORE filtering —
	@# piping straight into grep would make grep define the pipeline status, so a
	@# failing rtk trust would still report a completed setup.
	@cd $(REPO_ROOT) && out=$$($(RTK) trust 2>&1); rc=$$?; \
	  if [ $$rc -ne 0 ]; then printf '%s\n' "$$out"; exit $$rc; fi; \
	  printf '%s\n' "$$out" | grep -E "^(Trusted|Project-local)" || true
	@echo "==> ensuring rtk can see through the nix devshell wrappers"
	@$(PYTHON) $(REPO_ROOT)/tools/setup/sync_rtk_config.py

setup-mcp:
	@echo "==> pointing the eda-* entries in .mcp.json at this clone"
	@$(PYTHON) $(REPO_ROOT)/tools/eda/mcp/sync_mcp_paths.py "$(MCP_JSON)" "$(REPO_ROOT)"

# ------------------------------------------------------------ verification

# Every step here must be able to fail the target. A setup step that quietly
# did nothing is the failure mode this whole epic exists to prevent.
verify-tooling:
	@echo "==> rtk filter inline tests"
	@cd $(REPO_ROOT) && $(RTK) verify
	@echo "==> python unit tests"
	@cd $(REPO_ROOT) && $(RTK) pytest tb/tests/ -q
	@echo "==> .mcp.json is valid JSON and lists both eda servers"
	@$(PYTHON) -c "import json,sys; \
	  d=json.load(open('$(MCP_JSON)'))['mcpServers']; \
	  missing=[n for n in ('eda-opensta','eda-openroad') if n not in d]; \
	  sys.exit('missing from .mcp.json: %s (run: make setup-mcp)' % missing) if missing else None; \
	  bad=[n for n in ('eda-opensta','eda-openroad') if '$(REPO_ROOT)' not in ' '.join(d[n]['args'])]; \
	  sys.exit('.mcp.json points at another clone: %s (run: make setup-mcp)' % bad) if bad else None; \
	  print('  ok: eda-opensta, eda-openroad -> $(REPO_ROOT)')"
	@echo "==> beads merge driver is registered (bead b1o)"
	@cd $(REPO_ROOT) && d=$$(git config --get merge.beads-export.driver || true); \
	  if [ -z "$$d" ]; then \
	    echo "  merge.beads-export.driver is NOT set — run: make setup-beads"; exit 1; \
	  fi; \
	  case "$$d" in *beads_merge_driver.sh*) ;; \
	    *) echo "  merge.beads-export.driver points elsewhere: $$d"; exit 1 ;; esac; \
	  test -x $(REPO_ROOT)/tools/setup/beads_merge_driver.sh || { \
	    echo "  driver script missing or not executable"; exit 1; }; \
	  echo "  ok: $$d"
	@$(MAKE) --no-print-directory mcp-status
	@echo ""
	@echo "verify-tooling: PASS"

# Handshake each server exactly the way Claude Code launches it. A server that
# starts but answers `initialize` with an error is a failure, not a pass — the
# plugin-generated adapters this replaced failed in precisely that way.
mcp-status:
	@echo "==> MCP session server handshake"
	@for tool in opensta openroad; do \
	  printf '%s\n%s\n%s\n' \
	    '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \
	    '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
	    '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
	  | $(PYTHON) $(SESSION_SERVER) --tool $$tool 2>/dev/null \
	  | $(PYTHON) -c "import sys,json; \
	      msgs=[json.loads(l) for l in sys.stdin if l.strip()]; \
	      init=next((m for m in msgs if 'serverInfo' in m.get('result',{})), None); \
	      tools=next((m for m in msgs if 'tools' in m.get('result',{})), None); \
	      sys.exit('  FAIL: $$tool did not complete the MCP handshake') if not init or not tools else None; \
	      print('  ok: %-22s %d tools' % (init['result']['serverInfo']['name'], len(tools['result']['tools'])))" \
	  || exit 1; \
	done
