# Deal

**Schema** [`common/types/deal.json`](https://uap.dev/schemas/common/types/deal.json)

A pre-negotiated arrangement between a buyer and this supply, identified by `deal_id` and priced outside the open auction.

> **Rationale.** Maps to OpenRTB 2.6 `imp.pmp.deals`. Deals are how brand budget actually buys: a holding company commits spend against guaranteed or preferred access, not against an open auction it cannot forecast. Supply with no deal support is limited to remnant demand.
>
> Guaranteed deals bypass ranking. They do not bypass policy, the model steward's advertising policy, or the integrity requirements of SPEC.md §7.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `deal_id` | string | yes | Identifier agreed between buyer and seller. *(maxLength 128)* |
| `kind` | enum: `guaranteed`, `preferred`, `private_auction` | yes | How this deal participates in selection. |
| `floor_cpm_micros` | [`cpm`](cpm.md) |  | Agreed price or floor for this deal. |
| `currency` | [`currency`](currency.md) |  |  |
| `seats` | array of string |  | Buyer seat identifiers permitted to transact this deal. *(maxItems 64)* |
| `advertiser_domains` | array of string |  | Advertiser domains permitted on this deal. *(maxItems 64)* |
| `expires_at` | string (date-time) |  | End of the deal flight. |

---

*Generated from `source/schemas/common/types/deal.json`. Do not edit; run `make docs`.*
