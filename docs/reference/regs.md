# Regulatory Signals

**Schema** [`common/types/regs.json`](https://uap.dev/schemas/common/types/regs.json)

Consent and regulatory state applying to this request. Absence of a member means the signal was not determined, which is not the same as consent.

> **Rationale.** Maps to OpenRTB 2.6 `regs`. Without these members a request cannot lawfully be transacted in the EU, in US states with comprehensive privacy statutes, or against inventory that may reach children. Buyers drop requests with no regulatory block rather than assume permission, so an exchange that omits this object sells nothing in those markets.
>
> UAP carries the consent string but never the identifiers it governs. I1 forbids the cross-session identifier that most consent frameworks exist to regulate, so in practice these members constrain what a buyer may do post-click and in its own systems.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `gpp` | string |  | IAB Global Privacy Platform consent string. *(maxLength 4096)* |
| `gpp_sid` | array of integer |  | GPP section identifiers present in `gpp`. *(maxItems 32)* |
| `gdpr` | enum: `0`, `1` |  | 1 when the request is subject to GDPR. |
| `coppa` | enum: `0`, `1` |  | 1 when the request is subject to COPPA. |
| `us_privacy` | string |  | Legacy CCPA string. Deprecated in favour of `gpp`. *(maxLength 64)* |
| `dsa` | object |  | EU Digital Services Act transparency requirements for this request. |

---

*Generated from `source/schemas/common/types/regs.json`. Do not edit; run `make docs`.*
