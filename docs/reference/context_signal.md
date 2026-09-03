# ContextSignal

**Name** `dev.uap.supply.context_signal` · **Version** `2026-09-02` · **Schema** [`supply/context_signal.json`](https://uap.dev/schemas/supply/context_signal.json)

The only conversation-derived data permitted to leave a serving node. Every member is a closed enumeration or a bounded numeric.

> **Rationale.** Defined by SPEC.md §6. There is deliberately no free-text member anywhere in this schema, and scripts/validate.py asserts that mechanically: an unbounded string here is an I1 breach, not a style question.
>
> `local_only` is absent from the signal_class enum by design. A local-only signal is the richer form the node's own classifier produces and is never serialized off-device, so it has no wire representation. An instance carrying signal_class 'local_only' is by construction not a wire object and MUST NOT validate against this schema.

## Properties

| Property | Type | Required | Description |
|---|---|---|---|
| `signal_version` | string `/^uap\.intent/[0-9]+\.[0-9]+$/` | yes |  |
| `signal_class` | enum: `none`, `coarse`, `standard` | yes | The egress class of this signal. |
| `intents` | array of object |  | *(maxItems 5)* |
| `commercial_intent` | number |  | *(minimum 0, maximum 1, multipleOf 0.01)* |
| `turn` | object |  |  |
| `locale` | string `/^[a-z]{2}(-[A-Z]{2})?$/` |  |  |
| `geo` | object |  |  |
| `surface_hint` | enum: `chat`, `agent_tool_result`, `voice`, `ide`, `search_answer`, `embedded_widget` |  |  |
| `safety` | object |  |  |
| `embedding_bucket` | integer \| null |  | Locality-sensitive hash bucket over a publicly published projection matrix. *(minimum 0, maximum 65535)* |
| `k_cohort_size_estimate` | integer |  | *(minimum 0)* |

---

*Generated from `source/schemas/supply/context_signal.json`. Do not edit; run `make docs`.*
