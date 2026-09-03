# Universal Ads Protocol (UAP)

**Version:** `2026-09-02` (draft-01)
**Status:** Draft for public comment
**License:** Apache-2.0 (spec text CC-BY-4.0)

An open protocol that lets anyone serving an open-weights language model sell,
select, render, measure and settle advertising — without exfiltrating the user's
conversation, without corrupting the model's answer, and without trusting the
serving node.

---

## 0. Reading this document

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY, and OPTIONAL are to be interpreted as described in BCP 14
(RFC 2119, RFC 8174).

All wire formats are JSON (RFC 8259). All timestamps are RFC 3339 with a `Z`
offset. All monetary amounts are integers in **micros** of the stated currency
(1 USD = 1,000,000 micros). All identifiers are opaque UTF-8 strings ≤ 256 bytes
unless otherwise constrained.

---

## 1. Motivation

Web advertising was built on two assumptions that no longer hold:

| Web assumption | LLM reality |
|---|---|
| A **page** exists: public, addressable, crawlable, cacheable. The ad server can read it. | The context is a **private conversation**. There is no URL to look up and the text must not leave the machine. |
| The **publisher is a server operator** with a business relationship, a domain, and something to lose. | The publisher may be `llama.cpp` on a laptop. Anyone can run it. Anyone can fake a million impressions in a loop. |
| The ad sits **next to** content the publisher already wrote. | The content is **generated at request time by a model that can be steered**. An ad that pays per click creates direct pressure to change the answer. |

Existing agentic protocols solve adjacent problems. UCP standardises commerce
transactions between an agent and a merchant. AP2 standardises cryptographic
proof of user consent to pay. AdCP standardises how buyer and seller *agents*
negotiate media. None of them answer: *how does a sponsored unit get selected
and paid for, at inference time, on a serving node nobody trusts, without the
prompt leaving the box?*

UAP answers exactly that, and reuses the rest.

### 1.1 The three invariants

Everything in this specification exists to hold three lines. An implementation
that violates any of them is not UAP-conformant regardless of what else it does.

> **I1 — Context Confinement.** Raw prompt text, raw completion text, and any
> stable cross-session user identifier MUST NOT leave the serving node. Only
> bounded, enumerable, non-invertible signals may be transmitted (§6).

---

> **I2 — Answer Integrity.** The presence, identity, or price of an ad MUST NOT
> change the substance of the model's answer. Ad content MUST NOT enter the
> model's context as instructions. Bids MUST NOT influence decoding (§7).

---

> **I3 — Earned Payment.** A serving node is untrusted by default. Payment for an
> event is a function of what the *surface* attested and what the *settlement
> layer* could verify — never of what the node merely claimed (§9).

### 1.2 Non-goals

- UAP does not define an identity graph, a cookie, or a cross-site user profile.
- UAP does not define ad creative rendering for non-conversational surfaces.
- UAP does not replace OpenRTB for display/CTV. It defines an LLM-native supply
  type and provides an OpenRTB 2.6 mapping for demand reuse (Appendix C).
- UAP does not adjudicate whether a given deployment *should* show ads. It makes
  the ones that do legible, auditable, and safe.

---

## 2. Roles

```text
                       ┌──────────────────────────────────────┐
                       │            DEMAND SIDE               │
   Advertiser ────────▶│  Demand Agent (DSP)                  │
   /.well-known/       │  POST /uap/v1/bid                    │
   uap-brand           └───────────────┬──────────────────────┘
                                       │
                       ┌───────────────▼──────────────────────┐
                       │  Exchange (UAX)                      │
                       │  auction · bundles · receipts ·      │
                       │  settlement · policy                 │
                       └───────────────┬──────────────────────┘
                            hosted ▲   │   ▼ bundle sync
                                    │   │
                       ┌────────────┴───▼──────────────────────┐
                       │            SUPPLY SIDE                │
                       │  Supply Agent (optional aggregator)   │
                       │  Serving Node   (vLLM / Ollama / …)   │
                       │  Surface        (renders to a human)  │
                       └───────────────────────────────────────┘
                                       │
                              Model Steward (revenue share)
```

| Role | `role` value | Responsibility |
|---|---|---|
| **Serving Node** | `serving_node` | Runs the open-weights model. Derives the ContextSignal. Runs local auctions in Profile L. Never sees raw creative money flow. |
| **Surface** | `surface` | The component that renders to a human and can observe whether a placement was actually seen. Emits signed `ImpressionReceipt`s. MAY be the same process as the serving node; MUST be distinct in trust tier ≥ 1. |
| **Supply Agent** | `supply_agent` | Optional aggregator holding the commercial account for many nodes. Analogous to an SSP or an AdSense publisher account. |
| **Exchange** | `exchange` | Runs the auction, distributes Campaign Bundles, ingests receipts, verifies, settles. |
| **Demand Agent** | `demand_agent` | Bids on behalf of advertisers. Analogous to a DSP. |
| **Advertiser** | `advertiser` | Owns the brand, the budget, and the creative. Publishes `/.well-known/uap-brand`. |
| **Model Steward** | `model_steward` | The entity credited for the open-weights model in use. Receives a declared share of revenue (§10.3). This is how UAP funds open models. |
| **Measurement Agent** | `measurement_agent` | Optional independent verifier of receipts and aggregate reports. |

A single deployment MAY implement several roles. Every UAP message carries the
acting role in the `UAP-Agent` header (§4.3).

---

## 3. Conformance profiles

An implementation declares one or more profiles in its manifest. Profiles
compose; `UAP-CORE` is REQUIRED by all others.

