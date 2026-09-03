# UAP — MCP binding

For deployments where an AI agent is itself the buyer or the seller. Serve-time
decisioning SHOULD still use the REST binding (§4.2) — the MCP round trip does
not fit the 80 ms p99 budget. This binding covers negotiation-time work and
agent-native supply.

Server name: `uap`. All tools take and return the objects defined in `SPEC.md`.

## Supply-side tools (exposed by an exchange to a serving agent)

| Tool | Maps to | Notes |
|---|---|---|
| `uap_sync_bundles` | `GET /bundles` | Returns a signed `CampaignBundle`. The agent MUST verify the signature before use. |
| `uap_decide` | `POST /decisions` | Hosted profile only. Input MUST validate against `context-signal.schema.json`; a free-text field is a protocol error, not a warning. |
| `uap_report_receipts` | `POST /receipts:batch` | Batched. The calling agent MUST NOT invoke this synchronously with the turn that produced the impression. |
| `uap_report_event` | `POST /events` | `click`, `dismiss`, `expand`. |
| `uap_get_settlement` | `GET /settlements/{period}` | Returns the AP2 settlement mandate and the itemised rejection reasons. |

## Demand-side tools (exposed by an exchange to a buying agent)

| Tool | Maps to |
|---|---|
| `uap_list_inventory` | Aggregate supply forecast by intent node, format, locale, trust tier |
| `uap_create_campaign` | Line items, targeting predicate, budget, AP2 intent mandate reference |
| `uap_submit_creative` | Creative review; returns `review.status` |
| `uap_get_delivery` | Aggregate delivery and performance, k-anonymised and DP-noised per §6.6 |

## Tool-description safety

Two rules that are easy to get wrong and expensive to get wrong:

1. **Tool descriptions and tool results in this binding are part of the agent's
   context.** Creative content therefore MUST NOT appear in any MCP tool result
   that the agent will reason over. `uap_decide` returns a creative to be
   **rendered**, and a conformant client MUST route it to the renderer, not back
   into the model. If your MCP client cannot make that distinction, use the REST
   binding.

2. **`uap_decide` MUST NOT be callable by the model as a tool during generation.**
   Exposing it that way lets the model observe ad availability while composing
   the answer, which violates §7.3 whether or not it changes the output. Call it
   from the orchestration layer, after generation completes.
