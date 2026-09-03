# Detached Object Signature

**Schema** [`common/types/signature.json`](https://uap.dev/schemas/common/types/signature.json)

A detached signature over a UAP object. The signing input is the RFC 8785 canonical serialization of the object with the `signature` member removed, prefixed by a domain-separation tag.

> **Rationale.** Domain separation binds a signature to one object type. Without it, a signature over a Decision can be replayed as a Bundle whenever the two share a field subset. SPEC.md §4.4 defines the tag set.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `kid` | string | yes | Key identifier, resolvable in the signer's JWKS at the manifest `keys` URL. *(maxLength 128)* |
| `alg` | enum: `EdDSA`, `ES256` | yes | Signature algorithm. EdDSA over Ed25519 is REQUIRED to implement; ES256 is OPTIONAL. |
| `value` | string `/^[A-Za-z0-9_-]+$/` | yes | Unpadded base64url-encoded signature (RFC 4648 §5). *(maxLength 1024)* |
| `created` | string (date-time) |  | Signature creation time. |
| `domain` | string |  | The domain-separation tag prefixed to the signing input. |

---

*Generated from `source/schemas/common/types/signature.json`. Do not edit; run `make docs`.*
