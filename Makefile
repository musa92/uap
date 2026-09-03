# UAP repository checks. `make test` is the gate CI runs.

PY := python3

.PHONY: test schemas unit links demo serve clean help

help:
	@echo "make test     schemas, refs, invariants, vectors, links, unit tests"
	@echo "make schemas  schema and conformance checks only"
	@echo "make unit     reference implementation tests only"
	@echo "make links    relative markdown links and anchors"
	@echo "make demo     end-to-end Profile L flow, in process"
	@echo "make serve    run the reference exchange on localhost:8787"

test: schemas links unit

schemas:
	@$(PY) scripts/validate.py

links:
	@$(PY) scripts/check_links.py

unit:
	@cd reference/python && $(PY) -m pytest -q

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
