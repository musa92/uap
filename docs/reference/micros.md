# Micros

**Schema** [`common/types/micros.json`](https://uap.dev/schemas/common/types/micros.json)

A monetary amount as an integer count of micros of the stated currency, where one unit equals 1000000 micros. Each amount is paired with a sibling `currency` field or inherits one from the enclosing auction block.

> **Rationale.** Integer representation is required. Binary floating point cannot represent decimal fractions exactly, and accumulated error in a settlement ledger is unrecoverable. Micros give six decimal places of headroom against a CPM divided by 1000 to reach a per-impression price.

---

*Generated from `source/schemas/common/types/micros.json`. Do not edit; run `make docs`.*
