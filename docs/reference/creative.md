# Creative

**Name** `dev.uap.demand.creative` · **Version** `2026-09-02` · **Schema** [`demand/creative.json`](https://uap.dev/schemas/demand/creative.json)

The advertisement as structured data. Never markup, never a template, never text destined for a model's context.

> **Rationale.** The single most consequential design decision in UAP. A creative is attacker-controlled text that arrives over the network and is rendered beside a language model. Supplying it as markup or as a prompt fragment would make an ad slot the cheapest prompt-injection vector available, purchased at a CPM.
>
> So there is no `html`, no `adm`, no `script`, and no template member. The surface renders these fields as inert text nodes using its own chrome, and interactive behaviour exists only through the declared `actions`. See SPEC.md §7.2.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `creative_id` | string | yes | *(maxLength 128)* |
| `format` | enum: `sponsored_link`, `sponsored_card`, `sponsored_suggestion`, `product_offer`, `sponsored_action` | yes | Must match the format the placement declared. |
| `content` | object | yes |  |
| `disclosure` | object | yes |  |
| `categories` | array of string |  | Advertiser categories, used against seller block lists and brand suitability. *(maxItems 16)* |
| `review` | object |  | Exchange review state. A surface MUST refuse a creative that is not approved. |
| `content_digest` | [`digest`](digest.md) | yes | Digest over the RFC 8785 canonical form of `content`. |

---

*Generated from `source/schemas/demand/creative.json`. Do not edit; run `make docs`.*