| Profile | ID | Requires |
|---|---|---|
| **Core** | `uap.core` | Objects (§5), discovery (§4), signing (§4.3), integrity boundary (§7), disclosure (§7.4), error model (§12). |
| **Local Decisioning** | `uap.decision.local` | Bundle sync (§8.2), local auction (§8.4), auction trace in receipts. **Context never leaves the node.** |
| **Hosted Decisioning** | `uap.decision.hosted` | `POST /decisions` (§8.1), ContextSignal egress under §6 constraints. |
| **Hybrid Decisioning** | `uap.decision.hybrid` | Candidate fetch by coarse signal, final selection local (§8.3). |
| **Measurement** | `uap.measure` | Signed receipts (§9), event reporting, private aggregation. |
| **Attested Supply** | `uap.attest` | Remote attestation of the serving binary and/or surface (§9.3), unlocking trust tier 2. |
| **Settlement** | `uap.settle` | Revenue splits, AP2 settlement mandates, payout (§10). |
| **Commerce Handoff** | `uap.commerce` | Bridging a placement into a UCP checkout session (§11). |

The minimum useful deployment for a self-hosted open-source server is
`uap.core` + `uap.decision.local` + `uap.measure`. It requires **no context
egress at all**.

---

## 4. Discovery, versioning, transport

### 4.1 The manifest

Every UAP participant that accepts inbound requests MUST serve a manifest at
`GET /.well-known/uap`, `Content-Type: application/json`, cacheable, unauthenticated.

```json
{
  "uap_version": "2026-09-02",
  "entity": {
    "id": "uax.example.com",
    "role": ["exchange"],
    "legal_name": "Example Exchange, Inc.",
    "jurisdiction": "US-DE",
    "contact": "protocol@example.com"
  },
  "profiles": ["uap.core", "uap.decision.local", "uap.decision.hosted",
               "uap.measure", "uap.attest", "uap.settle"],
  "services": [
    {
      "name": "dev.uap.ads",
      "version": "2026-09-02",
      "base_url": "https://uax.example.com/uap/v1",
      "openapi": "https://uax.example.com/uap/v1/openapi.json",
      "capabilities": [
        { "name": "dev.uap.ads.decision", "version": "2026-09-02" },
        { "name": "dev.uap.ads.bundle",   "version": "2026-09-02" },
        { "name": "dev.uap.ads.receipt",  "version": "2026-09-02" },
        { "name": "dev.uap.ads.settlement","version": "2026-09-02" },
        { "name": "dev.uap.ads.deal", "version": "2026-09-02",
          "extends": "dev.uap.ads.decision" }
      ]
    }
  ],
  "taxonomies": [
    { "name": "uap.intent", "version": "1.0",
      "url": "https://uap.dev/taxonomy/intent-1.0.json" }
  ],
  "auction": {
    "mechanisms": ["uap.auction.second_price", "uap.auction.first_price"],
    "currencies": ["USD", "EUR"],
    "default_floor_cpm_micros": 10000000
  },
  "privacy": {
    "max_context_signal_class": "coarse",
    "k_anonymity_floor": 500,
    "retention_days": 30
  },
  "keys": "https://uax.example.com/.well-known/jwks.json",
  "policy": "https://uax.example.com/uap/policy",
  "extensions": []
}
```

- `services[].capabilities[].extends` declares that a capability augments another,
  exactly as in UCP. Agents MUST ignore capabilities they do not understand.
- Capability names are reverse-DNS. `dev.uap.*` is reserved for this
  specification. Vendors MUST namespace extensions under a domain they control
  (`com.acme.ads.brandlift`).
- `version` is a **date string**, `YYYY-MM-DD`. There are no semantic version
  numbers. A newer date MUST be backward-compatible for at least 12 months or
  carry a distinct capability name.

### 4.2 Transports

UAP defines one normative wire protocol and two bindings:

- **REST/HTTPS + JSON** — normative. TLS 1.3 REQUIRED. HTTP/2 or HTTP/3 RECOMMENDED.
- **MCP binding** (`bindings/mcp.md`) — for AI agents that are themselves the
  buyer or the seller. Each capability maps to a tool.
- **A2A binding** — for negotiation-time, long-running tasks (deal shaping,
  creative approval). Serve-time decisions MUST NOT use A2A; the latency budget
  forbids it.

Serve-time decisioning has a hard budget: **p99 ≤ 80 ms** for `POST /decisions`,
measured exchange-side. Exchanges SHOULD publish their observed p99.

### 4.3 Request signing and identity

Every non-public UAP request MUST carry:

| Header | Meaning |
|---|---|
| `UAP-Agent` | `<entity-id>; role=<role>; profile=<profile,…>; v=<uap_version>` |
| `UAP-Request-Id` | UUIDv7, unique per request, echoed in the response |
| `Idempotency-Key` | REQUIRED on all non-idempotent methods; 24 h replay window |
| `Signature-Input`, `Signature` | HTTP Message Signatures (RFC 9421) |

Signatures MUST cover, at minimum, the derived components `@method`,
`@target-uri`, and the headers `content-digest`, `uap-agent`, `uap-request-id`,
and `created`. `Content-Digest` (RFC 9530, SHA-256) is REQUIRED on requests with
a body. Keys are published as a JWKS at the manifest's `keys` URL; `Ed25519` is
REQUIRED to implement, `ES256` OPTIONAL. Key rotation is by adding a new `kid`;
verifiers MUST accept a signature from any key present in the JWKS at the
signature's `created` time, refetching at most once per 60 s.

Commercial identity (which account gets paid) is separate from cryptographic
identity and is established with OAuth 2.0 client credentials against the
exchange's `/.well-known/oauth-authorization-server`. A key may be enrolled to an
account; an unenrolled key is trust tier 0 (§9.3).

---

## 5. Core objects

### 5.1 `Placement` — the slot

The LLM analogue of an ad slot. Described by the *surface*, not by pixels.

```json
{
  "placement_id": "pl_post_answer_card",
  "surface": {
    "type": "chat",
    "modality": ["text", "image"],
    "renderer": "markdown",
    "client": "web",
    "attested": true
  },
  "position": "post_answer",
  "format": "sponsored_card",
  "constraints": {
    "max_chars": 280,
    "max_assets": 1,
    "max_actions": 2,
    "allows_link": true,
    "allows_tool_offer": false
  },
  "disclosure": {
    "required": true,
    "label": "Sponsored",
    "placement": "leading"
  },
  "floor_cpm_micros": 20000000,
  "max_ads": 1
}
```

