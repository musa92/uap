# UAP Service

**Schema** [`service.json`](https://uap.dev/schemas/service.json)

A transport-bound endpoint group exposing one or more capabilities. UAP defines one normative wire protocol (REST/HTTPS + JSON) and two bindings (MCP, A2A).

Serve-time decisioning has a hard latency budget: p99 <= 80 ms for POST /decisions, measured exchange-side. A2A MUST NOT be used for serve-time decisions — the round trip does not fit the budget — and the schema enforces this rather than merely recommending it.

## Definitions

### `transport`

rest — normative; TLS 1.3 REQUIRED, HTTP/2 or HTTP/3 RECOMMENDED. mcp — for agents that are themselves buyer or seller; negotiation-time work. a2a — long-running negotiation only (deal shaping, creative approval).

Values: `rest`, `mcp`, `a2a`

### `base`

### `platform_schema`

### `participant_schema`

### `response_schema`

---

*Generated from `source/schemas/service.json`. Do not edit; run `make docs`.*
