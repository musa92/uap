# UAP repository checks. `make test` is the gate CI runs.

PY := python3

.PHONY: test schemas unit interop interop-gen links terms spelling markdown lint docs docs-check docs-serve demo serve clean help

help:
	@echo "make test      everything CI runs"
	@echo "make schemas   schemas, refs, invariants, conformance vectors"
	@echo "make unit      reference implementation tests"
	@echo "make lint      spelling, terminology, markdown, links"
	@echo "make interop   cross-implementation conformance, Python against JavaScript"
	@echo "make docs      regenerate the schema reference from source/schemas"
	@echo "make docs-serve  run the documentation site locally"
	@echo "make demo      end-to-end flow, in process then over HTTP"
	@echo "make serve     reference exchange on localhost:8787"

test: schemas lint docs-check unit interop

schemas:
	@$(PY) scripts/validate.py

lint: spelling terms markdown links

spelling:
	@npm run --silent lint:spelling

terms:
	@$(PY) scripts/check_terminology.py

markdown:
	@npm run --silent lint:markdown

links:
	@$(PY) scripts/check_links.py

docs:
	@$(PY) scripts/gen_schema_docs.py

docs-check:
	@$(PY) scripts/gen_schema_docs.py --check

docs-serve: docs
	@mkdocs serve

unit:
	@cd reference/python && $(PY) -m pytest -q

# Regenerate the vectors the JavaScript implementation is checked against.
interop-gen:
	@$(PY) scripts/gen_interop_vectors.py

# Two implementations, written from the specification, must agree byte for byte.
interop:
	@cd reference/typescript && node --test test/interop.test.js

demo:
	@$(PY) reference/python/demo/end_to_end.py
	@$(PY) reference/python/demo/over_http.py

serve:
	@$(PY) -c "import sys; sys.path.insert(0,'reference/python'); \
	from uap import Exchange, SigningKey; from uap.server import serve; \
	serve(Exchange('uax.local', SigningKey.generate('uax-1')))"

clean:
	@find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -name '.pytest_cache' -type d -prune -exec rm -rf {} + 2>/dev/null || true