**`surface.type`** — `chat` · `agent_tool_result` · `voice` · `ide` · `search_answer` · `embedded_widget`
**`position`** — `post_answer` (REQUIRED to implement) · `sidebar` · `followup_suggestion` · `inline_citation` · `pre_answer`
**`format`** — `sponsored_link` · `sponsored_card` · `sponsored_suggestion` · `product_offer` · `sponsored_action`

`position: "inline"` — an ad interleaved into the body of the answer — is
**not defined by this specification and MUST NOT be used**. It cannot satisfy
I2 (§7). Implementations wanting in-body commercial content MUST use
`post_answer` with an explicit visual and structural break.

### 5.2 `ContextSignal` — what the buyer is allowed to know

See §6 for the derivation rules and the hard prohibitions. Structurally:

```json
{
  "signal_version": "uap.intent/1.0",
  "signal_class": "coarse",
  "intents": [
    { "id": "travel.accommodation.hotel", "confidence": 0.81 },
    { "id": "travel.destination.japan",   "confidence": 0.63 }
  ],
  "commercial_intent": 0.74,
  "turn": { "index_bucket": "2-5", "is_followup": true },
  "locale": "en-US",
  "geo": { "granularity": "country", "value": "US" },
  "surface_hint": "chat",
  "safety": { "sensitive_category": false, "brand_risk": "low" },
  "embedding_bucket": null,
  "k_cohort_size_estimate": 12400
}
```

### 5.3 `AdRequest`

```json
{
  "request_id": "01J9…",
  "uap_version": "2026-09-02",
  "supply": {
    "entity_id": "node.self-hosted.example",
    "supply_agent_id": "ssp.example.com",
    "trust_tier": 1,
    "model": {
      "id": "hf:meta-llama/Llama-4-70B-Instruct",
      "steward_id": "steward.example.org",
      "weights_digest": "sha256:9f2c…"
    }
  },
  "placements": [ /* Placement[] */ ],
  "context": { /* ContextSignal */ },
  "auction": {
    "mechanism": "uap.auction.second_price",
    "currency": "USD",
    "timeout_ms": 80,
    "deals": ["deal_abc123"]
  },
  "policy": {
    "blocked_advertisers": ["brand.competitor.example"],
    "blocked_categories": ["gambling", "alcohol"],
    "allowed_formats": ["sponsored_card", "sponsored_link"]
  },
  "test": false
}
```

### 5.4 `Bid` / `BidResponse`

```json
{
  "request_id": "01J9…",
  "bids": [
    {
      "bid_id": "b_1",
      "placement_id": "pl_post_answer_card",
      "pricing": { "model": "cpm", "bid_cpm_micros": 62000000, "currency": "USD" },
      "creative_id": "cr_884",
      "advertiser": {
        "id": "brand.acme.example",
        "brand_url": "https://acme.example/.well-known/uap-brand",
        "display_name": "Acme Travel"
      },
      "categories": ["travel.accommodation"],
      "deal_id": null,
      "expires_at": "2026-09-02T14:31:00Z",
      "attribution": { "click_id_required": true, "conversion_window_hours": 168 }
    }
  ]
}
```

`pricing.model` is one of `cpm` · `cpc` · `cpa`. The exchange normalises to eCPM
using its published conversion model before ranking. Trust tier 0 supply
(§9.3) MUST NOT be sold on `cpm`.

### 5.5 `Creative`

Creatives are **structured data, never markup and never instructions.**

```json
{
  "creative_id": "cr_884",
  "format": "sponsored_card",
  "content": {
    "headline": "Kyoto ryokan, free cancellation",
    "body": "Traditional inns from $180/night, cancel up to 24h before.",
    "brand_name": "Acme Travel",
    "assets": [
      { "role": "logo", "url": "https://cdn.acme.example/logo.png",
        "digest": "sha256:ab…", "width": 128, "height": 128 }
    ],
    "actions": [
      { "type": "link", "label": "See rooms",
        "url": "https://acme.example/kyoto?uap_click={CLICK_ID}" }
    ]
  },
  "disclosure": { "label": "Sponsored", "advertiser_name": "Acme Travel" },
  "review": {
    "status": "approved",
    "reviewer": "uax.example.com",
    "policy_version": "2026-08-01"
  },
  "content_digest": "sha256:5b7e…"
}
```

A serving node MUST reject a creative whose `content_digest` does not match, and
MUST render `content` fields as **text nodes**, never as markdown, HTML, or model
input. See §7.2.

### 5.6 `Decision`

The exchange's answer. Signed.

```json
{
  "decision_id": "dc_01J9…",
  "request_id": "01J9…",
  "issued_at": "2026-09-02T14:30:12Z",
  "expires_at": "2026-09-02T14:35:12Z",
  "nonce": "n_7f3c9a…",
  "placements": [
    {
      "placement_id": "pl_post_answer_card",
      "creative": { /* Creative */ },
      "clearing": { "price_cpm_micros": 41000001, "currency": "USD",
                    "mechanism": "uap.auction.second_price" },
      "billing_ref": "br_5521",
      "click_id": "ck_a91f…",
      "receipt_key_id": "rk_2026w36"
    }
  ],
  "signature": { "kid": "uax-ed25519-2026-08", "alg": "EdDSA", "value": "…" }
}
```

`nonce` is single-use and binds the decision to exactly one impression.

### 5.7 `ImpressionReceipt`

Emitted by the **surface**, not the node. This is the billable artefact.

```json
{
  "receipt_id": "rc_01J9…",
  "decision_id": "dc_01J9…",
  "nonce": "n_7f3c9a…",
  "placement_id": "pl_post_answer_card",
  "creative_digest": "sha256:5b7e…",
  "rendered_at": "2026-09-02T14:30:13Z",
  "viewability": {
    "rendered": true,
    "visible_ms": 3400,
    "method": "intersection_observer",
    "user_present": true
  },
  "integrity": {
    "organic_answer_digest": "sha256:c1d0…",
    "no_decode_influence": true,
    "ad_excluded_from_context": true,
    "disclosure_rendered": true
  },
  "auction_trace": null,
  "trust_tier": 1,
  "attestation": null,
  "signature": { "kid": "surface-ed25519-01", "alg": "EdDSA", "value": "…" }
}
```

