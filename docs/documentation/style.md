# Schema and specification style

Normative for all files under `source/`. Enforced by `scripts/validate.py`.

## 1. `description` and `$comment` have different jobs

`description` is consumed by code generators, IDE tooltips, and OpenAPI renderers.
Prose placed there is compiled into every generated client in every language.
`$comment` is defined by JSON Schema as an annotation for schema maintainers and
is discarded by generators.

| Field | Contains | Limit |
|---|---|---|
| `description` | The field's meaning and constraints. | 3 sentences. |
| `$comment` | Rationale, provenance, citation, market evidence. | No limit. |

A `description` states what the field is. It does not argue for the design.

## 2. Register

Third person. Present tense. Declarative.

- No first or second person. Not "you", "we", "our", "your".
- No rhetorical questions, similes, or superlatives.
- No evaluative adjectives: "powerful", "robust", "elegant", "simple", "cheapest",
  "best". State the property, not an opinion of it.
- One idea per sentence. Prefer a table or an enumeration to a paragraph.
- RFC 2119 keywords carry their RFC 2119 meaning and appear in upper case. They
  are not used for emphasis.

## 3. Citation

Cite a section, never restate it. `SPEC.md §6.1` is a reference. Reproducing the
text of §6.1 in a schema creates two sources of truth that drift.

External facts carry their source in `$comment`, with enough detail to re-verify:
standard, body, and date.

## 4. Enumerations

Every enum member is documented. An undocumented member is an ambiguity that each
implementer resolves differently.

Document members as a table in `$comment`, keyed by value, not as a prose list
inside `description`.

## 5. Naming

`snake_case` for properties. `lower_snake_case` for enum values. Reverse-DNS for
registry keys. Monetary fields carry their unit as a suffix: `_micros`, `_bps`.
Time fields carry theirs: `_ms`, `_at` for RFC 3339 instants, `_days`.

## 6. Prohibited constructions

The validator rejects these because each one has produced a defect in a shipped
protocol:

| Construction | Failure mode |
|---|---|
| Unbounded `type: "string"` in a signal schema | Free-text egress. Violates I1. |
| `additionalProperties` unset on a closed object | Undeclared fields survive validation. |
| A `description` over 3 sentences | Rationale reaches generated code. |
| First or second person in `source/` | Register drift across contributors. |
