"""Structural checks and negative controls for the reset paths of apb_cdc_bridge.

The bridge now reacts to the destination reset without a clock: m_rst_n_i reaches the async
clear of u_m_alive_sync through u_m_rst_sync. Two properties must hold, and no zero-delay
simulation can show either of them:

1. The reset net that drives m_rst_n_i of u_apb_dbg_cdc (cpu_domain_rst_n in soc_top.sv) cannot
   glitch low. It must be an AND of reset-tree signals and nothing else: an AND of steady-high
   inputs has no static hazard, so a spurious assertion is impossible. Two of its three terms
   must come straight from cdc_reset_sync. The third (cpu_core_rst_n) comes from the reset port
   and the PLL lock through a scan mux: it is a reset root, not a flop output, and the test says so.
2. The names that the CDC constraint files match exist in apb_cdc_bridge.sv, and the ASAP7 check
   file excludes the async pins of every cdc_reset_sync of the bridge from the domain-wide
   max-delay fallback.

Each check runs against a scratch copy that breaks the property (negative control).
"""

# pylint: disable=missing-function-docstring  # descriptive test names

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOC_TOP = (REPO / "rtl/soc/soc_top.sv").read_text()
BRIDGE = (REPO / "rtl/soc/apb_cdc_bridge.sv").read_text()
ASAP7_CHECK = (REPO / "pnr/constraints/phase5_soc_multiclock_check.sdc").read_text()
SKY130_CHECK = (REPO / "pnr/sky130/soc/constraints/sky130_soc_cdc_check.sdc").read_text()
PLL_SUB = (REPO / "rtl/soc/pll/pll_subsystem.sv").read_text()

SYNC_TERMS = ("pmu_cpu_rst_n_cpu_sync", "wdt_cpu_rst_n_cpu_sync")


def _strip(text: str) -> str:
    return re.sub(r"//[^\n]*", "", text)


def domain_reset_terms(soc_top: str) -> list:
    """Terms of the assign of cpu_domain_rst_n, or raise if it is anything but an AND chain."""
    m = re.search(r"assign\s+cpu_domain_rst_n\s*=\s*([^;]+);", _strip(soc_top))
    if not m:
        raise AssertionError("no assign of cpu_domain_rst_n")
    rhs = m.group(1).strip()
    if not re.fullmatch(r"\w+(\s*&\s*\w+)*", rhs):
        raise AssertionError(f"cpu_domain_rst_n is not a plain AND of signals: {rhs!r}")
    return [t.strip() for t in rhs.split("&")]


def check_domain_reset(soc_top: str, pll_sub: str) -> list:
    terms = domain_reset_terms(soc_top)
    code = _strip(soc_top)
    for t in SYNC_TERMS:
        if t not in terms:
            raise AssertionError(f"term {t} missing from cpu_domain_rst_n")
        pat = rf"cdc_reset_sync[^;]*?\.rst_n_o\s*\(\s*{t}\s*\)"
        if not re.search(pat, code, re.S):
            raise AssertionError(f"{t} is not the rst_n_o of a cdc_reset_sync")
    if "cpu_core_rst_n" not in terms or len(terms) != 3:
        raise AssertionError(f"unexpected terms {terms}")
    if not re.search(r"\.core_rst_n\s*\(\s*cpu_core_rst_n\s*\)", code):
        raise AssertionError("cpu_core_rst_n is not the core_rst_n of pll_subsystem")
    sub = _strip(pll_sub)
    if not re.search(r"assign\s+core_rst_n_func\s*=\s*rst_n_i\s*&\s*pll_locked\s*;", sub):
        raise AssertionError("core_rst_n_func is not rst_n_i & pll_locked")
    if not re.search(r"dft_rst_mux\s+u_core_rm[^;]*\.rst_n_o\s*\(\s*core_rst_n\s*\)", sub, re.S):
        raise AssertionError("core_rst_n is not the output of the dft_rst_mux u_core_rm")
    return terms


def test_domain_reset_is_an_and_of_reset_tree_signals():
    assert sorted(check_domain_reset(SOC_TOP, PLL_SUB)) == sorted(("cpu_core_rst_n",) + SYNC_TERMS)


