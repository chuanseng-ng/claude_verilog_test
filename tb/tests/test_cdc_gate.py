"""Unit tests for tools/cdc/cdc_gate.py — the CDC gate's decision logic.

The gate is what every other CDC claim rests on, so its own logic needs to be
pinned down. The cases that matter most are the ones that would rot silently:
a waiver that stops matching, a waiver whose regex quietly widens to swallow a
new crossing, and a change to cdc_snitch's report format that makes lines stop
parsing (which would otherwise look like "zero findings").
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_GATE_PATH = Path(__file__).resolve().parents[2] / "tools" / "cdc" / "cdc_gate.py"

_spec = importlib.util.spec_from_file_location("cdc_gate", _GATE_PATH)
cdc_gate = importlib.util.module_from_spec(_spec)
sys.modules["cdc_gate"] = cdc_gate
_spec.loader.exec_module(cdc_gate)


BASE_CFG = """
clock_domains: [clk_i, cpu_clk_i]
domain_aliases:
  cpu_gated_clk: cpu_clk_i
  gpu_gated_clk: clk_i
reset_domains: [rst_n_i, cpu_rst_n_i]
port_domains: {}
waivers: []
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def load(tmp_path: Path, cfg_text: str = BASE_CFG):
    return cdc_gate.load_config(write(tmp_path, "cfg.yml", cfg_text))


def line(stat, name, clk, inputs, magic=False):
    """Build a cdc_snitch report line. Note the DOUBLE space when not magic —
    cdc_snitch joins an empty magic field, and the parser must tolerate it."""
    mm = "magic " if magic else " "
    return f"{stat} {mm}42 {name} clk {clk} inputs ( {inputs} )\n"


# --------------------------------------------------------------------------
# canonicalization
# --------------------------------------------------------------------------

def test_reset_port_is_not_a_domain(tmp_path):
    """The ~85% case: a flop's reset pin shows clk + the async reset port."""
    cfg = load(tmp_path)
    doms = cdc_gate.canonical_domains("1 x clk_i, 1 x rst_n_i", cfg)
    assert doms == {"clk_i"}


def test_clock_gate_output_aliases_to_its_source(tmp_path):
    cfg = load(tmp_path)
    doms = cdc_gate.canonical_domains("1 x cpu_clk_i, 18 x cpu_gated_clk", cfg)
    assert doms == {"cpu_clk_i"}


def test_bus_bits_collapse_to_one_port_domain(tmp_path):
    """A 12-bit bus must count as one domain, not twelve."""
    cfg = load(tmp_path)
    raw = ", ".join(f"1 x apb_paddr_i[{i}]" for i in range(12))
    assert cdc_gate.canonical_domains(raw, cfg) == {"PORT:apb_paddr_i"}


def test_single_bit_port_is_tagged_like_a_bus(tmp_path):
    """Regression: single-bit ports were once left untagged while multi-bit
    ones got PORT:, which made waiver domain-strings unmatchable."""
    cfg = load(tmp_path)
    doms = cdc_gate.canonical_domains("1 x clk_i, 1 x spi_miso_i", cfg)
    assert doms == {"clk_i", "PORT:spi_miso_i"}


def test_port_domains_maps_a_bus_onto_a_real_clock(tmp_path):
    cfg = load(tmp_path, BASE_CFG.replace(
        "port_domains: {}", "port_domains: {apb_paddr_i: cpu_clk_i}"))
    doms = cdc_gate.canonical_domains("1 x apb_paddr_i[3], 4 x cpu_gated_clk", cfg)
    assert doms == {"cpu_clk_i"}


def test_genuine_two_domain_crossing_survives(tmp_path):
    """The whole point: a real crossing must NOT be canonicalized away."""
    cfg = load(tmp_path)
    doms = cdc_gate.canonical_domains("1 x clk_i, 1 x cpu_gated_clk", cfg)
    assert doms == {"clk_i", "cpu_clk_i"}


