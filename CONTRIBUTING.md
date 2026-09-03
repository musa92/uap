# Contributing to UAP

## Before opening a PR

Run the checks. Both must pass.

```bash
make test
cd reference/python && python3 -m pytest -q
```

## What changes are in scope

UAP is a protocol, so the cost of a change is paid by every implementer. The bar
scales accordingly.

| Change | Requirement |
|---|---|
| Typo, clarification, example | PR, one maintainer review |
| New optional field | PR, rationale in the description, a conformance vector |
| New capability or extension | Reverse-DNS name under a domain you control, schema, spec section, vectors, 30-day comment window |
| Change to a normative MUST | Two interoperating implementations demonstrating it |

## What is out of scope

Nothing in §6 (context confinement), §7 (answer integrity), or §9 (earned
payment) may be relaxed by an extension. This is stated so that the answer to
"can we add a mode where the prompt is sent to the ad server?" is a documented
no rather than a negotiation.

An extension that weakens an invariant is out of scope for the registry. The
`invariant_impact` field in `capability.json` has values `none` and
`strengthens`; there is deliberately no value for relaxing one.

## Schema changes

Schemas in `source/` are the source of truth. Follow
[docs/documentation/style.md](./docs/documentation/style.md), which is enforced
by `scripts/validate.py`:

- `description` states what a field is, in at most three sentences. It ships
  into every generated client, so rationale belongs in `$comment`.
- Every enum member is documented.
- Closed objects set `additionalProperties: false`.
- A new constraint needs a conformance vector, and a new *restriction* needs a
  negative vector proving the rejected case is actually rejected.

## Adding a conformance vector

1. Write the instance under `conformance/vectors/valid/` or `invalid/`.
2. Register it in `conformance/manifest.json` with its schema, expectation, and
   for a negative vector the `reason` it must be rejected.
3. Run `make test`.

A negative vector that the schema accepts is reported as a failure, so the suite
detects a loosened schema as readily as a broken one.

## Versioning

Versions are dates, `YYYY-MM-DD`. There are no semantic version numbers. A newer
date MUST be backward compatible for at least 12 months or carry a distinct
capability name.

## Registries

Formats, positions, auction mechanisms, and payout handlers are open registries
keyed by reverse-DNS name. `dev.uap.*` is reserved for this specification.
Anyone may register under a domain they control by opening a PR.

## Reporting a problem in the protocol rather than the code

Open a GitHub Discussion. The most useful contributions are attacks: a signal
combination that defeats the k-anonymity floor, a bundle-fetch pattern that
fingerprints a node, or a way for a node to profit from a fabricated auction
trace.
