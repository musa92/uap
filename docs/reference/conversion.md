# ConversionEvent

**Name** `dev.uap.demand.conversion` · **Version** `2026-09-02` · **Schema** [`demand/conversion.json`](https://uap.dev/schemas/demand/conversion.json)

A server-to-server report that a click led to an outcome. Sent by the advertiser or through an AP2 payment mandate reference, never by the serving node.

> **Rationale.** SPEC.md §9.2. The node cannot observe a conversion and has every incentive to guess high, so the only parties that may report one are the advertiser, from its own systems, and the payment rail, by mandate reference. The join key is the click_id issued in the Decision, which carries no user identity.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `event_id` | string | yes | Idempotency key; a repeat is ignored, not double-counted. *(maxLength 128)* |
| `click_id` | string | yes | From the Decision that produced the click. Must be within the line item's conversion window. *(maxLength 128)* |
| `event_type` | enum: `purchase`, `signup`, `lead`, `install`, `add_to_cart`, `subscribe`, … (7 values) | yes |  |
| `custom_type` | string |  | Required when event_type is custom. *(maxLength 64)* |
| `occurred_at` | string (date-time) | yes |  |
| `value` | object |  |  |
| `source` | object | yes |  |
| `signature` | [`signature`](signature.md) |  | Signed by the advertiser's enrolled key. |

## Conditional constraints

- **Constraint.**

---

*Generated from `source/schemas/demand/conversion.json`. Do not edit; run `make docs`.*