### 5.8 `CampaignBundle` (Profile L)

A signed, cacheable package of pre-negotiated line items shipped *to* the node so
the auction can run locally. See §8.2.

---

## 6. Context Confinement (Invariant I1)

### 6.1 Hard prohibitions

A conformant serving node MUST NOT transmit, to any UAP endpoint or any party
acting on behalf of demand:

1. Raw or lightly-transformed prompt text, completion text, system prompt text,
   attachment contents, tool call arguments, or tool results.
2. Any hash, encryption, compression, or n-gram of the above from which text
   could be recovered or confirmed by dictionary attack.
3. Any identifier that is stable for a user across sessions — account id, email,
   IP address, device fingerprint, hardware id, or a hash of any of these.
4. Any embedding of the conversation at a dimensionality or precision permitting
   inversion. Only the bucketed form in §6.4 is permitted, and only under
   §6.5's k-anonymity floor.
5. Free-text fields of any kind sourced from user input. Every field in
   `ContextSignal` is drawn from a **closed enumeration** or is a bounded numeric.

There is no consent flow that unlocks these. A deployment that wants to send
conversation text to an ad network is doing something else, and MUST NOT
describe it as UAP.

### 6.2 Derivation is local

The `ContextSignal` MUST be computed on the serving node from the conversation,
by a classifier the operator controls, and MUST be reduced to the published
taxonomy before it is serialised. Classifier output MUST be clipped to the top
`k ≤ 5` intents and rounded to 2 decimal places of confidence.

### 6.3 Signal classes

| `signal_class` | Contents | Where allowed |
|---|---|---|
| `none` | No signal. Untargeted/sponsorship inventory only. | Everywhere |
| `coarse` | ≤ 3 intent IDs at depth ≤ 2, `commercial_intent` bucketed to 0.1, country-level geo, locale. | Default for hosted decisioning |
| `standard` | ≤ 5 intent IDs at full depth, turn bucket, `safety`. | Hosted decisioning where the exchange publishes `max_context_signal_class: "standard"` and the operator opts in |
| `local_only` | Anything the operator's classifier produces, including full embeddings and raw text. | **Profile L only. Never serialised off-device.** |

Note the shape of this: the richest targeting is available *only* in the profile
where nothing leaves. That is deliberate. Privacy and relevance are not traded
off against each other here; they are traded off against *who runs the auction*.

### 6.4 `embedding_bucket` (OPTIONAL, hosted profiles)

Where an exchange supports it, a node MAY send a locality-sensitive hash bucket
id computed with a **publicly published random projection matrix** (referenced by
`signal_version`), producing an id from a space of at most 2^16 buckets. The
matrix MUST be published so third parties can audit invertibility. A bucket MUST
be suppressed if §6.5 is not satisfied.

### 6.5 k-anonymity floor

Any signal combination transmitted MUST be estimated by the node, or by the
supply agent, to describe at least `k` distinct users in the trailing 7 days,
where `k` is the exchange's published `k_anonymity_floor` (RECOMMENDED ≥ 500).
Below the floor, the node MUST degrade: drop the narrowest intent, then geo, then
fall back to `signal_class: "none"`. Nodes with insufficient traffic to estimate
k MUST use `none` or `coarse` only, or use Profile L.

### 6.6 Reporting

Performance reporting to advertisers MUST be aggregate and MUST satisfy the same
k floor, with counts ≥ 50 per reported cell. Exchanges SHOULD apply differential
privacy noise (ε ≤ 1.0 per campaign-day) to intent-level breakdowns. Per-turn,
per-user, or per-conversation reporting is prohibited.

### 6.7 User control

A surface MUST expose, and a serving node MUST honour:

- an off switch that suppresses all UAP traffic, defaulting per deployment policy;
- a per-turn "why this?" affordance rendering the `ContextSignal` that was used,
  verbatim and human-readable — the user can always see exactly what was sent;
- an opt-out that forces `signal_class: "none"`.

Signals derived from a turn the user marked private, or from a conversation the
deployment classifies as sensitive (`safety.sensitive_category: true`), MUST NOT
produce an `AdRequest` at all. Health, sexual, political, religious,
financial-distress, legal-jeopardy and minors-related contexts are sensitive by
default; the registry in `source/taxonomy/sensitive-1.0.json` is normative and
implementations MUST fail closed on categories they cannot classify.

---

## 7. Answer Integrity (Invariant I2)

This section is the reason to prefer UAP over ad-hoc monetisation. It is also
the section with the most MUSTs, because the failure mode — a model whose
answers bend toward whoever paid — destroys the value of both the model and the
ad.

### 7.1 The Integrity Boundary

```text
   user turn ──▶ ┌──────────────────────────────┐
                 │  MODEL CONTEXT               │  ads may not cross this line
                 │  system + history + user     │  in either direction
                 └──────────────┬───────────────┘
                                │ generate
                     organic_answer (verbatim)
                                │
                                ├──▶ digest ──▶ receipt
                                │
   ContextSignal ──▶ auction ──▶│
                                ▼
                 ┌──────────────────────────────┐
                 │  COMPOSER (non-model)        │
                 │  answer ‖ separator ‖ ad     │
                 └──────────────┬───────────────┘
                                ▼  surface renders
```

Normatively:

1. The organic answer MUST be generated to completion before any creative is
   selected for the same turn, **or** the selection MUST be provably independent
   of the generation (Profile L auctions run on the ContextSignal only).
2. The composer MUST be a deterministic, non-generative function. It MUST NOT be
   a language model. It concatenates; it does not rewrite.
3. `organic_answer_digest` = SHA-256 of the exact bytes shown to the user as the
   answer, excluding the ad block and separator. The surface commits to it in the
   receipt. A settlement-time audit MAY re-request the digest.