def test_domain_reset_negative_controls():
    for bad in (
        "cpu_core_rst_n & pmu_cpu_rst_n_cpu_sync & wdt_cpu_rst_n_cpu_sync | pmu_cpu_rst_n",
        "cpu_core_rst_n & ~pmu_cpu_rst_n_cpu_sync & wdt_cpu_rst_n_cpu_sync",
        "cpu_core_rst_n & (pmu_cpu_rst_n_cpu_sync ^ wdt_cpu_rst_n_cpu_sync)",
        "cpu_core_rst_n & pmu_cpu_rst_n & wdt_cpu_rst_n_cpu_sync",
    ):
        mutated = re.sub(
            r"assign cpu_domain_rst_n = [^;]+;", f"assign cpu_domain_rst_n = {bad};", SOC_TOP
        )
        assert mutated != SOC_TOP
        try:
            check_domain_reset(mutated, PLL_SUB)
        except AssertionError:
            continue
        raise AssertionError(f"the check accepted {bad!r}")


def test_dbg_bridge_destination_reset_is_cpu_domain_reset():
    code = _strip(SOC_TOP)
    m = re.search(r"apb_cdc_bridge[^;]*?u_apb_dbg_cdc\s*\((.*?)\)\s*;", code, re.S)
    assert m and re.search(r"\.m_rst_n_i\s*\(\s*cpu_domain_rst_n\s*\)", m.group(1))


def bridge_instances(text: str) -> dict:
    """Instance name -> module for the cdc_sync and cdc_reset_sync instances of the bridge."""
    out = {}
    for mod, inst in re.findall(
        r"\b(cdc_sync|cdc_reset_sync)\b\s*(?:#\s*\(.*?\))?\s*(\w+)\s*\(", _strip(text), re.S
    ):
        out[inst] = mod
    return out


def m_rst_only_in_rst_both(text: str) -> bool:
    """m_rst_n_i may appear only in the assign of rst_both_n (and the port list)."""
    code = _strip(text)
    body = code[code.index(") (") :]
    uses = [ln for ln in body.splitlines() if "m_rst_n_i" in ln and "input" not in ln]
    return len(uses) == 1 and "rst_both_n" in uses[0]


def test_bridge_instances_and_raw_reset_use():
    inst = bridge_instances(BRIDGE)
    for name in (
        "u_req_sync",
        "u_ack_sync",
        "u_m_alive_sync",
        "u_m_alive_dly_sync",
        "u_comp_rst_sync",
    ):
        assert name in inst, f"{name} missing"
    assert "u_m_rst_status_sync" not in inst
    assert m_rst_only_in_rst_both(BRIDGE)
    mutated = BRIDGE.replace(".rst_n_i       (m_rst_sync_n)", ".rst_n_i       (m_rst_n_i)", 1)
    if mutated == BRIDGE:
        mutated = BRIDGE.replace(
            "u_m_alive_sync (\n        .clk_i       (s_clk_i),\n"
            "        .rst_n_i     (m_rst_sync_n)",
            "u_m_alive_sync (\n        .clk_i       (s_clk_i),\n        .rst_n_i     (m_rst_n_i)",
            1,
        )
    assert mutated != BRIDGE and not m_rst_only_in_rst_both(mutated)


def constraint_tokens(sdc: str) -> set:
    """Bridge instance names that the CDC constraint text matches."""
    toks = set(
        re.findall(
            r"\bu_(?:req_sync|ack_sync|m_rst_status_sync|m_alive_sync|m_alive_dly_sync|comp_rst_sync)\b",
            sdc,
        )
    )
    return toks


def test_constraint_files_match_existing_instances():
    inst = bridge_instances(BRIDGE)
    for name, sdc in (("sky130", SKY130_CHECK), ("asap7", ASAP7_CHECK)):
        for tok in constraint_tokens(sdc):
            assert tok in inst, f"{name} check file matches {tok}, which the bridge no longer has"
    stale = (
        SKY130_CHECK + '\ncdc_apply_sync_budget x "u_apb_dbg_cdc*u_m_rst_status_sync" 1 a b "d"\n'
    )
    assert any(t not in inst for t in constraint_tokens(stale)), (
        "negative control: stale name not detected"
    )


def async_match_patterns(sdc: str) -> list:
    m = re.search(r"proc cdc_reset_sync_async_pins \{\}.*?\n\}\n", sdc, re.S)
    assert m, "proc cdc_reset_sync_async_pins missing"
    return re.findall(r'string match "([^"]+)"', m.group(0))


def _glob_match(pat: str, name: str) -> bool:
    return re.fullmatch(re.escape(pat).replace(r"\*", ".*"), name) is not None


