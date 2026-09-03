# Currency

**Schema** [`common/types/currency.json`](https://uap.dev/schemas/common/types/currency.json)

ISO 4217 alphabetic currency code. An auction clears in exactly one currency, declared on the request and echoed on every downstream object.

> **Rationale.** UAP performs no currency conversion. An exchange operating across currencies runs one auction per currency; a cross-currency comparison would require a rate and a rate timestamp that no object in this specification carries.

---

*Generated from `source/schemas/common/types/currency.json`. Do not edit; run `make docs`.*