def test_alias_cycle_is_rejected(tmp_path):
    cfg = load(tmp_path, BASE_CFG.replace(
        "  gpu_gated_clk: clk_i", "  gpu_gated_clk: clk_i\n  a: b\n  b: a"))
    with pytest.raises(cdc_gate.ConfigError, match="cycle"):
        cdc_gate.canonical_domains("1 x a", cfg)


# --------------------------------------------------------------------------
# report parsing
# --------------------------------------------------------------------------

def test_parse_counts_and_resolves(tmp_path):
    cfg = load(tmp_path)
    rpt = write(tmp_path, "r.txt",
                line("OK1", "u.a", "clk_i", "1 x clk_i")
                + line("CDC", "u.s.sync_q[0]:D", "clk_i", "1 x cpu_gated_clk", magic=True)
                + line("OKX", "u.rx0:D", "clk_i", "1 x uart_rx_i")
                + line("BAD", "u.b:R", "clk_i", "1 x clk_i, 1 x rst_n_i")
                + line("BAD", "u.c:D", "clk_i", "1 x clk_i, 1 x cpu_clk_i")
                + "  tree 0 from 19482 clk clk_i name u.whatever\n")
    counts, residue, unparsed = cdc_gate.parse_report(rpt, cfg)
    assert counts["OK1"] == 1 and counts["CDC"] == 1 and counts["OKX"] == 1
    assert counts["BAD"] == 2
    assert counts["RESOLVED"] == 1          # the :R reset line
    assert unparsed == []                   # 'tree' lines are not classifications
    assert [r["name"] for r in residue] == ["u.c:D"]
    assert residue[0]["domains"] == "clk_i+cpu_clk_i"


def test_malformed_classification_line_is_surfaced(tmp_path):
    """If cdc_snitch's format changes, that must be loud — not silently read
    as 'no findings'."""
    cfg = load(tmp_path)
    rpt = write(tmp_path, "r.txt", "BAD this is not the expected shape\n")
    counts, residue, unparsed = cdc_gate.parse_report(rpt, cfg)
    assert counts["BAD"] == 0 and residue == []
    assert len(unparsed) == 1


# --------------------------------------------------------------------------
# waivers
# --------------------------------------------------------------------------

WAIVED_CFG = BASE_CFG.replace("waivers: []", """
waivers:
  - id: w-exact
    kind: tool-limitation
    dest: '^u\\.qualified\\[\\d+\\]:D$'
    domains: 'clk_i+cpu_clk_i'
    reason: test
    ref: test
""")


def test_waiver_matches_and_clears(tmp_path):
    cfg = load(tmp_path, WAIVED_CFG)
    item = {"name": "u.qualified[3]:D", "clk": "clk_i", "domains": "clk_i+cpu_clk_i"}
    hits, unwaived = cdc_gate.apply_waivers([item], cfg)
    assert unwaived == []
    assert len(hits["w-exact"]) == 1


def test_waiver_domain_guard_blocks_a_different_crossing(tmp_path):
    """A waiver's dest regex may match, but if the crossing is between
    DIFFERENT domains than the one reviewed, it must not be absorbed."""
    cfg = load(tmp_path, WAIVED_CFG)
    item = {"name": "u.qualified[3]:D", "clk": "clk_i", "domains": "clk_i+PORT:new_port_i"}
    hits, unwaived = cdc_gate.apply_waivers([item], cfg)
    assert unwaived == [item]
    assert not hits


def test_unmatched_item_is_unwaived(tmp_path):
    cfg = load(tmp_path, WAIVED_CFG)
    item = {"name": "u.something_else:D", "clk": "clk_i", "domains": "clk_i+cpu_clk_i"}
    _, unwaived = cdc_gate.apply_waivers([item], cfg)
    assert unwaived == [item]


# --------------------------------------------------------------------------
# config validation
# --------------------------------------------------------------------------

def test_accepted_risk_without_a_bead_is_rejected(tmp_path):
    cfg_text = BASE_CFG.replace("waivers: []", """
waivers:
  - id: risky
    kind: accepted-risk
    dest: 'x'
    reason: test
    ref: test
""")
    with pytest.raises(cdc_gate.ConfigError, match="tracking bead"):
        load(tmp_path, cfg_text)


