# AggregationSpec

**Schema** [`supply/aggregation_spec.json`](https://uap.dev/schemas/supply/aggregation_spec.json)

A closed, declarative description of what a node will compute over its own turns and what will leave it. Carried in the CampaignBundle so the node can read it, check it, and refuse before computing anything.

This is the safety property of Profile `uap.federated`. Federated systems normally ship code from the server to run against user data, which is worse than shipping the data, because at least data is inspectable. Here the node is given a declaration with a fixed vocabulary and a fixed cardinality, evaluable without callbacks, regex or network, in the same way targeting predicates are (Appendix A).

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `spec_version` | const `"uap.agg/1.0"` | yes |  |
| `dimensions` | array of object | yes | Fields to bin on. Every dimension MUST fix its cardinality in advance: an open dimension lets one rare value become its own cell, which identifies whoever produced it. *(minItems 1, maxItems 4)* |
| `metrics` | array of enum: `impressions`, `clicks`, `conversions`, `viewable` | yes | *(minItems 1, maxItems 8)* |
| `contribution_bound` | integer | yes | Maximum events one user may add. This is the L1 sensitivity, and it is what makes `epsilon` mean anything: without a per-user bound the noise is decoration. *(minimum 1, maximum 16)* |
| `epsilon` | number | yes | Privacy parameter for the released aggregate. Enforced by the node against its own per-campaign-day budget, because a budget the exchange tracks is not a budget. *(maximum 10)* |
| `k_floor` | integer | yes | Cells below this are suppressed at publication. Noise does not hide a cell only one node could have contributed to. *(minimum 50)* |
| `min_participants` | integer | yes | Node count the noise is calibrated to. Nodes MUST calibrate to this floor rather than a live count they cannot verify; if fewer nodes report, the sum is under-noised. *(minimum 2)* |
| `aggregators` | array of string (uri) |  | Independent endpoints receiving additive secret shares. No single one can read a node's vector. They MUST NOT be operated by the same party; the guarantee is non-collusion. *(minItems 2, maxItems 4)* |
| `gradient` | object |  | Optional federated ranking update (SPEC.md 6.9). Features are the aggregation cells plus a bias, so an update cannot observe any field the dimensions did not already declare. |

---

*Generated from `source/schemas/supply/aggregation_spec.json`. Do not edit; run `make docs`.*
