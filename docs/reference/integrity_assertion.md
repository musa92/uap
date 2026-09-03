# Integrity Assertion

**Schema** [`common/types/integrity_assertion.json`](https://uap.dev/schemas/common/types/integrity_assertion.json)

Operator attestations that the answer-integrity boundary held for this turn. All four members are REQUIRED and constrained to `true`; a turn that cannot assert them is not billable.

> **Rationale.** Defined by SPEC.md §7 (invariant I2).
>
> There is deliberately no conformant encoding for a violated boundary. Admitting decode influence is a settlement-level breach, not a field value.
>
> Commercial basis: survey evidence indicates roughly two thirds of US adults report lower trust in AI answers when ads are present (Ipsos). In retail media, the nearest structural analogue, 30-40% of sponsored-product sales are estimated to cannibalize purchases that would have occurred organically. A surface that bends its answers converges on display CPMs. See docs/documentation/market-context.md §3.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `organic_answer_digest` | [`digest`](digest.md) | yes | Digest of the exact bytes shown to the user as the answer, excluding the ad block and its separator. |
| `no_decode_influence` | const `true` | yes | Asserts that no bid value, advertiser identity, or campaign state was an input to generation. |
| `ad_excluded_from_context` | const `true` | yes | Asserts that creative content did not enter the model's context for this turn and will be stripped before any subsequent summarization or re-feed. |
| `disclosure_rendered` | const `true` | yes | Asserts that the disclosure was rendered in-band before or at the moment the user could act on the placement. |
| `composer` | object |  | Identifies the function that joined answer and creative. |

---

*Generated from `source/schemas/common/types/integrity_assertion.json`. Do not edit; run `make docs`.*
