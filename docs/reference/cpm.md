# CPM (micros)

**Schema** [`common/types/cpm.json`](https://uap.dev/schemas/common/types/cpm.json)

Price of one thousand impressions, in micros of the stated currency. Every bid, floor, and clearing price in UAP is denominated in this unit.

> **Rationale.** CALIBRATION. An LLM turn is paid-search-like inventory, not display inventory. Reported clearing for a sponsored link rendered below a chat answer was approximately USD 60 CPM at launch (ChatGPT Ads, February 2026). Implementations SHOULD warn outside the band below; scripts/validate.py enforces it.

```text
  1000000  USD  1.00  remnant, untargeted sponsorship, trust tier 0
 10000000  USD 10.00  long-tail self-hosted supply, coarse or absent signal
 40000000  USD 40.00  targeted post_answer placement
 60000000  USD 60.00  observed launch clearing, major assistant surface
 80000000  USD 80.00  high commercial intent, attested tier 2 supply
```

> A floor set three orders of magnitude low sells premium inventory at remnant prices and validates silently. See docs/documentation/market-context.md §1.

---

*Generated from `source/schemas/common/types/cpm.json`. Do not edit; run `make docs`.*