### 7.2 Ads are data, not instructions

Creative content is attacker-controlled text arriving over the network. It MUST
be handled with the same posture as any untrusted input:

- Creative fields MUST NOT be appended to, prepended to, or interpolated into any
  prompt, system message, tool description, or retrieval context — not for this
  turn, and not for subsequent turns in the same conversation.
- Creative fields MUST be rendered as **plain text nodes**. Markdown, HTML, and
  template syntax in creative content MUST be escaped, not interpreted. The only
  interactive elements are the declared `actions[]`, rendered by the surface's
  own chrome from structured fields.
- URLs MUST be `https:` and MUST match a `verified_domain` in the advertiser's
  `/.well-known/uap-brand`. Redirect chains MUST be resolved and re-checked by
  the exchange at review time.
- If a conversation is later summarised or re-fed to the model, the ad block MUST
  be stripped first. `ad_excluded_from_context: true` in the receipt attests this.

Rationale: an ad slot is the cheapest prompt-injection vector ever invented. A
system that pastes purchased text into a model's context has sold write access to
its own reasoning for a CPM.

### 7.3 No decode influence

- Bid values, advertiser identity, and campaign state MUST NOT be inputs to
  sampling, logit biasing, beam scoring, speculative decoding, routing between
  models, or system-prompt selection.
- A node MUST NOT run a second generation conditioned on the winning ad, and MUST
  NOT re-rank candidate answers by expected revenue.
- Retrieval and tool selection MUST NOT be ordered by commercial relationship.
  If a deployment surfaces a paid merchant in a *tool result*, it MUST use
  `format: "sponsored_action"` with disclosure, and the organic tool results MUST
  be ranked and returned unchanged alongside it.
- `no_decode_influence: true` in the receipt is an attestation by the operator,
  and at trust tier 2 is covered by the binary attestation (§9.3). Falsely
  asserting it is a settlement-level breach, not a rendering bug.

### 7.4 Disclosure

Every placement MUST be disclosed, in-band, before or at the moment the user can
act on it:

- **Rich surfaces**: a visually distinct block, separated from the answer, with
  the label from `disclosure.label` and the advertiser's `display_name` legible
  without interaction.
- **Plain text / API surfaces**: the block MUST be preceded by a line containing
  exactly `--- Sponsored ---` and the advertiser name, and the response envelope
  MUST carry the header `X-UAP-Sponsored: 1` and a machine-readable
  `uap_placements[]` field so downstream agents can strip or attribute it.
- **Voice**: the disclosure MUST be spoken, before the creative content, and MUST
  NOT be compressed to a tone or sound effect.
- Disclosure MUST NOT be defeated by contrast, size, collapse, timing, or
  scroll position. `disclosure_rendered: true` is a billable precondition:
  an unrendered disclosure makes the impression **non-billable**, not merely
  non-compliant.

### 7.5 The model steward's veto

The entity that publishes an open-weights model MAY publish
`/.well-known/uap-model` declaring `advertising_policy`:

```json
{
  "model_id": "hf:meta-llama/Llama-4-70B-Instruct",
  "weights_digest": "sha256:9f2c…",
  "advertising_policy": {
    "permitted": true,
    "permitted_positions": ["post_answer", "sidebar"],
    "blocked_categories": ["gambling", "political"],
    "revenue_share_bps": 1500,
    "payout": { "handler": "dev.uap.payout.ap2", "account_ref": "acct_…" }
  }
}
```

Exchanges MUST fetch and honour this policy for the `supply.model.id` in the
request, and MUST refuse to clear an auction that violates it. This gives model
authors — for the first time — an enforceable say in how their weights are
monetised, and a share when they are. It is enforced at the exchange, which is
the only party in the chain with money to withhold.

---

## 8. Decisioning

### 8.1 Profile H — Hosted decisioning

`POST {base_url}/decisions` returns a `Decision`

The familiar shape: node sends `AdRequest` with a `ContextSignal`, exchange
fans out to demand agents (`POST {dsp_base}/bid`), runs the auction, returns a
signed `Decision`. Timeout is authoritative: an exchange MUST return within
`auction.timeout_ms` or return `204 No Content`. Nodes MUST treat a timeout as
no-fill and render nothing — never a placeholder that later swaps in.

Constraints: `signal_class` limited to the exchange's published maximum (§6.3);
per-request k-anonymity check; no raw context.

### 8.2 Profile L — Local decisioning

**This is the profile that makes open-source serving work.** Nothing about the
conversation leaves the machine, including from an exchange's point of view.

```text
   nightly / hourly              per turn (0 network calls)
   ────────────────              ──────────────────────────
   GET /bundles ──▶ CampaignBundle ──▶ local match ──▶ local auction ──▶ render
                     (signed, cached)                                      │
                                                                           ▼
   POST /receipts:batch  ◀── batched, delayed, shuffled ── ImpressionReceipt[]
```

`GET {base_url}/bundles?supply_agent_id=…&formats=…&locales=…&max_bytes=…`

```json
{
  "bundle_id": "bn_2026w36_a",
  "issued_at": "2026-09-02T00:00:00Z",
  "expires_at": "2026-09-03T00:00:00Z",
  "taxonomy_version": "uap.intent/1.0",
  "line_items": [
    {
      "line_item_id": "li_991",
      "advertiser": { "id": "brand.acme.example", "display_name": "Acme Travel" },
      "targeting": {
        "all": [
          { "intent_any": ["travel.accommodation.hotel", "travel.destination.japan"] },
          { "commercial_intent_gte": 0.5 },
          { "locale_any": ["en-US", "en-GB"] },
          { "not": { "intent_any": ["travel.insurance"] } }
        ]
      },
      "pricing": { "model": "cpm", "bid_cpm_micros": 62000000 },
      "pacing": { "budget_micros": 5000000000, "daily_cap_impressions": 20000,
                  "node_share_impressions": 40, "smoothing": "even" },
      "frequency_cap": { "per_user_per_day": 2, "per_conversation": 1 },
      "creatives": [ /* Creative[] */ ],
      "categories": ["travel.accommodation"],
      "expires_at": "2026-09-03T00:00:00Z"
    }
  ],
  "floor_cpm_micros": 10000000,
  "signature": { "kid": "uax-ed25519-2026-08", "alg": "EdDSA", "value": "…" }
}
```

