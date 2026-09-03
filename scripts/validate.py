#!/usr/bin/env python3
"""UAP repository validator.

Runs every mechanical check the specification can be held to today:

  1. schema     every schema parses and is a valid JSON Schema 2020-12 document
  2. refs       every $ref resolves, including JSON pointers into $defs
  3. lint       repository conventions ($id matches path, required metadata)
  4. I1         ContextSignal-class schemas admit no free text  (SPEC.md §6.1.5)
  5. money      CPM-denominated values fall in a plausible market band
  6. vectors    conformance vectors validate, or fail, exactly as declared

Exit code is non-zero if any check fails. Intended as the CI gate.
"""
from __future__ import annotations
import json, pathlib, re, sys
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
import jsonschema

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "source" / "schemas"
CONFORMANCE = ROOT / "conformance"
BASE = "https://uap.dev/schemas/"

# Calibrated against the observed market: a sponsored link below a chat answer
# cleared around USD 60 CPM at launch. See docs/documentation/market-context.md §1.
CPM_FLOOR_MICROS = 1_000_000       # USD  1.00 CPM - remnant / tier 0
CPM_CEILING_MICROS = 100_000_000   # USD 100.00 CPM - above any observed clearing

RED, GRN, YEL, DIM, RST = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"


class Results:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.counts: dict[str, int] = {}

    def ok(self, check: str) -> None:
        self.counts[check] = self.counts.get(check, 0) + 1

    def fail(self, check: str, msg: str) -> None:
        self.failures.append(f"{check}: {msg}")

    def warn(self, check: str, msg: str) -> None:
        self.warnings.append(f"{check}: {msg}")


def load_schemas() -> dict[pathlib.Path, dict]:
    out = {}
    for path in sorted(SCHEMA_DIR.rglob("*.json")):
        out[path] = json.loads(path.read_text())
    return out


def build_registry(schemas: dict[pathlib.Path, dict]) -> Registry:
    registry = Registry()
    for path, doc in schemas.items():
        uri = doc.get("$id") or (BASE + path.relative_to(SCHEMA_DIR).as_posix())
        registry = registry.with_resource(uri, Resource(contents=doc, specification=DRAFT202012))
    return registry


