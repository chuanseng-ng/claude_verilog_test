"""Check that the TeX packages of the book class are in the Nix TeX set of flake.nix.

MiKTeX installs a missing package on demand and hides a gap in the Nix list. The documentation
workflow builds with the Nix set only. This test finds the gap before the build does.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMMON = REPO / "docs" / "manual" / "common"

# A package that the LaTeX kernel provides, or that has another name in the TeX Live set.
KERNEL = {"xparse"}
COLLECTION = {
    "amssymb": "amsfonts",
    "graphicx": "graphics",
    "array": "tools",
    "calc": "tools",
    "longtable": "tools",
    "xr-hyper": "hyperref",
    "tikz": "pgf",
}


def flake_packages() -> set[str]:
    """Return the package names of the docs TeX set in flake.nix."""
    text = (REPO / "flake.nix").read_text(encoding="utf-8")
    start = text.index("docsTexFor = pkgs:")
    block = re.search(r"inherit \(pkgs\.texlive\)(.*?);", text[start:], re.S)
    assert block, "the docs TeX set was not found in flake.nix"
    return set(block.group(1).split())


def required_packages() -> set[str]:
    """Return the package names that the class and the macro files load."""
    names: set[str] = set()
    for path in sorted([*COMMON.glob("*.cls"), *COMMON.glob("*.sty")]):
        text = "\n".join(
            re.sub(r"(?<!\\)%.*", "", line)
            for line in path.read_text(encoding="utf-8").splitlines()
        )
        for m in re.finditer(r"\\RequirePackage\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", text):
            names.update(n.strip() for n in m.group(1).split(",") if n.strip())
    return names


def missing_packages(required: set[str], have: set[str], local: set[str]) -> list[str]:
    """Return the required packages that the TeX set does not cover."""
    return [
        name
        for name in sorted(required - KERNEL - local)
        if name not in have and COLLECTION.get(name) not in have
    ]


def test_every_required_package_is_in_the_nix_set() -> None:
    """Each RequirePackage maps to a name in the docs TeX set."""
    local = {p.stem for p in COMMON.glob("*.sty")}
    missing = missing_packages(required_packages(), flake_packages(), local)
    assert not missing, f"not in docsTexFor of flake.nix: {missing}"


def test_figure_packages_are_listed_explicitly() -> None:
    """The set names pgf and tikz-timing, so that a smaller scheme cannot drop them."""
    have = flake_packages()
    assert {"pgf", "tikz-timing"} <= have


def test_the_check_can_fail() -> None:
    """A package that no entry covers is reported, and the mapped and kernel names are not."""
    have = {"hyperref", "pgf", "tools", "booktabs"}
    required = {"no-such-package", "xr-hyper", "tikz", "array", "booktabs", "xparse", "cvtmacros"}
    assert missing_packages(required, have, {"cvtmacros"}) == ["no-such-package"]
    assert missing_packages({"tikz"}, {"hyperref"}, set()) == ["tikz"]
