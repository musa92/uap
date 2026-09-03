# Viewability

**Schema** [`common/types/viewability.json`](https://uap.dev/schemas/common/types/viewability.json)

The surface's measurement of whether a human could have seen the placement. Thresholds follow Media Rating Council definitions.

> **Rationale.** MRC thresholds, restated for reference:

```text
  display        >=50% of pixels in view for >=1 continuous second
  video          >=50% of pixels in view for >=2 continuous seconds
  large display  >=242000 px creative: >=30% for >=1 second
```

> Buyers reconcile against accredited measurement. A bespoke viewability definition cannot be priced against a rate card.
>
> Several conformant UAP surfaces have no pixels: a CLI, an API response, an MCP tool result. These measure `delivered_only`, which is weaker evidence and is priced as such under SPEC.md §9.3. The alternative -- permitting a pixel-less surface to assert viewability -- is the cheapest available method of rate-card inflation.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `rendered` | boolean | yes | The placement was composed into output returned to the client. |
| `standard` | enum: `mrc_display`, `mrc_video`, `mrc_large_display`, `audible_playback`, `delivered_only` | yes | The measurement standard `viewable` was evaluated against. |
| `viewable` | boolean |  | True only if the threshold named by `standard` was met. Absent or false when `standard` is `delivered_only`. |
| `method` | enum: `intersection_observer`, `native_layout`, `voice_playback`, `declared`, `none` | yes | How the measurement was obtained. |
| `visible_ms` | integer |  | Continuous milliseconds the placement met the pixel threshold. *(minimum 0, maximum 86400000)* |
| `visible_pct` | integer |  | Peak percentage of the placement's area in view during the measurement window. *(minimum 0, maximum 100)* |
| `user_present` | boolean |  | The surface observed evidence of a human in the session -- focus, input, scroll, or playback control -- within the measurement window. |
| `ivt` | [`ivt`](#definitions) |  | Invalid traffic classification applied before submission. |
| `measurement_agent` | object |  | An independent measurement vendor that corroborated this receipt. |

## Conditional constraints

- **delivered_only cannot assert viewability.** Enforced structurally rather than stated in prose. This is the field buyers price against.
- **A viewable impression must carry its evidence.** An unevidenced viewability claim is a self-report and belongs under method `declared`.

## Definitions

### `ivt`

Invalid traffic classification using the MRC two-category framework.

| Property | Type | Required | Description |
|---|---|---|---|
| `classification` | enum: `valid`, `givt`, `sivt`, `unclassified` | yes | The classification assigned by the filtering party. |
| `filtered_reason` | string |  | Registry key identifying why traffic was filtered. *(maxLength 128)* |
| `filter_version` | string |  | Version of the filtration list or model applied. *(maxLength 64)* |

---

*Generated from `source/schemas/common/types/viewability.json`. Do not edit; run `make docs`.*
