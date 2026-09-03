# Campaign

**Name** `dev.uap.demand.campaign` · **Version** `2026-09-02` · **Schema** [`demand/campaign.json`](https://uap.dev/schemas/demand/campaign.json)

A buyer's top-level unit of spend: an objective, a budget, a flight, and the line items that execute it.

> **Rationale.** Mirrors the hierarchy every buying platform already exposes (account, campaign, ad group, ad; here advertiser, campaign, line item, creative) so that an agency's tooling maps onto it without a new mental model. The objective vocabulary matches what the market buys against: reach prices on CPM, clicks on CPC, conversions on CPA.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `campaign_id` | string | yes | *(maxLength 128)* |
| `advertiser_id` | string | yes | *(maxLength 256)* |
| `name` | string | yes | *(maxLength 200)* |
| `objective` | enum: `reach`, `clicks`, `conversions`, `sponsorship` | yes |  |
| `status` | enum: `draft`, `active`, `paused`, `completed`, `archived` | yes |  |
| `budget` | object | yes |  |
| `flight` | object |  |  |
| `supply` | object |  | Where this campaign may run. |
| `line_items` | array of [`line_item`](line_item.md) |  | *(maxItems 500)* |
| `labels` | object |  | Buyer-defined key/values for reporting breakdowns. |
| `created_at` | string (date-time) |  |  |
| `updated_at` | string (date-time) |  |  |

---

*Generated from `source/schemas/demand/campaign.json`. Do not edit; run `make docs`.*
