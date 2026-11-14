"""Shared LaTeX table builder of the tools that write tables into the books."""

from __future__ import annotations

COL_PREFIX = ">{\\raggedright\\arraybackslash}"


def longtable(
    cols: tuple[str, ...], caption: str, label: str, heads: list[str], rows: list[list[str]]
) -> str:
    """Return one complete longtable. A column is a p{} specification."""
    spec = "@{}" + "".join(f"{COL_PREFIX}{c}" for c in cols) + "@{}"
    head = " & ".join(heads) + "\\\\"
    out = [
        "{\\small",
        f"\\begin{{longtable}}{{{spec}}}",
        f"\\caption{{{caption}}}\\label{{{label}}}\\\\",
        "\\toprule",
        head,
        "\\midrule",
        "\\endfirsthead",
        f"\\multicolumn{{{len(cols)}}}{{@{{}}l}}{{\\emph{{Table \\thetable\\ continued}}}}\\\\",
        "\\toprule",
        head,
        "\\midrule",
        "\\endhead",
        "\\bottomrule",
        "\\endlastfoot",
    ]
    out += [" & ".join(r) + "\\\\" for r in rows]
    out += ["\\end{longtable}", "}"]
    return "\n".join(out)