Rules:

- The bundle is **signed by the exchange**; the node MUST verify before use and
  MUST refuse expired bundles.
- `targeting` is a closed boolean predicate language (Appendix A) over
  `ContextSignal` fields only. It is total, side-effect free, and MUST be
  evaluable in < 1 ms for 10^3 line items. No regex, no callbacks, no network.
  Implementations SHOULD compile a predicate once when a bundle is loaded rather
  than interpreting it per turn; the reference implementation measures 0.66 ms
  compiled against 2.74 ms interpreted for 10^3 line items, and enforces the
  bound in `tests/test_performance.py`.
- `pacing.node_share_impressions` is the node's *allocated slice* of the campaign,
  assigned by the exchange. The node MUST NOT exceed it. Over-delivery is
  discarded at settlement, so the incentive is aligned.
- Bundles MUST NOT be personalised to a node in a way that would let the exchange
  infer the node's audience from *which* bundle it requested. Bundle variants are
  coarse (locale, format, category) and MUST be served to ≥ `k_anonymity_floor`
  nodes each. A node fetching a bundle SHOULD do so from a stable schedule, not
  on demand, and SHOULD use a fetch proxy or CDN where available.
- Receipt upload MUST be batched, delayed by a randomised interval, and MUST NOT
  correlate with turn timing.

### 8.3 Profile X — Hybrid

Node sends a `coarse` signal, receives a **candidate set** (≥ 10 line items, or
the exchange MUST refuse — a candidate set of 1 is hosted decisioning wearing a
hat), performs final selection locally against the full local-only signal, and
reports only the winner in the receipt. Gives near-hosted fill with a
k-anonymised query.

### 8.4 Auction mechanics

Identical semantics in all three profiles, so that revenue is comparable:

- Bids are normalised to eCPM in the request currency.
  `eCPM = bid_cpc × pCTR × 1000` and `eCPM = bid_cpa × pCVR × 1000` where the
  exchange publishes its `pCTR`/`pCVR` model version in the clearing block.
- Line items failing `policy` (blocked advertiser/category), `Placement.constraints`,
  the model steward's policy (§7.5), or the floor are eliminated **before** ranking.
- Default mechanism `uap.auction.second_price`: the winner pays
  `max(second_highest_eCPM, floor) + 1 micro`. `uap.auction.first_price` MUST be
  declared in the manifest if used.
- Deals (`dev.uap.ads.deal`): a `deal_id` line item may be a guaranteed
  (always wins, fixed price) or preferred (bids in the auction with priority)
  arrangement. Guaranteed deals bypass ranking but not policy or integrity checks.
- **Ties and no-fill**: a placement with no eligible bid MUST render nothing. The
  protocol has no house ads and no default creative.
- In Profile L, the node MUST include a compact `auction_trace` in the receipt:
  the eliminated-and-considered line item ids with their computed eCPMs. This
  makes the local auction **auditable** — the exchange can replay it, because it
  wrote the bundle and it now has the trace and the signal-independent inputs.
  Nodes whose traces do not reproduce are demoted or de-listed.

---

## 9. Earned Payment (Invariant I3)

The serving node is `curl` in a `for` loop until proven otherwise. UAP does not
try to make fraud impossible; it makes fraud **unprofitable by construction**,
by tying what an event pays to what could be verified about it.

### 9.1 Receipt flow

1. The `Decision` carries a single-use `nonce` and a `receipt_key_id`.
2. The **surface** — the thing with a screen and a human in front of it —
   renders, observes, and signs an `ImpressionReceipt` over the nonce, the
   creative digest, the integrity attestations and the viewability measurement.
3. Receipts are batched to `POST {base_url}/receipts:batch`.
4. The exchange verifies: signature chains to an enrolled key; nonce is live and
   unspent; `creative_digest` matches what it issued; `decision_id` was issued to
   *that* supply entity; timing is plausible; the auction trace replays; and the
   receipt is not a duplicate.
5. Only verified receipts enter settlement.

An unspent nonce with no receipt is simply not billed. A nonce presented twice is
a hard signal, not a rounding error.

### 9.2 Engagement and conversion

`POST {base_url}/events` with `click`, `dismiss`, `expand`, `conversion`.
`click_id` from the `Decision` is the join key and MUST be propagated in the
action URL. Conversions are reported by the *advertiser's* endpoint or via an
AP2 payment mandate reference (§10.2), never by the node — the node has no way
to know and every reason to guess high.

### 9.3 Trust tiers

| Tier | Who | Established by | Eligible pricing | Typical clearing |
|---|---|---|---|---|
| **0 — unverified** | Any self-hosted binary, anonymous | Nothing. Valid signature over an unenrolled key. | `cpa` only, post-verified | Long-tail, sponsorship, house |
| **1 — enrolled** | Operator with an account, enrolled key, payout identity, traffic history | OAuth account + KYC + key enrolment | `cpc`, `cpa`, `cpm` at a discount | Most open-source deployments |
| **2 — attested** | Node and/or surface running an attested build | Remote attestation (§9.4) of binary measurement + surface integrity | Full `cpm` | Managed inference providers, shipped apps |

Tier is asserted in the request and **verified** at settlement. Asserting a tier
you cannot substantiate voids the receipts for that period. Tier 0 exists so the
laptop case is *supported and honest*, not so it is paid like a browser.

Additional supply-side controls: per-entity rate limits scaled by verified
history; new-entity ramp (a fixed low impression ceiling for the first 30 days);
receipt-to-decision ratio, CTR, and dwell-time distribution anomaly detection;
and a public transparency ledger of de-listed entity ids.

### 9.4 Attestation (Profile `uap.attest`)

A tier-2 receipt carries an `attestation` object:

