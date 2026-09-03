# UAP Sellers Declaration

**Name** `dev.uap.supply.sellers` · **Version** `2026-09-02` · **Schema** [`supply/sellers.json`](https://uap.dev/schemas/supply/sellers.json)

Served at `GET /.well-known/uap-sellers.json` by every exchange and supply agent that pays anyone. Declares the identity and role of every entity it is authorized to pay for UAP inventory, so that a buyer can resolve each `asi`/`sid` pair in a SupplyChain object to a real, named counterparty.

This is the direct analogue of IAB Tech Lab sellers.json, and is deliberately field-compatible with it. It is unauthenticated, cacheable, and public: publishing it is what makes an exchange's supply auditable by buyers who have no contract with it.

The UAP-specific problem it solves: on the open web, ads.txt anchors a seller to a domain the seller controls. UAP's core supply is a self-hosted binary with no domain and nothing to lose, so `anchor_type` records which authority actually vouches for each seller instead.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `version` | const `"1.0"` | yes | Version of this declaration format, for parity with sellers.json. |
| `uap_version` | [`version`](uap.md) |  | The UAP protocol version this declaration is published against. |
| `contact_email` | string (email) | yes | Address a buyer can use to raise a supply quality or payment dispute. |
| `contact_address` | string |  | Business postal address of the publishing entity. *(maxLength 512)* |
| `identifiers` | array of object |  | Third-party identity assertions about the publishing entity — TAG-ID, DUNS, LEI, or an equivalent. Buyers use these to tie the declaration to a legal entity they can contract with. *(maxItems 16)* |
| `sellers` | array of [`seller`](#definitions) | yes | Every entity this system is authorized to pay. A SupplyChain node whose (asi, sid) does not resolve here is unauthorized supply and buyers SHOULD discard it. *(maxItems 1000000)* |
| `signature` | [`signature`](signature.md) |  | OPTIONAL signature over this declaration. sellers.json on the open web is unsigned and trusted by TLS alone; UAP permits signing so that a declaration can be cached, mirrored by a CDN, or served from a fetch proxy without losing its authority. |

## Definitions

### `seller`

| Property | Type | Required | Description |
|---|---|---|---|
| `seller_id` | string | yes | Opaque, stable identifier for this seller within the publishing system. This is the value that appears as `sid` in a SupplyChain node. MUST NOT be derived from any user-level value, and MUST be unique within this document. *(maxLength 64)* |
| `seller_type` | enum: `PUBLISHER`, `INTERMEDIARY`, `BOTH` | yes | PUBLISHER — this seller directly operates the serving node or surface where the impression occurs. INTERMEDIARY — this seller resells inventory it does not operate. BOTH — both, which buyers treat with more scrutiny. Values match sellers.json exactly. |
| `name` | string |  | Legal or business name. REQUIRED unless `is_confidential` is 1. *(maxLength 256)* |
| `domain` | string |  | Business domain of the seller. Frequently absent in UAP: a self-hosted serving node legitimately has no domain, which is what `anchor_type` exists to handle. *(maxLength 256)* |
| `is_confidential` | enum: `0`, `1` |  | 1 if `name` and `domain` are withheld under a confidentiality agreement. Buyers commonly apply a discount to confidential supply; a system that marks most of its supply confidential should expect to be treated as opaque. *(default 0)* |
| `is_passthrough` | enum: `0`, `1` |  | 1 if this system passes the bid request through without being the seller of record — the entity is upstream and paid by someone else. *(default 0)* |
| `anchor_type` | enum: `domain`, `model_steward`, `enrolment`, `attestation`, `none` | yes | The authority establishing this seller's right to sell, mirroring supply_chain.json#/$defs/anchor. UAP-specific and REQUIRED: it is the field that lets a buyer distinguish an operator with a domain and a contract from an anonymous binary, when neither has a website. |
| `model_ids` | array of string |  | For sellers whose inventory is the output of specific open-weights models, the model identifiers whose /.well-known/uap-model policies govern this supply. Lets a buyer confirm the steward permits the monetisation it is about to fund, and lets a steward audit who is selling against their weights. *(maxItems 64)* |
| `trust_tier` | enum: `0`, `1`, `2` |  | The highest trust tier this seller has substantiated with the publishing system in the trailing 30 days. This is the publishing system's own assessment, not the seller's claim. |
| `enrolled_since` | string (date) |  | When this seller was enrolled. New supply is the highest-risk supply; SPEC.md §9.3 requires a ramp ceiling for the first 30 days, and buyers SHOULD apply their own. |
| `comment` | string |  | *(maxLength 512)* |

---

*Generated from `source/schemas/supply/sellers.json`. Do not edit; run `make docs`.*
