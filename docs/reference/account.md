# Account

**Name** `dev.uap.settlement.account` · **Version** `2026-09-02` · **Schema** [`settlement/account.json`](https://uap.dev/schemas/settlement/account.json)

The commercial relationship between a participant and an exchange. Every party that pays or is paid has one.

> **Rationale.** Cryptographic identity and commercial identity are separate in UAP. A signing key proves who sent a message; an account determines who gets billed or paid. A valid signature over a key with no account is trust tier 0: it can serve, and it can be paid on CPA, but it cannot sell CPM (SPEC.md §9.3).
>
> One schema covers both sides because the lifecycle is the same. What differs is direction: an advertiser account accrues a payable, a payee account accrues a receivable.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | *(maxLength 128)* |
| `entity_id` | string | yes | The participant this account belongs to. *(maxLength 256)* |
| `kind` | enum: `advertiser`, `serving_node`, `supply_agent`, `model_steward`, `measurement_agent` | yes | Which side of the ledger. `advertiser` pays in; the rest are paid out. |
| `status` | enum: `pending_verification`, `active`, `suspended`, `closed` | yes |  |
| `currency` | [`currency`](currency.md) | yes | Denomination of this account's balance. |
| `verification` | object |  | What has been established about this entity, and therefore what it may do. |
| `balance` | object |  | Running position. Positive means owed to the account holder for a payee, owed by them for an advertiser. |
| `credit` | object |  | Advertiser accounts only. |
| `payout` | object |  | Payee accounts only: where money goes and when. |
| `created_at` | string (date-time) |  |  |
| `updated_at` | string (date-time) |  |  |

---

*Generated from `source/schemas/settlement/account.json`. Do not edit; run `make docs`.*
