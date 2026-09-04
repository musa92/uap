# Brand Manifest

**Name** `dev.uap.common.brand` · **Version** `2026-09-02` · **Schema** [`common/types/brand.json`](https://uap.dev/schemas/common/types/brand.json)

Served at `GET /.well-known/uap-brand` by every advertiser. Establishes which domains an advertiser may link to and who is accountable for the creative.

> **Rationale.** Referenced by creative review since draft-01 but never defined, which meant the one check that stops click laundering had no schema behind it. An action URL that does not resolve to a domain listed here is rejected at review; redirect chains are followed and re-checked, so a creative cannot be approved against one destination and later serve another.
>
> This is the advertiser-side counterpart to uap-sellers.json. Together they close the loop: a buyer can see who is selling, and a seller can see who is buying.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `advertiser_id` | string | yes | Stable identifier, matching `advertiser.id` on every creative. *(maxLength 256)* |
| `legal_name` | string | yes | *(maxLength 256)* |
| `display_name` | string |  | Name shown to users in the disclosure. May differ from the legal name. *(maxLength 128)* |
| `verified_domains` | array of string | yes | Domains this advertiser may direct clicks to. Subdomains are included. *(minItems 1, maxItems 64)* |
| `contact` | string (email) | yes |  |
| `jurisdiction` | string |  | ISO 3166 code of the entity's registration. *(maxLength 16)* |
| `identifiers` | array of object |  | Third-party identity assertions, so an exchange can tie the brand to a contractable entity. *(maxItems 16)* |
| `categories` | array of string |  | Categories this advertiser operates in. Sellers block on these. *(maxItems 16)* |
| `keys` | string (uri) |  | JWKS URL. Conversion reports are signed with a key from it. |
| `policy_contact` | string (email) |  | Where creative rejections and policy appeals are sent. |

---

*Generated from `source/schemas/common/types/brand.json`. Do not edit; run `make docs`.*
