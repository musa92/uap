# SupplyChain

**Schema** [`common/types/supply_chain.json`](https://uap.dev/schemas/common/types/supply_chain.json)

The complete set of entities that participated in selling this placement, in the order they were involved. Structurally and semantically compatible with the IAB Tech Lab SupplyChain object (OpenRTB `source.ext.schain`) so that a buyer's existing supply path optimization logic applies unchanged.

Why this exists: buyers filter supply by who they are paying and how many hops separate them from the impression, long before they consider attestation. A UAP AdRequest without a supply chain is unsellable to a holding company. See docs/documentation/market-context.md §4.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `complete` | boolean | yes | True only if every entity between the serving node and this request is represented in `nodes`. An intermediary that cannot vouch for an upstream hop MUST set this false rather than omit the hop. Buyers commonly discard incomplete chains. |
| `nodes` | array of [`node`](#definitions) | yes | Hops in order, from the entity closest to the impression to the entity making this request. The first node is the seller of record for the serving node. *(minItems 1, maxItems 16)* |
| `ver` | const `"1.0"` |  | SupplyChain object version, for parity with the IAB object. |

## Definitions

### `node`

| Property | Type | Required | Description |
|---|---|---|---|
| `asi` | string | yes | Advertising system identifier: the canonical domain of the system this hop was sold through, matching the `$id` of that system's uap-sellers.json. Equivalent to OpenRTB SupplyChain `asi`. *(maxLength 256)* |
| `sid` | string | yes | The seller id, as it appears in that system's uap-sellers.json. Equivalent to SupplyChain `sid`. MUST be stable per seller and MUST NOT encode any user-derived value. *(maxLength 64)* |
| `hp` | enum: `0`, `1` | yes | 1 if this node is involved in the payment flow for the impression, 0 if it only passes the request through. Equivalent to SupplyChain `hp`. |
| `rid` | string |  | The request id issued by this node, for reconciliation across hops. Equivalent to SupplyChain `rid`. *(maxLength 128)* |
| `name` | string |  | Business name of the seller, where not confidential. *(maxLength 256)* |
| `domain` | string |  | Business domain of the seller, where not confidential. *(maxLength 256)* |
| `role` | [`role`](uap.md) |  | The UAP role this hop acted as. |
| `anchor` | [`anchor`](#definitions) | yes | How this hop's right to sell is established. This is the UAP-specific addition to the IAB object, and it is REQUIRED. On the open web every seller has a domain and ads.txt anchors the chain to it. UAP's core supply is a self-hosted binary with no domain, so each hop MUST state which authority vouches for it. |
| `trust_tier` | enum: `0`, `1`, `2` |  | The trust tier this hop asserts (SPEC.md §9.3). Asserted here, verified at settlement. Asserting a tier that cannot be substantiated voids the period's receipts. |
| `signature` | [`signature`](signature.md) |  | OPTIONAL per-hop signature over this node object plus the digest of all preceding nodes, making the chain append-only. A hop that signs cannot later be reordered, removed, or attributed to a different seller by a downstream intermediary. Absent on hops that do not sign; buyers MAY require signed chains. |

### `anchor`

The authority establishing this seller's right to sell the inventory.

| Property | Type | Required | Description |
|---|---|---|---|
| `type` | enum: `domain`, `model_steward`, `enrolment`, `attestation`, `none` | yes | domain — a uap-sellers.json at `asi` lists `sid`; equivalent to the ads.txt/sellers.json guarantee on the open web. model_steward — the right to monetise derives from a /.well-known/uap-model policy that permits it (SPEC.md §7.5). This is the anchor for self-hosted supply, which has no domain of its own. enrolment — an OAuth account with the exchange plus an enrolled signing key; trust tier 1. attestation — a remote attestation over the serving binary and/or surface; trust tier 2. none — anonymous supply. Permitted, and honestly labelled. Tier 0: CPA only, never CPM. |
| `reference` | string (uri) |  | The document establishing the anchor: the uap-sellers.json, the /.well-known/uap-model, or the attestation policy URL. |
| `verified_at` | string (date-time) |  | When the asserting party last resolved and checked the reference. Buyers SHOULD discount anchors verified long ago. |

---

*Generated from `source/schemas/common/types/supply_chain.json`. Do not edit; run `make docs`.*
