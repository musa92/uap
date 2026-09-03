# Placement

**Name** `dev.uap.supply.placement` · **Version** `2026-09-02` · **Schema** [`supply/placement.json`](https://uap.dev/schemas/supply/placement.json)

An advertising slot on a generated turn, described by the surface rather than by pixels.

> **Rationale.** Format ranking by observed market outcome, per docs/documentation/market-context.md §2:

```text
  sponsored_link at post_answer   REQUIRED to implement; the format that cleared ~USD 60 CPM
  sponsored_card at post_answer   RECOMMENDED
  product_offer                   RECOMMENDED with the uap.commerce profile
  sponsored_action                OPTIONAL; untested in LLM surfaces, highest integrity risk
  sponsored_suggestion            OPTIONAL, NOT RECOMMENDED; withdrawn after minimal revenue
```

> `position: inline` -- interleaved into the answer body -- is intentionally absent from the position enum. It cannot satisfy I2. Implementations wanting in-body commercial content use post_answer with an explicit structural break.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `placement_id` | string | yes | *(maxLength 128)* |
| `surface` | object | yes |  |
| `position` | enum: `post_answer`, `sidebar`, `followup_suggestion`, `inline_citation`, `pre_answer` | yes | 'inline' (interleaved into the answer body) is intentionally absent: it cannot satisfy the answer-integrity invariant. |
| `format` | enum: `sponsored_link`, `sponsored_card`, `sponsored_suggestion`, `product_offer`, `sponsored_action` | yes |  |
| `constraints` | object |  |  |
| `disclosure` | object | yes |  |
| `floor_cpm_micros` | [`cpm`](cpm.md) |  | Minimum acceptable clearing price for this placement. |
| `max_ads` | integer |  | *(minimum 0, maximum 3)* |

---

*Generated from `source/schemas/supply/placement.json`. Do not edit; run `make docs`.*
