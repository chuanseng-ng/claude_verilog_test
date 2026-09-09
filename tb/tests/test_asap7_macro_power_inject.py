"""Unit tests for pnr/scripts/asap7_macro_power_inject.py (bead 86a).

Why these exist: the injector writes power numbers into the macro Liberty files
that every SoC-level `report_power` then trusts. A silent unit-parsing error
there does not crash anything -- it produces a plausible-looking figure that is
wrong by orders of magnitude, which is exactly the failure mode bead `7l5`
exists to prevent. The Liberty scalar unit for `internal_power` is declared
nowhere in these files and had to be derived empirically, so the header-unit
parsing in particular is worth pinning down.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INJECTOR = REPO_ROOT / "pnr" / "scripts" / "asap7_macro_power_inject.py"


def _load():
    spec = importlib.util.spec_from_file_location("asap7_macro_power_inject", INJECTOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load()


class TestParseUnit:
    @pytest.mark.parametrize(
        "raw, expect_value, expect_base",
        [
            ('"1pW"', 1.0, 1e-12),
            ("1pW", 1.0, 1e-12),
            ("(1,fF)", 1.0, 1e-15),
            ('"10fF";', 10.0, 1e-15),
            ("1V", 1.0, 1.0),
        ],
    )
    def test_accepts_the_liberty_spellings_actually_seen(self, raw, expect_value, expect_base):
        value, mult = mod.parse_unit(raw)
        assert value == pytest.approx(expect_value)
        assert mult == pytest.approx(expect_base)

    def test_rejects_unknown_suffix_rather_than_guessing(self):
        # Silently defaulting an unrecognised suffix would put the injected
        # power off by orders of magnitude with no visible failure.
        with pytest.raises(ValueError, match="unrecognized unit suffix"):
            mod.parse_unit("1qW")

    def test_rejects_unparseable_input(self):
        with pytest.raises(ValueError, match="cannot parse Liberty unit"):
            mod.parse_unit("not a unit")


class TestParseHeaderUnits:
    # Attributes are anchored at line start by parse_header_units' ^-regex,
    # which is how they appear in a real Liberty file.
    HEADER = """library (macro) {
capacitive_load_unit (1,fF);
voltage_unit : "1V";
leakage_power_unit : "1pW";
}
"""

    def test_derives_all_three_base_units(self):
        cload_f, volt_v, leak_w = mod.parse_header_units(self.HEADER)
        assert cload_f == pytest.approx(1e-15)
        assert volt_v == pytest.approx(1.0)
        assert leak_w == pytest.approx(1e-12)

    def test_internal_power_scalar_unit_is_cload_times_voltage_squared(self):
        # This is the empirically-derived relationship (single-cell test lib):
        # the implicit internal_power unit is capacitive_load_unit * voltage_unit^2,
        # = 1 fJ for the ASAP7 macro libs -- NOT 1 pJ or 1 nJ.
        cload_f, volt_v, _ = mod.parse_header_units(self.HEADER)
        assert cload_f * volt_v**2 == pytest.approx(1e-15)

    def test_missing_required_declaration_raises(self):
        with pytest.raises(ValueError, match="voltage_unit"):
            mod.parse_header_units(
                'library (m) {\ncapacitive_load_unit (1,fF);\nleakage_power_unit : "1pW";\n}\n'
            )


class TestParsePowerReport:
    # OpenSTA prints the Total row starting at column 0; TOTAL_ROW_RE anchors there.
    REPORT = """Group                  Internal  Switching    Leakage      Total
                          Power      Power      Power      Power (Watts)
----------------------------------------------------------------
Sequential             1.00e-02   2.00e-03   3.00e-04   1.23e-02
Total                  2.17e-01   1.10e-02   5.46e-03   2.34e-01
"""

    def test_extracts_the_total_row(self):
        internal, switching, leakage, total = mod.parse_power_report(self.REPORT)
        assert internal == pytest.approx(2.17e-01)
        assert switching == pytest.approx(1.10e-02)
        assert leakage == pytest.approx(5.46e-03)
        assert total == pytest.approx(2.34e-01)

    def test_absent_total_row_raises_rather_than_returning_zeros(self):
        # A report that produced no Total row must not be read as 0.00 W --
        # that is precisely the 0.00 W macro figure this bead exists to fix.
        with pytest.raises(ValueError, match="no 'Total"):
            mod.parse_power_report("Group Internal Switching Leakage Total\n(no rows)\n")
