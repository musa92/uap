# Forecast

**Name** `dev.uap.demand.forecast` · **Version** `2026-09-02` · **Schema** [`demand/forecast.json`](https://uap.dev/schemas/demand/forecast.json)

Available inventory and expected delivery for a proposed line item, before any budget is committed.

> **Rationale.** The first thing a buyer asks for and the thing draft-01 lacked entirely. Every figure is an aggregate over at least the k-anonymity floor of users; a forecast cell that would describe fewer users is suppressed, not rounded, because a narrow forecast is a targeting oracle.

## Definitions

### `request`

| Property | Type | Required | Description |
|---|---|---|---|
| `targeting` | object | yes | Appendix A predicate. |
| `pricing` | [`pricing`](line_item.md) | yes |  |
| `flight` | [`flight`](line_item.md) | yes |  |
| `supply` | [`supply`](campaign.md) |  |  |
| `formats` | array of enum: `sponsored_link`, `sponsored_card`, `sponsored_suggestion`, `product_offer`, `sponsored_action` |  |  |
| `frequency_cap` | [`frequency_cap`](line_item.md) |  |  |

### `response`

| Property | Type | Required | Description |
|---|---|---|---|
| `forecast_id` | string | yes | *(maxLength 128)* |
| `generated_at` | string (date-time) | yes |  |
| `valid_until` | string (date-time) | yes |  |
| `matched` | object | yes | Inventory the targeting would reach over the flight, regardless of bid. |
| `estimate` | object | yes | Expected delivery at the proposed bid, given competing demand. |
| `suppressed` | array of string |  | Breakdowns withheld because they fell below the k-anonymity floor. |

### `range`

> **Rationale.** Forecasts are ranges, never points. A point estimate implies a precision no forecast has, and buyers plan against the low end.

| Property | Type | Required | Description |
|---|---|---|---|
| `low` | integer | yes | *(minimum 0)* |
| `high` | integer | yes | *(minimum 0)* |

---

*Generated from `source/schemas/demand/forecast.json`. Do not edit; run `make docs`.*