def walk(node, path="$"):
    """Yield (json_path, dict_node) for every object in a schema document."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


def check_schemas(schemas, registry, r: Results) -> None:
    validator_cls = jsonschema.Draft202012Validator
    metaschema = validator_cls.META_SCHEMA
    for path, doc in schemas.items():
        rel = path.relative_to(ROOT)
        errs = sorted(validator_cls(metaschema).iter_errors(doc), key=lambda e: e.path)
        if errs:
            for e in errs[:3]:
                r.fail("schema", f"{rel}: {e.message}")
        else:
            r.ok("schema")


def check_refs(schemas, registry, r: Results) -> None:
    for path, doc in schemas.items():
        rel = path.relative_to(ROOT)
        base = doc.get("$id") or (BASE + path.relative_to(SCHEMA_DIR).as_posix())
        resolver = registry.resolver(base_uri=base)
        for jpath, node in walk(doc):
            ref = node.get("$ref") if isinstance(node, dict) else None
            if not isinstance(ref, str):
                continue
            try:
                resolver.lookup(ref)
                r.ok("refs")
            except Exception as exc:  # noqa: BLE001 - report any resolution failure
                r.fail("refs", f"{rel} at {jpath}: $ref {ref!r} did not resolve ({type(exc).__name__})")


def check_lint(schemas, r: Results) -> None:
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    rdn_re = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9][a-z0-9_]*)+$")
    for path, doc in schemas.items():
        rel = path.relative_to(ROOT)
        for field in ("$schema", "$id", "title", "description"):
            if field not in doc:
                r.fail("lint", f"{rel}: missing required top-level {field!r}")
            else:
                r.ok("lint")
        expected = BASE + path.relative_to(SCHEMA_DIR).as_posix()
        if doc.get("$id") not in (None, expected):
            r.fail("lint", f"{rel}: $id {doc['$id']!r} does not match path (expected {expected!r})")
        if "name" in doc:
            if not rdn_re.match(doc["name"]):
                r.fail("lint", f"{rel}: name {doc['name']!r} is not a reverse-domain name")
            if not date_re.match(str(doc.get("version", ""))):
                r.fail("lint", f"{rel}: schema declares 'name' so it needs a YYYY-MM-DD 'version'")


def check_context_signal_closed(schemas, r: Results) -> None:
    """SPEC.md §6.1.5 - every ContextSignal field is a closed enumeration or a
    bounded numeric. A single unbounded string is an I1 hole, so make it a test."""
    targets = [p for p in schemas if "context_signal" in p.name or "context-signal" in p.name]
    if not targets:
        r.warn("I1", "no ContextSignal schema present in source/schemas yet - check is inert")
        return
    for path in targets:
        doc, rel = schemas[path], path.relative_to(ROOT)
        for jpath, node in walk(doc):
            if node.get("type") != "string":
                continue
            bounded = any(k in node for k in ("enum", "const", "pattern", "format", "maxLength"))
            if not bounded:
                r.fail("I1", f"{rel} at {jpath}: unbounded string admits free text (SPEC.md §6.1.5)")
            else:
                r.ok("I1")
        for jpath, node in walk(doc):
            if node.get("type") == "object" and node.get("additionalProperties") is not False:
                if "properties" in node:
                    r.fail("I1", f"{rel} at {jpath}: object must set additionalProperties:false")


def check_money(schemas, r: Results) -> None:
    """A floor three orders of magnitude low silently sells premium inventory at
    remnant prices. It is the most common integration defect, so lint for it."""
    def scan(source: str, doc) -> None:
        for jpath, node in walk(doc):
            for key in ("examples", "default", "const", "minimum"):
                if key not in node:
                    continue
                if "cpm" not in (jpath + source).lower():
                    continue
                vals = node[key] if isinstance(node[key], list) else [node[key]]
                for v in vals:
                    if not isinstance(v, int) or v == 0:
                        continue
                    if v < CPM_FLOOR_MICROS:
                        r.warn("money", f"{source} at {jpath}: {v} micros = USD {v/1e6:.4f} CPM, "
                                        f"below the USD 1.00 remnant floor")
                    elif v > CPM_CEILING_MICROS:
                        r.warn("money", f"{source} at {jpath}: {v} micros = USD {v/1e6:.2f} CPM, "
                                        f"above any observed clearing price")
                    else:
                        r.ok("money")
    for path, doc in schemas.items():
        scan(str(path.relative_to(ROOT)), doc)


def check_vectors(registry, r: Results) -> None:
    manifest_path = CONFORMANCE / "manifest.json"
    if not manifest_path.exists():
        r.warn("vectors", "no conformance/manifest.json")
        return
    manifest = json.loads(manifest_path.read_text())
    for vec in manifest["vectors"]:
        vpath = CONFORMANCE / "vectors" / vec["file"]
        if not vpath.exists():
            r.fail("vectors", f"{vec['file']}: vector file missing")
            continue
        schema_uri = BASE + vec["schema"]
        try:
            schema = registry.get_or_retrieve(schema_uri).value.contents
        except Exception:
            r.fail("vectors", f"{vec['file']}: schema {vec['schema']} not found")
            continue
        validator = jsonschema.Draft202012Validator(schema, registry=registry)
        errors = list(validator.iter_errors(json.loads(vpath.read_text())))
        expect_valid = vec["expect"] == "valid"
        if expect_valid and errors:
            r.fail("vectors", f"{vec['file']}: expected valid, got {errors[0].message}")
        elif not expect_valid and not errors:
            r.fail("vectors", f"{vec['file']}: expected REJECTION but schema accepted it "
                              f"- {vec.get('reason', '')}")
        else:
            r.ok("vectors")


def main() -> int:
    if not SCHEMA_DIR.exists():
        print(f"{RED}no source/schemas directory{RST}")
        return 1
    schemas = load_schemas()
    registry = build_registry(schemas)
    r = Results()

    check_schemas(schemas, registry, r)
    check_refs(schemas, registry, r)
    check_lint(schemas, r)
    check_context_signal_closed(schemas, r)
    check_money(schemas, r)
    check_vectors(registry, r)

    print(f"\n  {len(schemas)} schemas in source/schemas\n")
    labels = {"schema": "JSON Schema 2020-12 validity", "refs": "$ref resolution",
              "lint": "repository conventions", "I1": "context confinement (§6.1.5)",
              "money": "CPM calibration", "vectors": "conformance vectors"}
    for check, label in labels.items():
        n = r.counts.get(check, 0)
        failed = [f for f in r.failures if f.startswith(check + ":")]
        mark = f"{RED}FAIL{RST}" if failed else (f"{GRN}pass{RST}" if n else f"{YEL}skip{RST}")
        print(f"  {mark}  {label:<34} {DIM}{n} checks{RST}")

    for w in r.warnings:
        print(f"\n  {YEL}warning{RST}  {w}")
    for f in r.failures:
        print(f"\n  {RED}FAIL{RST}     {f}")

    total = sum(r.counts.values())
    if r.failures:
        print(f"\n  {RED}{len(r.failures)} failure(s){RST}, {total} checks passed, "
              f"{len(r.warnings)} warning(s)\n")
        return 1
    print(f"\n  {GRN}all {total} checks passed{RST}, {len(r.warnings)} warning(s)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
