# Quickstart: monetise a model in five minutes

For anyone running vLLM, SGLang, Ollama, llama.cpp, TGI, LM Studio, or any
other server that exposes `/v1/chat/completions`. One process goes in front of
it. Your model, your clients and your prompts do not change.

## 1. Install

```bash
pip install uap-protocol
```

Standard library only. Nothing is added to the inference path.

## 2. Mint a signing key

```bash
uap keygen --kid surface-ed25519-01 > key.json
```

The `jwk` inside is public; give it to the exchange when you enrol. The
`seed_hex` is your private key. Enrolling moves you from trust tier 0 to tier
1, which is what makes CPM inventory available to you.

## 3. Run the proxy

```bash
uap proxy \
  --upstream http://localhost:8000 \
  --exchange https://uax.example.com \
  --entity  node.yourco.example \
  --model   hf:moonshotai/Kimi-K2-Instruct \
  --seed    "$(jq -r .seed_hex key.json)"
```

The key has to be enrolled against a payee account before anything is paid.
Until it is, the exchange cannot map a receipt to an entity and rejects every
one with `signature`: **ads render normally and you earn nothing.** Check
`enrolled` in `/uap/status`. On a development exchange, `--enrol` creates the
account and binds the key at startup; against a real one you enrol out of band
and the exchange verifies you first.

Point your OpenAI client at `http://localhost:8800` instead of `:8000`. That
is the whole integration.

## What the proxy does on each turn

1. Forwards the request to your server, unchanged.
2. Waits for the answer to finish. Nothing in the ad path can reach the model.
3. Classifies the conversation locally. Only bounded codes exist afterwards;
   the text never leaves.
4. Runs the auction against a signed bundle it fetched an hour ago. Zero
   network calls.
5. Appends a disclosed block under the answer, or nothing.
6. Signs a receipt and queues it. Receipts upload later, batched and delayed.

Streaming requests pass straight through. An ad appended to a stream would
have to be chosen before the answer finished, which the integrity boundary
forbids.

## The classifier

The proxy ships with a keyword classifier that **fails closed**: it will not
serve anything until you replace it, because a nine-word list cannot tell a
travel question from a question about a medical bill. To try the flow anyway,
add `--accept-unverified-classifier`. Do not run that in production.

To plug in your own, subclass `uap.ContextClassifier`, set
`production_ready = True`, and pass it to `UAPMiddleware(classifier=...)`. The
contract: run on the node, reduce to the published taxonomy, return
`sensitive_category` as `True`, `False`, or `None` for undetermined. `None`
suppresses the turn exactly as `True` does.

## Check it is working

```bash
curl http://localhost:8800/uap/status
```

Returns bundle state, turns seen, placements filled, and receipts waiting to
upload.

## Try it without an exchange

```bash
docker compose up
```

Brings up a reference exchange, a stand-in model server, and the proxy on
`:8800`. Send it a chat completion and you will get an answer with a sponsored
block under it.
