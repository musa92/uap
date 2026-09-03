# Report

**Name** `dev.uap.demand.report` · **Version** `2026-09-02` · **Schema** [`demand/report.json`](https://uap.dev/schemas/demand/report.json)

Aggregate delivery and performance for a buyer, under the privacy floors of SPEC.md §6.6: every cell describes at least 50 events and at least the k-anonymity floor of users, with differential-privacy noise on intent-level breakdowns.

> **Rationale.** Per-turn, per-user and per-conversation reporting is prohibited by the specification and has no representation here. The dimension list is closed for the same reason: a free-form group-by is a re-identification query.

## Definitions

### `request`

| Property | Type | Required | Description |
|---|---|---|---|
| `scope` | object | yes |  |
| `period` | object | yes |  |
| `granularity` | enum: `day`, `week`, `month`, `total` |  | *(default "day")* |
| `dimensions` | array of enum: `campaign`, `line_item`, `creative`, `format`, `position`, `intent_depth1`, … (14 values) |  | *(maxItems 4)* |
| `metrics` | array of enum: `impressions`, `viewable_impressions`, `clicks`, `conversions`, `conversion_value_micros`, `spend_micros`, … (12 values) | yes | *(minItems 1)* |

### `response`

| Property | Type | Required | Description |
|---|---|---|---|
| `report_id` | string | yes | *(maxLength 128)* |
| `generated_at` | string (date-time) | yes |  |
| `privacy` | object | yes |  |
| `rows` | array of object | yes |  |

---

*Generated from `source/schemas/demand/report.json`. Do not edit; run `make docs`.*
