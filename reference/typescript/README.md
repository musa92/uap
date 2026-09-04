# UAP, JavaScript implementation

An independent implementation of the serve-time core: RFC 8785 canonical JSON,
Ed25519 with domain-separated object signatures, the Appendix A predicate
language, and the integrity boundary.

JavaScript rather than a second Python package on purpose. The **surface** is
the party that renders a turn, measures viewability and signs the receipt the
exchange bills against, and surfaces run in browsers. A protocol whose receipt
signing exists only in Python cannot be implemented by the component that is
supposed to do the signing.

Zero dependencies. `node:crypto` implements Ed25519 natively, so this vendors
into a surface without pulling in a tree, for the same reason the Python side
has no dependencies.

## Independence is the point

Nothing here imports the Python implementation, and it was not translated from
it. Both were written from the specification. `test/interop.test.js` loads
vectors the Python side produced and recomputes every value:

```bash
npm test
```

It asserts that both implementations produce **identical canonical bytes**,
**identical signatures**, identical creative escaping, identical composition,
and identical predicate results including the fail-closed cases.

That last property is the one that matters. Every UAP signature covers the
canonical bytes of an object, so a single byte of disagreement means every
signature one side produces fails on the other and the protocol does not
interoperate. It is also what SPEC.md §14 requires before a capability can
leave draft.

## Use

```js
const uap = require('@uap/protocol');

// Verify a decision the exchange signed
const ring = new uap.KeyRing().add(uap.VerifyingKey.fromJwk(jwk));
const [ok, why] = uap.verifyObject(decision, ring, 'decision');

// Compose, then prove the answer was untouched
const out = uap.compose(answer, decision);
uap.verifyComposition(out.text, answer, decision);   // [true, 'composition is exact']
uap.verifyAnswerCommitment(out.text, committedDigest);

// Run a local auction predicate
const match = uap.predicate.compile(lineItem.targeting);
match(uap.predicate.prepare(signal));
```

## What is not here

The exchange, the buy side, settlement, and the HTTP server. Those live in the
Python implementation. This covers what a surface and a serving node need,
which is the part that has to exist in more than one language.
