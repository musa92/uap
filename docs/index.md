# Universal Ads Protocol

An open protocol for advertising on LLM inference. Any inference provider can
sell a placement, any demand source can buy it, and the ad cannot change the
answer or take the conversation off the machine.

Draft-01 · protocol version `2026-09-02` · [GitHub](https://github.com/musa92/uap)

## Start here

- [Market context](documentation/market-context.md) — why this exists, with sources
- [Integration guide](documentation/integration.md) — what each party builds
- [Specification](specification/index.md) — the normative text
- [Schema reference](reference/index.md) — every wire object, generated from source

## Three invariants

**Context confinement.** Prompt text, completion text, and any identifier stable
across sessions never leave the serving node.

**Answer integrity.** Ad presence, identity, and price never change the answer.
The node commits to the answer digest before the auction runs, so this is
checkable rather than asserted.

**Earned payment.** The serving node is untrusted. Payment follows what the
surface attested and the settlement layer verified.

## Run it

```bash
git clone https://github.com/musa92/uap && cd uap
make demo     # full flow in process, then over HTTP
make test     # schemas, conformance, lint, 79 tests
```
