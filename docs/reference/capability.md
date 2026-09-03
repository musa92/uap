# UAP Capability

**Schema** [`capability.json`](https://uap.dev/schemas/capability.json)

Schema for UAP capabilities and extensions. An extension is a capability carrying an `extends` field. Reverse-domain naming is the governance mechanism: `dev.uap.*` is reserved for this specification and anyone may register under a domain they control.

Nothing in SPEC.md §6 (context confinement), §7 (answer integrity) or §9 (earned payment) may be relaxed by an extension. An extension that weakens an invariant is out of scope for the registry — stated here so the answer to 'can we add a mode where the prompt is sent?' is a documented no rather than a negotiation.

## Definitions

### `base`

### `platform_schema`

Full declaration for discovery. Includes spec and schema URLs so an agent can fetch and compose the capability during negotiation.

### `participant_schema`

Declaration in a participant's own manifest. Requires `schema` so counterparties can compose it; may add participant-specific `config`.

### `response_schema`

Minimal reference in an API response. Only name and version are needed to confirm which capabilities were active.

---

*Generated from `source/schemas/capability.json`. Do not edit; run `make docs`.*
