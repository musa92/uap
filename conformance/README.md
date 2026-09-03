# Conformance vectors

Each vector is validated against exactly one schema with an explicit
expectation, declared in `manifest.json`. Run them with `make test` from the
repository root.

## Why the negative vectors matter more

A suite that only proves valid documents are accepted proves almost nothing — an
empty schema passes that. The `invalid/` vectors assert that specific,
commercially motivated lies are **structurally impossible to express**:

| Vector | The lie it makes unrepresentable |
|---|---|
| `viewability-delivered-only-claims-viewable` | A surface with no pixels reporting a viewable impression. The cheapest way to inflate a rate card. |
| `viewability-viewable-without-evidence` | A viewability claim carrying no measurement to support it. |
| `supply-chain-hop-without-anchor` | An unauthorized hop in the supply chain. `anchor` is REQUIRED — including the honest value `none`. |
| `sellers-unknown-seller-type` | A seller type outside the closed IAB set that buyer tooling depends on. |
| `integrity-decode-influence-admitted` | Admitting that a bid influenced decoding. There is deliberately no conformant way to say this. |
| `signature-padded-base64` | Padded base64url, the classic cross-implementation signature mismatch. |

## Adding a vector

1. Write the instance under `vectors/valid/` or `vectors/invalid/`.
2. Register it in `manifest.json` with its `schema`, `expect`, and — for a
   negative vector — the `reason` it must be rejected.
3. Run `make test`.

A negative vector that the schema accepts is reported as a failure, so the suite
detects a schema that has been loosened as readily as one that has been broken.
