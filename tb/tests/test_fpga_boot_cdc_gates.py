"""Tests for the FPGA board-flow gates (beads hlrm.3, hlrm.4).

Covers tools/fpga/boot_image.py and tools/fpga/cdc_gate.py. No Vivado and no RISC-V toolchain:
the boot gate runs on the committed image and tampered copies; the CDC gate on synthetic reports.
"""
# pylint: disable=missing-function-docstring,missing-class-docstring,invalid-name,protected-access,import-error

import argparse
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "fpga"))

import boot_image as bi  # type: ignore[import-not-found]  # noqa: E402
import cdc_gate as cg  # type: ignore[import-not-found]  # noqa: E402

NS = argparse.Namespace()


# ---- boot_image.py --------------------------------------------------------------------------


def test_committed_boot_image_passes_check() -> None:
    assert bi.cmd_check(NS) == 0


def test_committed_image_is_the_bootloader_not_a_placeholder() -> None:
    words = bi.HEX.read_text().split()
    assert 100 < len(words) <= bi.ROM_WORDS
    # placeholder was `jal x0,0` then NOPs (0x0000006f / 0x00000013): the real image is not that
    assert len(set(words)) > 50


@pytest.fixture(name="sandbox")
def fixture_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copy(bi.HEX, tmp_path / "boot_uart.hex")
    shutil.copy(bi.MANIFEST, tmp_path / "boot_uart.manifest.json")
    monkeypatch.setattr(bi, "HEX", tmp_path / "boot_uart.hex")
    monkeypatch.setattr(bi, "MANIFEST", tmp_path / "boot_uart.manifest.json")
    return tmp_path


def test_check_detects_hand_edited_hex(sandbox: Path) -> None:
    hexp = sandbox / "boot_uart.hex"
    lines = hexp.read_text().splitlines()
    lines[3] = "deadbeef" if lines[3] != "deadbeef" else "00000000"
    hexp.write_text("\n".join(lines) + "\n")
    assert bi.cmd_check(NS) == 1


def test_check_detects_stale_source_hash(sandbox: Path) -> None:
    man = json.loads((sandbox / "boot_uart.manifest.json").read_text())
    man["sources"]["sw/bootloader/uart_boot.c"] = "0" * 64
    (sandbox / "boot_uart.manifest.json").write_text(json.dumps(man))
    assert bi.cmd_check(NS) == 1


def test_check_detects_param_drift(sandbox: Path) -> None:
    man = json.loads((sandbox / "boot_uart.manifest.json").read_text())
    man["params"]["SRAM_BYTES"] = "4096"
    (sandbox / "boot_uart.manifest.json").write_text(json.dumps(man))
    assert bi.cmd_check(NS) == 1


def test_check_hex_rejects_malformed_and_oversize(tmp_path: Path) -> None:
    bad = tmp_path / "bad.hex"
    bad.write_text("0000006f\nnothex!!\n")
    assert bi.check_hex(bad)[1]
    big = tmp_path / "big.hex"
    big.write_text("00000013\n" * (bi.ROM_WORDS + 1))
    assert bi.check_hex(big)[1]


def test_check_missing_files_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(bi, "HEX", tmp_path / "absent.hex")
    assert bi.cmd_check(NS) == 2


def test_makefile_params_match_manifest_params() -> None:
    mk = (ROOT / "fpga" / "nexys_video" / "Makefile").read_text()
    assert f"SRAM_BYTES := {bi.PARAMS['SRAM_BYTES']}" in mk
    assert f"EXTRA_DEFS := {bi.PARAMS['EXTRA_DEFS']}" in mk


# ---- cdc_gate.py ----------------------------------------------------------------------------

HEADER = "CDC Report\n\nID      Severity  Count  Description\n------  --------  -----  ----\n"


def _report(summary: list[tuple[str, str, int]], rows: list[tuple[str, str, str, str]]) -> str:
    out = HEADER
    for cid, sev, n in summary:
        out += f"{cid:<7} {sev:<9} {n:>5}  desc\n"
    out += "\nSource Clock: a\nDestination Clock: b\n\nRow  ID\n"
    for i, (cid, sev, src, dst) in enumerate(rows, 1):
        out += f" {i:>3}  {cid:<6} {sev:<8}  Some description   2  Max Delay  {src}   {dst}\n"
    return out


def _run(tmp_path: Path, text: str, *flags: str) -> int:
    rpt = tmp_path / "cdc.rpt"
    rpt.write_text(text)
    sys.argv = ["cdc_gate.py", str(rpt), *flags]
    return int(cg.main())


PMU = (
    "CDC-10",
    "Critical",
    "u_soc/u_pmu/dom_state_q_reg[0][3]/C",
    "u_soc/u_cpu_clk_dis_sync/sync_q_reg[0][0]/D",
)
OTHER = ("CDC-1", "Critical", "u_soc/u_x/mem_q_reg/CLK", "u_soc/u_y/q_reg/D")


def test_gate_passes_with_only_rtl_open_rows(tmp_path: Path) -> None:
    assert _run(tmp_path, _report([("CDC-10", "Critical", 1)], [PMU])) == 0


def test_gate_strict_fails_on_rtl_open_rows(tmp_path: Path) -> None:
    assert _run(tmp_path, _report([("CDC-10", "Critical", 1)], [PMU]), "--strict") == 1


def test_gate_fails_on_unexplained_critical(tmp_path: Path) -> None:
    assert (
        _run(tmp_path, _report([("CDC-10", "Critical", 1), ("CDC-1", "Critical", 1)], [PMU, OTHER]))
        == 1
    )


def test_gate_summary_detail_mismatch_is_not_a_pass(tmp_path: Path) -> None:
    assert _run(tmp_path, _report([("CDC-1", "Critical", 5)], [OTHER])) == 2


def test_gate_clean_report_passes_strict(tmp_path: Path) -> None:
    assert _run(tmp_path, _report([("CDC-3", "Info", 54)], []), "--strict") == 0


def test_gate_rejects_non_report_and_missing_file(tmp_path: Path) -> None:
    assert _run(tmp_path, "hello\n") == 2
    sys.argv = ["cdc_gate.py", str(tmp_path / "nope.rpt")]
    assert cg.main() == 2