```json
{
  "type": "tee",
  "platform": "amd-sev-snp",
  "measurement": "sha384:8e21…",
  "binary": { "name": "vllm-uap", "version": "0.9.2",
              "source_digest": "sha256:44ab…" },
  "evidence": "<base64 quote>",
  "nonce": "n_7f3c9a…"
}
```

Accepted evidence types: `tee` (SEV-SNP, TDX, Nitro), `platform` (Play Integrity,
App Attest), `sw_transparency` (a reproducible build whose digest is in a public
transparency log, signed by the operator). The attestation MUST cover the nonce
so it cannot be replayed, and SHOULD cover the code path that enforces §7.
Attesting the *integrity enforcement*, not merely the impression counter, is what
makes tier 2 meaningful.

---

## 10. Settlement

### 10.1 Split

Every cleared impression carries a `RevenueSplit`, resolved by the exchange:

```json
{
  "billing_ref": "br_5521",
  "gross_micros": 41000,
  "currency": "USD",
  "splits": [
    { "party": "serving_node",  "entity_id": "node.self-hosted.example", "bps": 5500 },
    { "party": "supply_agent",  "entity_id": "ssp.example.com",          "bps": 1000 },
    { "party": "model_steward", "entity_id": "steward.example.org",      "bps": 1500 },
    { "party": "exchange",      "entity_id": "uax.example.com",          "bps": 2000 }
  ],
  "policy_refs": ["https://steward.example.org/.well-known/uap-model"]
}
```

Splits MUST sum to 10000 bps. The `model_steward` share is taken from the model's
own published policy (§7.5) and MUST NOT be reduced by the exchange or the node.

### 10.2 Payment

Settlement uses AP2 mandates so that payout obligations are cryptographically
provable rather than ledger-internal:

- A **Settlement Mandate** is a W3C Verifiable Credential issued per period,
  signed by the exchange, committing to the hash of the period's verified receipt
  set and the resulting split table.
- Advertiser-side, a spend authorisation is an AP2 **Intent Mandate** scoped to
  campaign, budget ceiling, and window; each cleared batch derives a **Payment
  Mandate**. As in AP2, the signature commits to the hash of the specific batch,
  so it cannot be replayed against a different period or amount.
- Payout handlers are pluggable and namespaced, mirroring UCP's handler model:
  `dev.uap.payout.ap2`, `dev.uap.payout.ach`, `com.stripe.connect`,
  `com.wise.payout`. A handler declares supported instruments and minimum payout.

`GET {base_url}/settlements/{period}` returns the mandate, the split table, the
verified/rejected receipt counts, and the rejection reasons — itemised, because
"we rejected 40% of your traffic" without reasons is how the web ad ecosystem
lost publisher trust.

### 10.3 Funding open models

The `model_steward` split is the point. An open-weights model is a public good
with no revenue mechanism; every downstream serving node currently captures the
value. UAP makes the model's own manifest the authority on its monetisation
terms, makes those terms enforceable at the only chokepoint that holds money,
and pays the steward automatically from traffic they never see and cannot audit
directly. A steward that wants none of this sets `permitted: false` and the
protocol refuses to clear.

---

## 11. Commerce handoff (Profile `uap.commerce`)

A `product_offer` placement MAY carry a `commerce` block bridging into UCP:

```json
{
  "commerce": {
    "protocol": "ucp",
    "version": "2026-01-11",
    "merchant_manifest": "https://acme.example/.well-known/ucp",
    "offer": { "product_id": "sku_7781", "price_micros": 180000000, "currency": "USD" },
    "handoff": "checkout_session"
  }
}
```

The surface MAY initiate a UCP checkout session from the placement. Consent for
any payment is governed entirely by AP2 — UAP never carries payment credentials
and never implies purchase authority. A click on an ad is a click on an ad.
Conversion attribution flows back via §9.2 using the UCP session id as the
conversion reference.

---

## 12. Errors

`application/problem+json` (RFC 9457), with a UAP `code`:

```json
{
  "type": "https://uap.dev/errors/signal-policy-violation",
  "title": "ContextSignal exceeds permitted signal class",
  "status": 400,
  "code": "UAP_SIGNAL_CLASS_EXCEEDED",
  "detail": "signal_class 'standard' not permitted; exchange maximum is 'coarse'",
  "request_id": "01J9…",
  "retryable": false
}
```

| Code | Status | Meaning |
|---|---|---|
| `UAP_UNSUPPORTED_VERSION` | 400 | `uap_version` not supported |
| `UAP_SIGNAL_CLASS_EXCEEDED` | 400 | §6.3 violation |
| `UAP_SIGNAL_MALFORMED` | 400 | Free text or off-taxonomy value in ContextSignal |
| `UAP_K_ANON_FLOOR` | 400 | Signal below k floor |
| `UAP_SIGNATURE_INVALID` | 401 | RFC 9421 verification failed |
| `UAP_KEY_NOT_ENROLLED` | 403 | Valid signature, unknown key; treated as tier 0 |
| `UAP_TIER_INSUFFICIENT` | 403 | Requested pricing model not available at this tier |
| `UAP_ROLE_FORBIDDEN` | 403 | The acting role may not perform this operation (e.g. a serving node reporting a conversion) |
| `UAP_MANDATE_REQUIRED` | 402 | A campaign cannot run without an AP2 spend mandate |
| `UAP_REPORT_DIMENSIONS` | 400 | Report requested a dimension outside the closed set, or more than four |
| `UAP_MODEL_POLICY_FORBIDS` | 403 | §7.5 steward veto |
| `UAP_NONCE_SPENT` | 409 | Receipt replay |
| `UAP_BUNDLE_EXPIRED` | 410 | Stale bundle presented |
| `UAP_PACING_EXCEEDED` | 429 | Node exceeded its allocated share |
| `UAP_NO_FILL` | 204 | No eligible bid (not an error; render nothing) |

Clients MUST implement exponential backoff with jitter and MUST NOT retry
non-retryable codes. Serve-time failures MUST fail **closed** (no ad), never open.

---

## 13. Security considerations

