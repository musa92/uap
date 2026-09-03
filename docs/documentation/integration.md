# Integration guide

Who does what, and what each party actually builds.

There are three roles that matter operationally. An **inference provider** sells
placements on turns it generates. A **demand source** buys them. An **exchange**
sits between, runs the auction, and holds the money. A single company may be two
of these, but the trust boundaries stay where they are regardless.

## Part 1. Inference providers

You run vLLM, SGLang, Ollama, llama.cpp, or your own stack, and you want the
turns you serve to earn.

### Choose a profile first

This is the only decision that changes your architecture.

**Local decisioning** syncs signed campaign bundles to your machine on a
schedule. The auction runs on your hardware against the full conversation, and
signed receipts go back later in batches. Nothing about the conversation
leaves, including from the exchange's point of view. Fill is lower because you
are matching against a cached set rather than live demand. Choose this if you
self-host, if your users expect privacy, or if you serve in a jurisdiction where
sending context off-box is a problem.

**Hosted decisioning** sends a bounded signal to the exchange per turn and gets
a signed decision back inside 80 ms. Fill is higher and you carry no auction
logic. The signal that leaves is constrained to closed enumerations under a
published k-anonymity floor, but it does leave. Choose this if you are a managed
provider and latency budget is not a concern.

Both use the same auction semantics, so revenue is comparable and you can switch
later without renegotiating anything.

### Where it goes in your stack

UAP is middleware around your completions endpoint, not something inside the
model. The ordering constraint is the whole point: the answer must be finished
before selection begins, so that selection cannot influence it.

```python
from uap import Node, Surface, ContextClassifier

node = Node(entity_id="node.yourco.example",
            model_id="hf:moonshotai/Kimi-K2-Instruct",
            signing_key=your_key, exchange_keys=exchange_ring)

# Scheduled, on a fixed cadence. Not per turn, and not on demand: which bundle
# you fetch and when would otherwise leak something about your traffic.
node.load_bundle(fetch_bundle())

def handle_turn(conversation, placement):
    answer = model.generate(conversation)              # finishes first
    signal = ContextClassifier.derive(conversation)    # never transmitted
    result = node.decide_local(signal, placement)      # no network call
    if result is None or result.winner is None:
        return answer                                  # no-fill renders nothing
    decision = build_decision(result)
    return node.compose(answer, decision).text         # concatenation, not a model
```

`ContextClassifier` in the reference implementation is a keyword stub. Replace it
with something real. The contract it must satisfy: it runs on your machine, its
output reduces to the published intent taxonomy, and it emits nothing outside a
closed enumeration. If a conversation classifies into any category in
`source/taxonomy/sensitive-1.0.json`, it must produce no ad request at all.

### What you must not do

Do not put creative text into a prompt, a system message, a tool description, or
retrieval context. Do not run a second generation conditioned on the winning ad.
Do not re-rank candidate answers by expected revenue. Do not let bid values reach
sampling, logit bias, or model routing.

`node.guard_context(messages, decision)` fails closed if creative text has
reached the model context. Call it immediately before `generate()`.

### Getting paid

Open an account with an exchange, complete identity verification, and enrol your
signing key. That moves you from trust tier 0 to tier 1, which is what makes CPM
inventory available to you. Tier 0 exists so anonymous self-hosted serving is
supported and honestly labelled, not so it is paid like a browser: it is
indistinguishable from general invalid traffic by construction and can only be
sold on CPA.

Your surface, meaning whatever renders to a human, signs the receipts. If your
surface and your node are the same process, say so honestly in the trust tier you
assert rather than claiming separation you do not have.

### Effort

A day for local decisioning if you already have a classifier. The auction, the
composer, the signing, and the receipt flow are in the reference implementation.
What you write is the classifier, the bundle fetch schedule, and the wiring into
your completions handler.

## Part 2. Demand sources

You represent advertisers and want to reach these turns. There are two ways in
and they have very different costs.

### Option A: ship campaign bundles

You give the exchange line items, each carrying a targeting predicate, a price,
pacing, and creatives. The exchange packages them into signed bundles that sync
to nodes, and the auction runs on the node without you being in the request path.

