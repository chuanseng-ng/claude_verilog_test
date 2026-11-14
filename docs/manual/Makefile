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
	@$(PY) ../../tools/docs/gen_fact_tables.py --check; rc=$$?; if [ $$rc -eq 3 ]; then echo "WARNING: pyslang is not installed. The fact-table check is SKIPPED (pip install pyslang==11.0.0)."; elif [ $$rc -ne 0 ]; then exit $$rc; fi
	$(PY) ../../tools/docs/check_requirements.py -v
	$(PY) ../../tools/docs/check_doc_labels.py

clean:
	rm -rf _build