def test_unknown_waiver_kind_is_rejected(tmp_path):
    cfg_text = BASE_CFG.replace("waivers: []", """
waivers:
  - id: w
    kind: probably-fine
    dest: 'x'
    reason: test
    ref: test
""")
    with pytest.raises(cdc_gate.ConfigError, match="kind"):
        load(tmp_path, cfg_text)


def test_missing_required_field_is_rejected(tmp_path):
    cfg_text = BASE_CFG.replace("waivers: []", """
waivers:
  - id: w
    kind: tool-limitation
    dest: 'x'
    reason: test
""")
    with pytest.raises(cdc_gate.ConfigError, match="'ref'"):
        load(tmp_path, cfg_text)


def test_duplicate_waiver_id_is_rejected(tmp_path):
    cfg_text = BASE_CFG.replace("waivers: []", """
waivers:
  - {id: w, kind: tool-limitation, dest: 'a', reason: t, ref: t}
  - {id: w, kind: tool-limitation, dest: 'b', reason: t, ref: t}
""")
    with pytest.raises(cdc_gate.ConfigError, match="duplicate"):
        load(tmp_path, cfg_text)


def test_missing_clock_domains_is_rejected(tmp_path):
    with pytest.raises(cdc_gate.ConfigError, match="clock_domains"):
        load(tmp_path, "reset_domains: []\nwaivers: []\n")


# --------------------------------------------------------------------------
# end-to-end exit status
# --------------------------------------------------------------------------

def test_main_passes_when_everything_resolves(tmp_path, capsys):
    cfg = write(tmp_path, "cfg.yml", BASE_CFG)
    rpt = write(tmp_path, "r.txt", line("BAD", "u.b:R", "clk_i", "1 x clk_i, 1 x rst_n_i"))
    assert cdc_gate.main([str(rpt), "-c", str(cfg)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_main_fails_on_unwaived_crossing(tmp_path, capsys):
    cfg = write(tmp_path, "cfg.yml", BASE_CFG)
    rpt = write(tmp_path, "r.txt", line("BAD", "u.c:D", "clk_i", "1 x clk_i, 1 x cpu_clk_i"))
    assert cdc_gate.main([str(rpt), "-c", str(cfg)]) == 1
    assert "1 unwaived" in capsys.readouterr().out


def test_main_fails_on_stale_waiver(tmp_path, capsys):
    """A waiver that matches nothing is a failure, not a free pass — the
    crossing it covered may have been renamed out from under it."""
    cfg = write(tmp_path, "cfg.yml", WAIVED_CFG)
    rpt = write(tmp_path, "r.txt", line("OK1", "u.a", "clk_i", "1 x clk_i"))
    assert cdc_gate.main([str(rpt), "-c", str(cfg)]) == 1
    assert "stale waiver" in capsys.readouterr().out


def test_main_reports_usage_error_for_missing_report(tmp_path):
    cfg = write(tmp_path, "cfg.yml", BASE_CFG)
    assert cdc_gate.main([str(tmp_path / "nope.txt"), "-c", str(cfg)]) == 2


def test_json_summary_is_written(tmp_path):
    cfg = write(tmp_path, "cfg.yml", BASE_CFG)
    rpt = write(tmp_path, "r.txt", line("BAD", "u.c:D", "clk_i", "1 x clk_i, 1 x cpu_clk_i"))
    out = tmp_path / "gate.json"
    cdc_gate.main([str(rpt), "-c", str(cfg), "--json", str(out)])
    import json
    data = json.loads(out.read_text())
    assert data["pass"] is False
    assert data["unwaived"][0]["name"] == "u.c:D"


# --------------------------------------------------------------------------
# the real config must stay valid
# --------------------------------------------------------------------------

def test_repo_config_loads_and_validates():
    """Catches a typo'd regex or a missing bead in the committed config."""
    cfg = cdc_gate.load_config(_GATE_PATH.with_name("cdc_config.yml"))
    assert "clk_i" in cfg["clock_domains"]
    assert cfg["waivers"], "expected at least one committed waiver"