def covered(sdc: str) -> list:
    """cdc_reset_sync instances of the bridge whose flattened register name no pattern matches."""
    pats = async_match_patterns(sdc)
    miss = []
    for inst, mod in bridge_instances(BRIDGE).items():
        if mod != "cdc_reset_sync":
            continue
        reg = f"u_apb_dbg_cdc.{inst}.sync_q[0]"
        if not any(_glob_match(p, reg) for p in pats):
            miss.append(inst)
    return miss


def test_asap7_async_pin_fallback_exclusion_covers_every_bridge_reset_sync():
    assert covered(ASAP7_CHECK) == []
    # negative control: the pattern list before the destination status chain existed
    old = ASAP7_CHECK.replace('string match "*m_alive_sync*" ', "")
    old = re.sub(r'\|\|\s*\[string match "\*m_alive_sync\*" \[get_full_name \$_reg\]\]', "", old)
    assert "u_m_alive_sync" in covered(re.sub(r"m_alive_sync", "zz_never", ASAP7_CHECK))


def sky130_async_waiver_present(sdc: str) -> bool:
    return bool(
        re.search(r"set_false_path -from \[get_clocks cpu_clk\]\s+-to \$_async_to_core", sdc)
        and re.search(r"set_false_path -from \[get_clocks core_clk\] -to \$_async_to_cpu", sdc)
        and "all_registers -clock core_clk -async_pins" in sdc
    )


def test_sky130_async_pin_waiver_covers_the_status_chain():
    assert sky130_async_waiver_present(SKY130_CHECK)
    assert not sky130_async_waiver_present(SKY130_CHECK.replace("-async_pins", "-data_pins"))


# --- u_apb_pll_cdc: both check files must budget its two level crossings ----------------------


def pll_bridge_budgets(sdc: str) -> dict:
    """Which level crossings of u_apb_pll_cdc the check file budgets, by the names it matches."""
    return {
        "req": bool(
            re.search(r"\*u_apb_pll_cdc\*req_q\*", sdc)
            or re.search(r"cdc_apply_sync_budget \w+ \"u_apb_pll_cdc\*u_req_sync\"", sdc)
        ),
        "ack": bool(
            re.search(r"\*u_apb_pll_cdc\*ack_q\*", sdc)
            or re.search(r"cdc_apply_sync_budget \w+ \"u_apb_pll_cdc\*u_ack_sync\"", sdc)
        ),
    }


def test_pll_bridge_is_an_apb_cdc_bridge_instance_of_soc_top():
    assert re.search(r"\bapb_cdc_bridge\b[^;]*?\bu_apb_pll_cdc\s*\(", _strip(SOC_TOP), re.S)


def test_both_check_files_budget_the_pll_bridge_level_crossings():
    for name, sdc in (("sky130", SKY130_CHECK), ("asap7", ASAP7_CHECK)):
        assert pll_bridge_budgets(sdc) == {"req": True, "ack": True}, name


def test_pll_bridge_budget_names_are_names_of_the_bridge():
    """The sky130 file matches u_req_sync and u_ack_sync, the ASAP7 file matches req_q and ack_q."""
    inst = bridge_instances(BRIDGE)
    assert {"u_req_sync", "u_ack_sync"} <= set(inst)
    code = _strip(BRIDGE)
    assert re.search(r"\blogic\s+req_q\b", code) and re.search(r"\blogic\s+ack_q\b", code)


def test_pll_bridge_budget_negative_controls():
    """A stale instance name and a missing section must both be seen as no budget."""
    for sdc in (SKY130_CHECK, ASAP7_CHECK):
        stale = sdc.replace("u_apb_pll_cdc", "u_apb_pllZ_cdc")
        assert pll_bridge_budgets(stale) == {"req": False, "ack": False}
    # the pll2 budgets must not satisfy the pll bridge pattern
    only_pll2 = ASAP7_CHECK.replace("u_apb_pll_cdc", "u_apb_pll2_cdc")
    assert pll_bridge_budgets(only_pll2) == {"req": False, "ack": False}


def test_pll_bridge_budget_clock_variables_are_per_face():
    """Each face has its own clock and period variable, so a new clock needs no new budget."""
    for sdc in (SKY130_CHECK, ASAP7_CHECK):
        for var in ("_pll_s_clk", "_pll_m_clk", "_pll_s_period", "_pll_m_period"):
            assert re.search(rf"^set {var}\b", sdc, re.M), var
