# LineItem

**Name** `dev.uap.demand.line_item` · **Version** `2026-09-02` · **Schema** [`demand/line_item.json`](https://uap.dev/schemas/demand/line_item.json)

The unit of demand that an auction ranks. A campaign owns one or more line items; a campaign bundle carries the subset eligible for a node. Targeting is a closed predicate over ContextSignal fields only.

> **Rationale.** Previously defined only by example in SPEC.md §8.2. Promoted to a first-class schema because it is the object shared by the campaign API (buyer creates it), the bundle (exchange ships it), and the auction trace (node reports it). One definition, three consumers.
>
> Maps to an OpenRTB line of demand at the DSP, and to a Google Ads ad group: the level at which bid, budget share, and targeting are set.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `line_item_id` | string | yes | *(maxLength 128)* |
| `campaign_id` | string |  | Owning campaign. Absent inside a bundle, where campaign structure is not the node's concern. *(maxLength 128)* |
| `advertiser` | object | yes |  |
| `status` | enum: `draft`, `in_review`, `active`, `paused`, `exhausted`, `ended`, … (7 values) | yes | Lifecycle state. |
| `targeting` | object |  | Appendix A predicate over ContextSignal. Depth <= 8, terms <= 64. |
| `pricing` | object | yes |  |
| `pacing` | object |  |  |
| `frequency_cap` | object |  |  |
| `flight` | object |  |  |
| `deal_id` | string |  | Present when this line item transacts under a pre-negotiated deal. *(maxLength 128)* |
| `categories` | array of string |  | *(maxItems 16)* |
| `brand_safety` | object |  | Buyer-side suitability requirements, GARM categories. |
| `creatives` | array of [`creative`](creative.md) | yes | *(minItems 1, maxItems 16)* |
| `expires_at` | string (date-time) |  | Inside a bundle: when this entry MUST be discarded. |

---

*Generated from `source/schemas/demand/line_item.json`. Do not edit; run `make docs`.*
