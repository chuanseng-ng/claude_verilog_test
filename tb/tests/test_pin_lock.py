"""Unit tests for tools/verif/pin_lock.py (bead lu09): the Sky130 CPU macro pin-coordinate lock."""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "verif"))

import pin_lock as pl  # type: ignore[import-not-found]  # noqa: E402

CPU_LEF = REPO / "pnr" / "sky130" / "cpu" / "macro" / "rv32i_cpu_top.lef"
CPU_DEF = REPO / "pnr" / "sky130" / "cpu" / "pin_template.def"


Pin = tuple[float, float, float, float]

_POWER_PIN = [
    "  PIN VPWR",
    "    DIRECTION INOUT ;",
    "    USE POWER ;",
    "    PORT",
    "      LAYER met4 ;",
    "        RECT 1.000 1.000 2.000 49.000 ;",
    "    END",
    "  END VPWR",
]


def _lef(pins: dict[str, Pin], power: bool = True) -> str:
    out = ["MACRO m", "  SIZE 100.000 BY 50.000 ;"]
    if power:
        out += _POWER_PIN
    for name, (a, b, c, d) in pins.items():
        out += [
            f"  PIN {name}",
            "    DIRECTION INPUT ;",
            "    USE SIGNAL ;",
            "    PORT",
            "      LAYER met2 ;",
            f"        RECT {a:.3f} {b:.3f} {c:.3f} {d:.3f} ;",
            "    END",
            f"  END {name}",
        ]
    out.append("END m")
    return "\n".join(out) + "\n"


def _args(
    lef: Path,
    deff: Path,
    new_lef: str | None = None,
    odb_lef: str | None = None,
    min_space: float = 0.14,
) -> argparse.Namespace:
    return argparse.Namespace(
        lef=str(lef), def_file=str(deff), new_lef=new_lef, odb_lef=odb_lef, min_space=min_space
    )


def _setup(tmp_path: Path, pins: dict[str, Pin]) -> tuple[Path, Path]:
    lef = tmp_path / "m.lef"
    lef.write_text(_lef(pins), encoding="utf-8")
    deff = tmp_path / "m.def"
    deff.write_text(pl.gen_def(lef), encoding="utf-8")
    return lef, deff


BASE = {
    "a[0]": (10.0, 49.0, 10.28, 50.0),
    "a[1]": (20.0, 49.0, 20.28, 50.0),
    "clk": (30.0, 49.0, 30.28, 50.0),
}


def test_committed_template_matches_committed_lef() -> None:
    """The repo's own template must reproduce the committed LEF exactly (this is the CI gate)."""
    assert pl.cmd_check(_args(CPU_LEF, CPU_DEF)) == 0


def test_template_roundtrips_the_lef(tmp_path: Path) -> None:
    lef, deff = _setup(tmp_path, BASE)
    assert pl.parse_def_pins(deff) == {p: r for p, r in pl.lef_rects(lef).items() if p != "VPWR"}


def test_bracketed_bus_names_survive(tmp_path: Path) -> None:
    """Regression: lef_pin_diff's PIN regex used to truncate 'a[0]' to 'a[0'."""
    lef, deff = _setup(tmp_path, BASE)
    assert "a[0]" in pl.lef_rects(lef)
    assert "- a[0] + NET a[0] +" in deff.read_text(encoding="utf-8")


def test_power_pins_excluded(tmp_path: Path) -> None:
    _, deff = _setup(tmp_path, BASE)
    assert "VPWR" not in deff.read_text(encoding="utf-8")


def test_check_passes_when_unchanged(tmp_path: Path) -> None:
    lef, deff = _setup(tmp_path, BASE)
    assert pl.cmd_check(_args(lef, deff, new_lef=str(lef))) == 0


def test_moved_pin_in_new_lef_fails(tmp_path: Path) -> None:
    lef, deff = _setup(tmp_path, BASE)
    moved = dict(BASE, **{"a[1]": (21.0, 49.0, 21.28, 50.0)})
    new = tmp_path / "new.lef"
    new.write_text(_lef(moved), encoding="utf-8")
    assert pl.cmd_check(_args(lef, deff, new_lef=str(new))) == 1


def test_added_pin_in_new_lef_is_not_an_error(tmp_path: Path) -> None:
    lef, deff = _setup(tmp_path, BASE)
    new = tmp_path / "new.lef"
    new.write_text(_lef(dict(BASE, extra=(40.0, 49.0, 40.28, 50.0))), encoding="utf-8")
    assert pl.cmd_check(_args(lef, deff, new_lef=str(new))) == 0


def test_dropped_pin_in_new_lef_fails(tmp_path: Path) -> None:
    lef, deff = _setup(tmp_path, BASE)
    new = tmp_path / "new.lef"
    new.write_text(_lef({k: v for k, v in BASE.items() if k != "clk"}), encoding="utf-8")
    assert pl.cmd_check(_args(lef, deff, new_lef=str(new))) == 1


def test_template_that_moves_a_locked_pin_fails(tmp_path: Path) -> None:
    lef, deff = _setup(tmp_path, BASE)
    text = deff.read_text(encoding="utf-8").replace(
        "( 20000 49000 ) ( 20280 50000 )", "( 21000 49000 ) ( 21280 50000 )"
    )
    deff.write_text(text, encoding="utf-8")
    assert pl.cmd_check(_args(lef, deff)) == 1


def test_template_missing_a_locked_pin_fails(tmp_path: Path) -> None:
    lef, deff = _setup(tmp_path, BASE)
    lines = [
        ln for ln in deff.read_text(encoding="utf-8").splitlines() if not ln.startswith("- clk ")
    ]
    deff.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert pl.cmd_check(_args(lef, deff)) == 1


def test_pending_template_pin_is_allowed(tmp_path: Path) -> None:
    """A PR may add a pin to the template before the re-harden regenerates the LEF."""
    lef, _ = _setup(tmp_path, BASE)
    ext = tmp_path / "ext.lef"
    ext.write_text(_lef(dict(BASE, extra=(40.0, 49.0, 40.28, 50.0))), encoding="utf-8")
    deff = tmp_path / "ext.def"
    deff.write_text(pl.gen_def(ext), encoding="utf-8")
    assert pl.cmd_check(_args(lef, deff)) == 0


def test_overlapping_template_pins_fail(tmp_path: Path) -> None:
    """LibreLane's strict mode does NOT detect two template pins on one slot; this check must."""
    lef, _ = _setup(tmp_path, BASE)
    ext = tmp_path / "ext.lef"
    ext.write_text(_lef(dict(BASE, extra=BASE["a[1]"])), encoding="utf-8")
    deff = tmp_path / "ext.def"
    deff.write_text(pl.gen_def(ext), encoding="utf-8")
    assert pl.cmd_check(_args(lef, deff)) == 1


def test_too_close_template_pins_fail(tmp_path: Path) -> None:
    lef, _ = _setup(tmp_path, BASE)
    ext = tmp_path / "ext.lef"
    ext.write_text(
        _lef(dict(BASE, extra=(10.35, 49.0, 10.63, 50.0))), encoding="utf-8"
    )  # 0.07 um gap
    deff = tmp_path / "ext.def"
    deff.write_text(pl.gen_def(ext), encoding="utf-8")
    assert pl.cmd_check(_args(lef, deff)) == 1
