# Digest

**Schema** [`common/types/digest.json`](https://uap.dev/schemas/common/types/digest.json)

A content digest formatted as `<algorithm>:<lowercase-hex>`. SHA-256 is REQUIRED to implement.

> **Rationale.** A digest over a JSON object is computed on the RFC 8785 (JCS) canonical form. Without a canonicalization rule, two conformant serializers produce different digests for the same object and every signature check fails. See SPEC.md §4.4.

---

*Generated from `source/schemas/common/types/digest.json`. Do not edit; run `make docs`.*
