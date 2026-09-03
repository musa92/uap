# BidResponse

**Name** `dev.uap.demand.bid_response` · **Version** `2026-09-02` · **Schema** [`demand/bid_response.json`](https://uap.dev/schemas/demand/bid_response.json)

A demand agent's reply to an AdRequest. An empty `bids` array is a valid no-bid and MUST NOT be treated as an error.

> **Rationale.** Maps to an OpenRTB 2.6 BidResponse. A demand agent implementing this endpoint participates in hosted decisioning. Real-time bidding is not the only way in: a buyer may instead ship line items to the exchange for inclusion in campaign bundles, which requires no low-latency infrastructure at all and is how Profile L supply is filled. See docs/documentation/integration.md.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `request_id` | string | yes | Echoes AdRequest.id. *(maxLength 128)* |
| `currency` | [`currency`](currency.md) |  |  |
| `bids` | array of [`bid`](#definitions) | yes | *(maxItems 32)* |
| `no_bid_reason` | enum: `no_matching_campaign`, `budget_exhausted`, `blocked_by_policy`, `unsupported_format`, `below_floor`, `signal_insufficient`, … (8 values) |  | Why no bid was returned. Optional but strongly encouraged. |

## Definitions

### `bid`

| Property | Type | Required | Description |
|---|---|---|---|
| `bid_id` | string | yes | *(maxLength 128)* |
| `placement_id` | string | yes | The placement this bid is for. *(maxLength 128)* |
| `deal_id` | string |  | Present when bidding into a pre-negotiated deal. *(maxLength 128)* |
| `seat` | string |  | Buyer seat, matched against seats_allowed and seats_blocked. *(maxLength 64)* |
| `pricing` | object | yes | Exactly one amount member must be present, matching `model`. |
| `creative` | [`creative`](creative.md) | yes |  |
| `advertiser` | object | yes |  |
| `attribution` | object |  |  |
| `expires_at` | string (date-time) |  |  |

---

*Generated from `source/schemas/demand/bid_response.json`. Do not edit; run `make docs`.*
