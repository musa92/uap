# Payout

**Name** `dev.uap.settlement.payout` · **Version** `2026-09-02` · **Schema** [`settlement/payout.json`](https://uap.dev/schemas/settlement/payout.json)

What a serving node, supply agent or model steward is owed for a period, and the state of its disbursement.

> **Rationale.** The other half of the invoice. Where an invoice collects, a payout disburses, and the two are reconciled against the same verified receipt set: an exchange that bills for an impression it does not pay out on is visibly out of balance.
>
> Rejections are itemised for the same reason they are on the invoice. A node told only that its earnings were lower than expected has no way to improve, and no reason to trust the number.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `payout_id` | string | yes | *(maxLength 128)* |
| `account_id` | string | yes | *(maxLength 128)* |
| `entity_id` | string |  | *(maxLength 256)* |
| `party` | enum: `serving_node`, `surface`, `supply_agent`, `model_steward`, `measurement_agent` |  |  |
| `period` | object | yes |  |
| `currency` | [`currency`](currency.md) | yes |  |
| `status` | enum: `accruing`, `pending`, `held`, `sent`, `failed`, `rolled_over` | yes |  |
| `receipts` | object |  |  |
| `gross_micros` | [`micros`](micros.md) | yes | Before the exchange fee and any other party's share. |
| `splits` | array of object |  | How the gross was divided. Basis points sum to 10000. |
| `withholding` | object |  | Tax withheld at source, where the payee's jurisdiction requires it. |
| `net_micros` | [`micros`](micros.md) | yes | This party's share after splits and withholding. What is actually sent. |
| `handler` | [`reverse_domain_name`](reverse_domain_name.md) |  |  |
| `handler_reference` | string |  | The handler's own transfer id, for tracing a payment that did not arrive. *(maxLength 256)* |
| `mandate` | string |  | AP2 settlement mandate committing to this period's verified receipt set. *(maxLength 512)* |
| `sent_at` | string (date-time) |  |  |
| `signature` | [`signature`](signature.md) |  |  |

---

*Generated from `source/schemas/settlement/payout.json`. Do not edit; run `make docs`.*
