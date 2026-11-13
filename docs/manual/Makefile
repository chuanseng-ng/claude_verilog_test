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
	$(PY) ../../tools/docs/check_doc_labels.py

clean:
	rm -rf _build
