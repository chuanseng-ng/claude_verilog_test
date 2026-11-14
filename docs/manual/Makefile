# Build the project books. One build path: tools/docs/build_books.py.
PY ?= python3
BUILD = $(PY) ../../tools/docs/build_books.py

.PHONY: all ds tm um cr check clean

all:
	$(BUILD)

ds tm um cr:
	$(BUILD) $@

check:
	$(PY) ../../tools/docs/gen_glossary.py --check
	@$(PY) ../../tools/docs/gen_fact_tables.py --check || { rc=$$?; if [ $$rc -eq 3 ]; then echo "ERROR: pyslang is not installed, so the fact-table check cannot run (nix develop .#docs provides it; otherwise pip install pyslang==11.0.0)." >&2; fi; exit $$rc; }
	$(PY) ../../tools/docs/check_requirements.py -v
	$(PY) ../../tools/docs/check_doc_labels.py

clean:
	rm -rf _build
