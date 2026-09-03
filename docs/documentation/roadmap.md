# Roadmap

Draft-01 covers the serve-time path end to end. What follows is the buy side
and the operational surface, in the order a first exchange would need them.
Each is a tracked milestone with an issue, not a gap to be discovered later.

## Draft-02 — a buyer can transact

| Milestone | Status |
|---|---|
| Forecast endpoint | Done — ranges, k-floor suppression |
| Campaign and creative review APIs | Done — review checks verified domains and instruction-shaped text |
| Conversions API | Done — advertiser or payment mandate only, never the node |
| Reporting API | Done — closed dimensions, cell minimums, DP noise on intent |
| Published schemas | Done — served at their `$id` paths by the docs workflow |
| RFC 9421 transport signing | Open |

## Draft-03 — money moves correctly

| Milestone | Unblocks |
|---|---|
| Billing lifecycle | Invoicing, disputes, make-goods, invalid-traffic chargebacks |
| Tax handling | VAT/GST on payouts; 1099 and DAC7 reporting for individual operators |
| Multi-currency settlement | Rate locking so cross-currency payouts are provable |
| Reference classifier | Replaces the fail-closed stub so a deployment can serve |

## Draft-04 — regulated markets

| Milestone | Unblocks |
|---|---|
| GPP/TCF enforcement | Consent strings are carried today; nothing yet acts on them |
| GARM suitability enforcement | The taxonomy is in the schema; the auction does not filter on it |
| DSA Article 39 repository | A public ad repository, required for very large platforms in the EU |

## Open design problems

Documented rather than hidden. The remaining one needs a design, not a patch.

**Frequency capping across nodes.** `per_user_per_day` requires an identifier
stable across sessions, which invariant I1 forbids. Capping works within one
node today; network-wide capping needs an on-device approach in the shape of
Protected Audience.

**Local pacing stranding revenue** is resolved in draft-02: allocations are
signed per node, sum to at most the remaining budget, and a node inside its
slice is always paid.

## Leaving draft

Per §14: a public PR, a 30-day comment window, and two independent
interoperating implementations. There is currently one.
