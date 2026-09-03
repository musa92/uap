# ImpressionReceipt

**Name** `dev.uap.supply.impression_receipt` · **Version** `2026-09-02` · **Schema** [`supply/impression_receipt.json`](https://uap.dev/schemas/supply/impression_receipt.json)

The billable artefact, emitted and signed by the surface. A claim without a verifiable receipt is not paid.

> **Rationale.** Signed by the surface, not the serving node. The node has both the means and the motive to inflate its own impression counts, so it is not permitted to sign this object. See SPEC.md §9.1.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `receipt_id` | string | yes | *(maxLength 128)* |
| `decision_id` | string | yes | *(maxLength 128)* |
| `nonce` | string | yes | Single-use, exchange-issued. Binds this receipt to exactly one decision. *(maxLength 128)* |
| `placement_id` | string | yes | *(maxLength 128)* |
| `creative_digest` | [`digest`](digest.md) | yes |  |
| `rendered_at` | string (date-time) | yes |  |
| `viewability` | [`viewability`](viewability.md) | yes |  |
| `integrity` | [`integrity_assertion`](integrity_assertion.md) | yes |  |
| `auction_trace` | array \| null |  | REQUIRED in Profile L. Replayable by the exchange that issued the bundle. |
| `trust_tier` | enum: `0`, `1`, `2` | yes |  |
| `attestation` | object \| null |  |  |
| `signature` | [`signature`](signature.md) | yes |  |
| `local_decision` | object |  | Present in Profile L. The inputs the exchange uses to reconstruct the nonce. |

---

*Generated from `source/schemas/supply/impression_receipt.json`. Do not edit; run `make docs`.*
