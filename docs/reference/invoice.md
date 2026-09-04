# Invoice

**Name** `dev.uap.settlement.invoice` · **Version** `2026-09-02` · **Schema** [`settlement/invoice.json`](https://uap.dev/schemas/settlement/invoice.json)

What an advertiser owes for a settlement period, itemised, with every adjustment shown.

> **Rationale.** Buyers reconcile against their own logs and dispute the difference. An invoice that states only a total is a dispute waiting to happen, so line items carry the counts the exchange billed on and adjustments name their cause.
>
> Invalid traffic is credited here rather than silently netted, so a buyer can see what was filtered and challenge it.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `invoice_id` | string | yes | *(maxLength 128)* |
| `account_id` | string | yes | *(maxLength 128)* |
| `period` | object | yes |  |
| `currency` | [`currency`](currency.md) | yes |  |
| `status` | enum: `draft`, `issued`, `disputed`, `paid`, `void` | yes |  |
| `lines` | array of object | yes | *(minItems 1)* |
| `adjustments` | array of object |  | Credits and debits applied after the lines, each naming its cause. |
| `subtotal_micros` | [`micros`](micros.md) |  |  |
| `tax` | object |  |  |
| `total_micros` | [`micros`](micros.md) | yes |  |
| `due_at` | string (date-time) |  |  |
| `issued_at` | string (date-time) |  |  |
| `mandate` | string |  | AP2 payment mandate derived for this invoice. *(maxLength 512)* |
| `signature` | [`signature`](signature.md) |  |  |

---

*Generated from `source/schemas/settlement/invoice.json`. Do not edit; run `make docs`.*
