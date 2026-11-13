# Documentation

The project documentation is in four LaTeX books. Each book builds to a PDF.
The guide for agents and contributors is [`AGENTS.md`](../AGENTS.md) in the repository root.

| Book | Source | Content |
| :--- | :----- | :------ |
| Design Specification (`ds`) | `docs/manual/ds/` | What the design must do |
| Technical Manual (`tm`) | `docs/manual/tm/` | How the design and the flows work |
| User Manual (`um`) | `docs/manual/um/` | How to use the project |
| Changes record (`cr`) | `docs/manual/cr/` | History of the project |

Shared files are in `docs/manual/common/`: the class `cvtdocs.cls`, the macros
`cvtmacros.sty`, the term list `dictionary.yaml`, the generated `glossary.tex` and
`labels.tsv`, and `path_map.tsv`.

## Build

LuaLaTeX and Python 3 with PyYAML are the only requirements. Run from the repository root.

```bash
python tools/docs/build_books.py          # all books, PDFs in docs/manual/_build/
python tools/docs/build_books.py um       # one book
python tools/docs/gen_glossary.py         # regenerate glossary.tex after you edit dictionary.yaml
python tools/docs/check_doc_labels.py     # check labels, citations and paths
```

The directory `docs/manual/_build/` holds build output. Do not commit it.

## Labels

A label has the form `book:kind:slug`, for example `ds:ch:mod-cdc-primitives`. A source file cites
a label with one comment line:

```text
// Doc: ds:ch:mod-cdc-primitives
```

Use `#` in place of `//` in Python, Tcl and shell files. Labels do not change when sections
move. Search `docs/manual/common/labels.tsv` to find a label. The chapter "Documentation
system" in the User Manual has the full rules.

## Where the old Markdown files went

No other Markdown file remains in `docs/`. The content of each one is in a book.
`docs/manual/common/path_map.tsv` has one row for each old path: the old path, the new
file and the label. Use it to find the new place of a path that an old note or a git commit
cites. Local `README.md` files next to the code (`pnr/`, `tools/`, `tb/`, `hls/`, `fpga/`,
`sw/`) stay Markdown.
