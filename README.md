# Universal Ads Protocol (UAP)

An open protocol for selling advertising on LLM inference. Any inference
provider can sell a placement, any demand source can buy it, and the ad cannot
change the answer or take the conversation off the machine.

[Specification](./SPEC.md) · [Market context](./docs/documentation/market-context.md) · draft-01 · protocol version `2026-09-02` · Apache-2.0

Written by [Musa Aghayev](https://github.com/musa92). Design questions and
critique are welcome in [Discussions](https://github.com/musa92/uap/discussions);
I read all of them.

## Why this exists

Assistants now carry ads. ChatGPT began serving sponsored links below answers in
February 2026, and the unit works commercially. But that is a closed platform:
OpenAI's Advertiser API sells one surface, and nobody else can sell into it or
buy through it.

Everyone else who serves a model has no way to monetise it. The obvious
workaround, sending the conversation to an ad server and pasting the winning
creative into the prompt, fails twice. It leaks private context to a third
party, and it hands an advertiser write access to the model's reasoning for the
price of a CPM.

UAP is the interoperable version, built so neither failure is expressible.

## Three invariants

An implementation that violates any of these is not conformant, whatever else it
does.

**Context confinement.** Prompt text, completion text, and any identifier stable
across sessions never leave the serving node. Only bounded, enumerable signals
may be transmitted. No consent flow unlocks this.

**Answer integrity.** Ad presence, identity, and price never change the answer.
Creative never enters the model's context and never influences decoding.

**Earned payment.** The serving node is untrusted. Payment follows what the
surface attested and the settlement layer verified, never what the node claimed.

## How the answer guarantee works

"The ad did not change the answer" is a claim a node has every incentive to make
falsely, so it rests on three mechanisms rather than an attestation.

**Ordering.** The node commits to the answer digest inside the `AdRequest`,
before the exchange runs the auction. The exchange holds the commitment before a
winner exists, so an answer matching it could not have depended on the outcome.
A receipt whose rendered answer does not match is not billable. Only the digest
is sent, so this adds no context egress.

**Composition.** The composer is deterministic and never calls a model. Given
the answer and the decision, anyone can recompute the exact bytes and compare.
Byte equality proves the output is the organic answer followed by the disclosed
creative, with nothing interleaved or rewritten. This needs no key and no
cooperation from the node:

```python
from uap import verify_composition, verify_answer_commitment

verify_composition(rendered, answer, decision)     # (True, 'composition is exact')
verify_answer_commitment(rendered, committed)      # (True, 'matches the commitment')
```

**Holdout.** The exchange marks a deterministic fraction of requests as holdout.
The node runs the identical path, no ad is served, and it still reports the
answer digest. Systematic divergence between served and held-out answers is
evidence of decode influence that no per-turn check can produce.

Local decisioning has no round trip and so cannot produce the ordering proof.
There the guarantee rests on composition, on the holdout, and at trust tier 2 on
an attestation covering the enforcement path. The specification prices that
difference rather than pretending it away.

## Run it

Python 3.10 or later. No dependencies.

```bash
git clone https://github.com/musa92/uap && cd uap
make demo     # full flow in process, then the same flow over HTTP
make test     # 210 schema and conformance checks, links, 57 unit tests
make serve    # run the reference exchange on localhost:8787
```

The first demo runs four parties with four keys through one impression, then
shows five abuse cases being rejected: a replayed nonce, a swapped creative
digest, a tier 0 node billed on CPM, an impression index past the pacing
allocation, and a sensitive turn that produces no auction. The second does the
same over a socket against the reference exchange.

In local decisioning the nonce is derived rather than issued, because there is
no round trip to issue one. The exchange recomputes it from the bundle it
signed, resolves the entity from the signing key rather than from anything the
node sends, and derives the clearing price from the reported auction trace
instead of reading it from the receipt.

## Integrating

Two five-minute guides: [monetise a model](docs/documentation/quickstart-provider.md)
if you serve one, [run a campaign](docs/documentation/quickstart-advertiser.md)
if you buy. Or `docker compose up` for an exchange, a stand-in model and the
proxy, wired together.

If you serve a model you are the serving node. If you render to a human you are
the surface. They are separate because a node signing its own impression counts
is a claim, not a measurement.

```python
from uap import Node, Surface, ContextClassifier

node = Node("node.example", "hf:moonshotai/Kimi-K2-Instruct",
            signing_key=key, exchange_keys=ring)
node.load_bundle(bundle)                          # hourly, not per turn

answer   = model.generate(conversation)           # ads cannot reach this call
signal   = ContextClassifier.derive(conversation) # stays on this machine
result   = node.decide_local(signal, placement)   # zero network calls
composed = node.compose(answer, decision)         # deterministic, not a model
```

No call takes `conversation` and a network address in the same expression.

If you already run an OpenAI-compatible server, which vLLM, SGLang, Ollama,
llama.cpp, TGI and LM Studio all are, the integration is one wrapper:

```python
from uap.middleware import UAPMiddleware, ExchangeClient

ads = UAPMiddleware(node, surface, ExchangeClient("https://uax.example.com", agent))
ads.sync_bundle()                              # scheduled

response = ads.complete(your_client, request)  # upstream call is untouched
```

`complete` calls upstream first and appends a disclosed sponsored block only if
one wins. Any error in the ad path returns the unmodified completion, so a
monetisation bug can never cost you an answer.

Buying side: `conformance/vectors/valid/ad-request-full.json` is a complete
request body with deals, seller metrics, GPP and DSA consent, GARM brand
suitability, and a two-hop supply chain. Every field names its OpenRTB 2.6
equivalent in `source/schemas/supply/ad_request.json`, so existing demand needs
a translation layer rather than a rewrite.

The checks a buyer runs before spending are implemented, not just specified:

```python
from uap import verify_chain, assess, meets_mrc

verify_chain(chain, declarations)   # every hop resolves in a uap-sellers.json
meets_mrc(viewability)              # 50% of pixels for 1s, and the rest
assess(receipts)                    # viewable and IVT rates, dwell anomalies
```

`verify_chain` rejects a hop absent from the named system's seller declaration,
a hop claiming a trust tier the system does not substantiate, an incomplete
chain, a loop, and a chain in which nobody is in the payment flow. `assess`
flags a dwell distribution too uniform to be human, which is how fabrication at
scale actually shows up.

Full integration guide for both sides:
[docs/documentation/integration.md](./docs/documentation/integration.md).

## Two decisioning profiles

**Hosted.** The node sends a bounded signal, the exchange runs the auction and
returns a signed decision. Familiar, and the signal is constrained by a
published k-anonymity floor.

**Local.** Signed campaign bundles sync to the node on a schedule. The auction
runs on-device against the full private context, and batched signed receipts go
back later. Nothing about the conversation leaves, including from the exchange's
point of view. This is the same architecture as Chrome's Protected Audience API,
applied to a turn instead of a page.

## Status

Draft for public comment. §14 requires two independent interoperating
implementations to leave draft. The serve-time core now has two, in Python and
JavaScript, written from the specification rather than translated from each
other, and `make interop` holds them to byte-identical canonicalization,
signatures, escaping, composition and predicate results.

Implemented: canonicalization, signing, the targeting predicate language, the
auction, the integrity boundary, receipt verification, settlement splits, and
schemas for all of it.

Sensitive-category classification fails closed. `sensitive_category` is
three-valued, because a two-valued flag collapses "found no evidence" into
"confidently not sensitive", and only an explicit false permits a turn to carry
advertising. A node also refuses to act on a classifier that does not declare
itself evaluated against the sensitive taxonomy. The consequence is that the
shipped keyword classifier monetises nothing unless the operator explicitly
accepts the risk, which is correct and which means **nobody can run this in
production without building a real classifier first**. That is the hardest
remaining piece and it is not in this repository.

The supply service is defined in OpenAPI 3.1 at
`source/services/supply/rest.openapi.json` and implemented over HTTP in
`reference/python/uap/server.py`.

The buy side is implemented at the reference level: campaign and line-item
management, creative review that resolves URLs against the advertiser's
verified domains and scans for instruction-shaped text, forecasting as ranges
with sub-floor breakdowns suppressed, a conversions endpoint that refuses
serving nodes as a source, and aggregate reporting under a closed dimension
set with differential-privacy noise on intent breakdowns.

Not yet built: the billing lifecycle (invoicing, disputes, make-goods), RFC
9421 transport signing, and a production classifier.

Two design problems are documented rather than hidden:
frequency capping is enforceable only within one node, and Profile L pacing can
strand node revenue. Both are described in `SPEC.md`.

The parts most worth attacking are the k-anonymity floor (§6.5), bundle fetch as
a side channel (§8.2), and whether trust tier 0 has any honest demand (§9.3).

## Layout

```text
SPEC.md               normative specification
source/schemas/       JSON Schema for every wire object
source/services/      OpenAPI definition of the REST binding
source/taxonomy/      intent and sensitive-category taxonomies
reference/python/     reference implementation: exchange, buy side, settlement
reference/typescript/ second implementation: the serve-time core a surface runs
conformance/          vectors, positive and negative
examples/             end-to-end traces
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) and [GOVERNANCE.md](./GOVERNANCE.md).
Nothing in §6, §7, or §9 may be relaxed by an extension. Security reports: [SECURITY.md](./SECURITY.md).

## License

Apache-2.0. Specification text is additionally available under CC-BY-4.0 so the
protocol can be re-specified independently of this implementation.