```json
{
  "line_item_id": "li_991",
  "advertiser": { "id": "brand.acme.example", "display_name": "Acme Travel" },
  "targeting": { "all": [
    { "intent_any": ["travel.accommodation.hotel", "travel.destination.japan"] },
    { "commercial_intent_gte": 0.5 },
    { "locale_any": ["en-US", "en-GB"] },
    { "not": { "intent_any": ["travel.insurance"] } }
  ]},
  "pricing": { "model": "cpm", "bid_cpm_micros": 62000000 },
  "pacing": { "budget_micros": 5000000000, "node_share_impressions": 40 },
  "categories": ["travel.accommodation"],
  "creatives": [ { "creative_id": "cr_884", "format": "sponsored_card", "...": "..." } ]
}
```

No latency requirement, no bidder to operate, no infrastructure. You are writing
a targeting expression and a budget. This is the only way to reach local
decisioning supply, which is the supply that does not exist on any other network.

The targeting language is closed and total: boolean combinators over enumerated
signal fields, no regex, no arithmetic on user data, no code. That is a
restriction on you, and it is deliberate. A node must be able to bound evaluation
cost and prove afterwards that the auction ran as the bundle specified.

### Option B: bid in real time

Expose `POST /uap/v1/bid`, receive an `AdRequest`, return a `BidResponse` inside
the timeout. This reaches hosted supply only.

`conformance/vectors/valid/ad-request-full.json` is a complete request body.
Every field names its OpenRTB 2.6 equivalent in the schema, so if you already run
a bidder this is a translation layer rather than a rewrite. Deals, seat lists,
GPP and DSA consent, GARM brand suitability, seller-supplied CTR and viewability
predictions, and the supply chain are all present and mean what they mean
elsewhere.

Three things differ from a normal bid request and will break a naive port.

There is no user object and there cannot be one. No cookie, no device id, no
hashed email, no lookalike seed. Targeting is contextual, derived on the node,
and reduced to a published taxonomy before it is transmitted. Retargeting is not
supported and will not be.

There is no `adm`, no HTML, and no template. Your creative is structured fields
that the surface renders as inert text. If your creative pipeline emits markup,
that pipeline does not work here.

Frequency capping is per node, not network-wide, because network-wide capping
requires an identifier the protocol forbids. Plan reach accordingly.

### Conversions

Report them from your own systems or through an AP2 payment mandate reference.
Never from the serving node. The node cannot observe a conversion and has every
incentive to guess high.

## Part 3. Exchanges

You run the auction, sign bundles and decisions, verify receipts, and pay
everyone. You are also the only party with the leverage to enforce the rules,
because you are the only one holding money.

What you must do that a conventional exchange does not:

Fetch and honour `/.well-known/uap-model` for the model named in each request,
and refuse to clear an auction that violates it. An open-weights author who sets
`permitted: false` gets a real veto only because you enforce it.

Publish `/.well-known/uap-sellers.json` naming every entity you pay, and publish
your k-anonymity floor so it can be audited.

Verify receipts rather than trust them. The reference implementation checks
signature against an enrolled key, nonce liveness and single use, creative digest
against what was issued, the integrity assertions, viewability consistency, trust
tier against pricing model, and replays the auction trace against the bundle you
signed. Only receipts that pass all of it enter settlement.

Pay the model steward their declared share, and do not reduce it.

### The bootstrapping problem, stated honestly

Nobody runs a UAP exchange yet. Supply will not integrate without demand, demand
will not integrate without supply, and the protocol does not solve that. The
realistic first move is a single party who wants the market to exist operating
all three roles for a narrow vertical, then opening the demand side once there
is inventory worth bidding on. That is how every ad network started, including
the closed one this protocol is a response to.

## Sequence, end to end

Local decisioning. The only per-turn work is on the node.

```text
scheduled     exchange signs a campaign bundle
              node fetches it, verifies the signature, caches it

per turn      user sends a turn
              node generates the answer to completion
              node classifies context locally
              node runs the auction against the cached bundle
              node composes answer and creative deterministically
              surface renders, measures, and signs a receipt

later         receipts upload in a delayed, shuffled batch
              exchange verifies each one and replays the auction trace
              verified receipts settle; splits pay node, steward, exchange
```

Hosted decisioning replaces the cached-bundle step with a signed request and
response inside the 80 ms budget. Everything after composition is identical.
