# Dispute

**Schema** [`settlement/dispute.json`](https://uap.dev/schemas/settlement/dispute.json)

A challenge to billed lines on an invoice, adjudicated by re-verifying the cited receipts rather than by negotiation. Every billable impression under UAP carries a receipt the exchange already verified against what it issued, so a dispute has a determinate answer: either the cited receipts still verify, or they do not. This is the difference from open-web billing disputes, which are settled by whoever has more leverage.

A credit to an advertiser MUST be matched by a clawback from the payees who were paid for the same impressions. An exchange that credits one side without reversing the other is silently absorbing the difference and will not reconcile.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `dispute_id` | string | yes | *(maxLength 64)* |
| `invoice_id` | string | yes | *(maxLength 64)* |
| `account_id` | string | yes | The advertiser account challenging the invoice. *(maxLength 64)* |
| `status` | enum: `open`, `under_review`, `upheld`, `partially_upheld`, `rejected`, `withdrawn`, … (7 values) | yes |  |
| `reason_code` | enum: `not_delivered`, `invalid_traffic`, `measurement_discrepancy`, `duplicate`, `wrong_price`, `brand_safety`, … (7 values) | yes |  |
| `lines` | array of object | yes | The challenged lines. Each MUST cite the receipts it disputes, so adjudication has something to re-verify. *(minItems 1, maxItems 1000)* |
| `evidence` | object |  | Optional supporting material. Adjudication does not depend on it; the receipt set is authoritative. |
| `adjudication` | object |  |  |
| `remedy` | object |  |  |
| `opened_at` | string (date-time) | yes |  |
| `deadline_at` | string (date-time) |  | End of the adjudication window. An exchange that lets this pass resolves the dispute in the advertiser's favour; otherwise ignoring a dispute is a winning strategy. |
| `resolved_at` | string (date-time) |  |  |
| `signature` | [`signature`](signature.md) |  |  |

---

*Generated from `source/schemas/settlement/dispute.json`. Do not edit; run `make docs`.*
