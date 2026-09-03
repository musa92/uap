# UAP Metadata

**Schema** [`uap.json`](https://uap.dev/schemas/uap.json)

Protocol metadata for discovery manifests and responses. Mirrors the UCP entity/registry pattern so that a participant implementing both protocols shares one discovery code path.

## Definitions

### `version`

Version identifier in YYYY-MM-DD format. UAP has no semantic version numbers; a newer date MUST be backward compatible for 12 months or carry a distinct capability name.

Type: `string`, pattern `^\d{4}-\d{2}-\d{2}$`

### `version_constraint`

Version range requirement with minimum and optional maximum.

| Property | Type | Required | Description |
|---|---|---|---|
| `min` | [`version`](#definitions) | yes | Minimum required version (inclusive). |
| `max` | [`version`](#definitions) |  | Maximum compatible version (inclusive). When absent, no upper bound. |

### `role`

The acting role for a message. A deployment MAY implement several roles; every request declares the one it is acting as. See SPEC.md §2.

Values: `serving_node`, `surface`, `supply_agent`, `exchange`, `demand_agent`, `advertiser`, `model_steward`, `measurement_agent`

### `profile`

Conformance profile. uap.core is REQUIRED by all others. See SPEC.md §3.

Values: `uap.core`, `uap.decision.local`, `uap.decision.hosted`, `uap.decision.hybrid`, `uap.measure`, `uap.attest`, `uap.settle`, `uap.commerce`, `uap.supplychain`

### `entity`

Shared foundation for all UAP entities (capabilities, services, handlers).

| Property | Type | Required | Description |
|---|---|---|---|
| `version` | [`version`](#definitions) | yes |  |
| `spec` | string (uri) |  | URL to the human-readable specification section. |
| `schema` | string (uri) |  | URL to the JSON Schema defining this entity's payloads. |
| `id` | string |  | Instance identifier, to disambiguate multiple configurations of the same entity. *(maxLength 256)* |
| `config` | object |  | Entity-specific configuration. Structure defined by the entity's own schema. |

### `members`

Members of the reserved `uap` protocol object. Open for forward compatibility: consumers MUST ignore unrecognized members, and every defined member MUST be safe to ignore — a participant that does not process it loses that member's benefit, never correctness.

| Property | Type | Required | Description |
|---|---|---|---|
| `map_order` | object |  | Preferred key order for map-valued fields in the annotated scope. Advisory only. |
| `integrity` | [`integrity_assertion`](integrity_assertion.md) |  | Answer-integrity assertions travelling with an object. Never safe to ignore at settlement, but safe to ignore for rendering. |

### `capabilities_registry`

Capabilities keyed by reverse-domain name. Each value is an array so that multiple versions or configurations may be declared simultaneously.

Type: `object`

### `services_registry`

Services keyed by reverse-domain name.

Type: `object`

### `payout_handlers_registry`

Payout handlers keyed by reverse-domain name, e.g. dev.uap.payout.ap2, com.stripe.connect. Mirrors UCP's payment_handlers registry.

Type: `object`

### `base`

Base UAP metadata carried in the root `uap` envelope of a manifest or response.

| Property | Type | Required | Description |
|---|---|---|---|
| `version` | [`version`](#definitions) | yes |  |
| `status` | enum: `success`, `error` |  | *(default "success")* |
| `capabilities` | [`capabilities_registry`](#definitions) |  |  |
| `services` | [`services_registry`](#definitions) |  |  |
| `payout_handlers` | [`payout_handlers_registry`](#definitions) |  |  |

---

*Generated from `source/schemas/uap.json`. Do not edit; run `make docs`.*