**Prompt injection via creative.** The highest-severity risk in the protocol. See
§7.2. Creative is untrusted network input rendered adjacent to a model. Exchanges
MUST scan creative for instruction-shaped content at review time; nodes MUST NOT
rely on that scan.

**Signal inversion.** Repeated low-k queries can fingerprint a user. Mitigated by
§6.5, by bundle coarseness in Profile L, and by requiring exchanges to publish
their k floor so it can be audited.

**Bundle fetch as a side channel.** Which bundle a node requests leaks something.
Mitigated by coarse variants, minimum recipients per variant, scheduled fetches,
and CDN/proxy fetch.

**Receipt fabrication.** The core supply-side attack. Mitigated by exchange-issued
nonces, surface-side signing, trust tiers that make unattested `cpm` unavailable,
auction-trace replay, ramp limits, and settlement-time verification rather than
serve-time trust.

**Auction manipulation by the node** (Profile L). The node runs the auction and
could pick the highest-paying line item regardless of targeting. Mitigated by the
signed bundle plus the replayable `auction_trace`; detection is statistical over a
node's history, and the penalty is at settlement.

**Advertiser-side inference.** A demand agent could bid to probe whether a user
matches a narrow segment. Mitigated by the k floor, by exchanges withholding
per-request feedback below aggregation thresholds, and by DP noise in reporting.

**Malicious exchange.** A hostile exchange could ship a targeting predicate that
functions as an oracle. Mitigated by the closed predicate language (Appendix A),
which cannot express computation over anything but enumerated signal fields, and
by nodes being free to run multiple exchanges and compare.

**Click laundering.** URLs must resolve to verified advertiser domains, resolved
and re-checked at review; redirect chains are part of the reviewed creative.

**Denial of wallet.** Per-entity rate limits, budget ceilings in AP2 intent
mandates, and pacing allocation bound the blast radius.

---

## 14. Governance, registries, extensions

- **Taxonomies** (`uap.intent`, `uap.category`, `uap.sensitive`) are versioned
  JSON documents published at stable URLs. Additions are minor versions; removals
  and re-parentings require a new major version and a 12-month overlap.
- **Formats, positions, mechanisms, payout handlers** are open registries keyed by
  reverse-DNS name. `dev.uap.*` is reserved; anyone may register under a domain
  they control by opening a PR against this repository.
- **Extensions** attach to capabilities via `extends`, exactly as in UCP, and MUST
  be namespaced. Unknown extensions MUST be ignored, not rejected.
- **Nothing in §6, §7, or §9 may be relaxed by an extension.** An extension that
  weakens an invariant is out of scope for the registry. This is stated here so
  that the answer to "can we add a mode where the prompt is sent?" is a
  documented no rather than a negotiation.
- Changes proceed by public PR, a 30-day comment window, and two independent
  interoperating implementations before a capability leaves draft.

---

## Appendix A — Targeting predicate language

A closed, total, side-effect-free boolean language over `ContextSignal`. No
regex, no arithmetic on user data, no external references.

```abnf
predicate := { "all":   predicate[] }
           | { "any":   predicate[] }
           | { "not":   predicate }
           | { "intent_any":            taxonomy_id[] }
           | { "intent_all":            taxonomy_id[] }
           | { "intent_confidence_gte": { "id": taxonomy_id, "value": number } }
           | { "commercial_intent_gte": number }
           | { "locale_any":            bcp47[] }
           | { "geo_any":               region_code[] }
           | { "surface_any":           surface_type[] }
           | { "format_any":            format[] }
           | { "turn_bucket_any":       ("0" | "1" | "2-5" | "6+")[] }
           | { "brand_risk_max":        ("low" | "medium" | "high") }
```

Evaluation: unknown operators evaluate to `false` (fail closed). Depth ≤ 8.
Total terms ≤ 64 per line item. A missing signal field evaluates the containing
term to `false`, never `true`.

## Appendix B — Minimal integration (Profile L)

```python
from uap import Node, ContextClassifier

node = Node(
    entity_id="node.self-hosted.example",
    model_id="hf:meta-llama/Llama-4-70B-Instruct",
    exchanges=["https://uax.example.com"],
    profiles=["uap.core", "uap.decision.local", "uap.measure"],
    signing_key=ed25519_key,
)
node.sync_bundles()                      # background, hourly

def handle_turn(conversation, placements):
    answer = model.generate(conversation)          # ads cannot reach this call
    signal = ContextClassifier.derive(conversation)  # stays on this machine
    decision = node.decide_local(signal, placements)  # 0 network calls
    return compose(answer, decision)                  # deterministic, non-model

def on_rendered(decision, evidence):
    node.emit_receipt(decision, evidence)   # batched, delayed, signed
```

Note what is absent: any call that takes `conversation` and a network address in
the same expression.

## Appendix C — OpenRTB 2.6 mapping

For demand reuse. `AdRequest` maps to `BidRequest` with a `uap` object in `imp.ext`;
`ContextSignal.intents` maps to `site.content.data[]` with a UAP segment taxonomy id;
`Placement` maps to `imp.native` with a UAP-specific `plcmttype`; `Bid.price` in CPM
units of the request currency. The `uap.integrity` object in `imp.ext` is
REQUIRED and carries the placement position and disclosure requirement, so that
legacy DSPs cannot bid into a UAP placement while ignoring §7.

## Appendix D — Comparison

| | OpenRTB | AdCP | UCP / AP2 | **UAP** |
|---|---|---|---|---|
| Unit of supply | Impression on a page | Media package | — | **Placement on a generated turn** |
| Targeting input | URL, cookie, IDFA | Signals, pre-negotiated | — | **Local ContextSignal, closed taxonomy** |
| Trust in publisher | Assumed | Contractual | — | **Assumed absent; tiered and attested** |
| Content integrity | N/A | Brand suitability | N/A | **Normative integrity boundary** |
| Consent proof | Consent strings | — | AP2 mandates | **AP2 mandates, reused for payout** |
| Creator payout | Publisher | Publisher | Merchant | **Node + surface + model steward** |
