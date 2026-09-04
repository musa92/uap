/**
 * Cross-implementation conformance.
 *
 * These vectors were produced by the Python implementation. Nothing here
 * imports it; every value is recomputed from the JavaScript implementation and
 * compared. A single byte of disagreement in canonicalization would mean every
 * signature one side produces fails on the other, so this is the test that
 * decides whether UAP has two interoperating implementations or one
 * implementation and a document.
 */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const uap = require('../src');
const P = uap.predicate;

const V = JSON.parse(fs.readFileSync(
  path.join(__dirname, '..', '..', '..', 'conformance', 'interop', 'vectors.json'), 'utf8'));

test('canonical bytes match the Python implementation', () => {
  for (const c of V.canonical) {
    assert.equal(uap.serialize(c.value), c.canonical, `case: ${c.name}`);
  }
});

test('canonicalization is stable under key reordering', () => {
  for (const c of V.canonical) {
    if (c.value && typeof c.value === 'object' && !Array.isArray(c.value)) {
      const reversed = Object.fromEntries(Object.entries(c.value).reverse());
      assert.equal(uap.serialize(reversed), c.canonical, `case: ${c.name}`);
    }
  }
});

test('the key derives to the published RFC 8032 public key', () => {
  const key = uap.SigningKey.fromSeedHex(V.kid, V.seed_hex);
  assert.equal(key.publicKey.toString('hex'), V.public_key_hex);
});

test('signatures produced by Python verify here', () => {
  const key = uap.SigningKey.fromSeedHex(V.kid, V.seed_hex);
  const ring = new uap.KeyRing().add(key.verifyingKey());
  for (const c of V.signing) {
    const signed = { ...c.object, signature: { kid: V.kid, alg: 'EdDSA', value: c.signature } };
    const [ok, why] = uap.verifyObject(signed, ring, c.domain);
    assert.ok(ok, `case ${c.name}: ${why}`);
  }
});

test('signatures produced here are byte-identical to Python', () => {
  const key = uap.SigningKey.fromSeedHex(V.kid, V.seed_hex);
  for (const c of V.signing) {
    const signed = uap.signObject(c.object, key, c.domain);
    assert.equal(signed.signature.value, c.signature, `case: ${c.name}`);
  }
});

test('domain separation blocks cross-type replay across implementations', () => {
  const key = uap.SigningKey.fromSeedHex(V.kid, V.seed_hex);
  const ring = new uap.KeyRing().add(key.verifyingKey());
  const decision = V.signing.find((c) => c.domain === 'decision');
  const signed = { ...decision.object, signature: { kid: V.kid, alg: 'EdDSA', value: decision.signature } };
  assert.ok(uap.verifyObject(signed, ring, 'decision')[0]);
  assert.equal(uap.verifyObject(signed, ring, 'bundle')[0], false);
  assert.equal(uap.verifyObject(signed, ring, 'receipt')[0], false);
});

test('tampering is detected', () => {
  const key = uap.SigningKey.fromSeedHex(V.kid, V.seed_hex);
  const ring = new uap.KeyRing().add(key.verifyingKey());
  const c = V.signing[0];
  const tampered = { ...c.object, nonce: 'n_changed',
                     signature: { kid: V.kid, alg: 'EdDSA', value: c.signature } };
  assert.equal(uap.verifyObject(tampered, ring, c.domain)[0], false);
});

test('padded base64url is refused', () => {
  const key = uap.SigningKey.fromSeedHex(V.kid, V.seed_hex);
  const ring = new uap.KeyRing().add(key.verifyingKey());
  const c = V.signing[0];
  const padded = { ...c.object, signature: { kid: V.kid, alg: 'EdDSA', value: c.signature + '=' } };
  assert.equal(uap.verifyObject(padded, ring, c.domain)[0], false);
});

test('creative escaping matches the Python implementation', () => {
  for (const c of V.escaping) {
    assert.equal(uap.escapeText(c.input, 'markdown'), c.markdown, `input: ${JSON.stringify(c.input)}`);
  }
});

test('composition is byte-identical to the Python composer', () => {
  const c = V.composition;
  const out = uap.compose(c.answer, c.decision);
  assert.equal(out.text, c.text);
  assert.equal(out.organicAnswerDigest, c.organic_answer_digest);
  assert.equal(uap.answerDigest(c.answer), c.answer_digest);
});

test('the organic answer survives composition byte for byte', () => {
  const c = V.composition;
  const out = uap.compose(c.answer, c.decision);
  assert.equal(uap.stripAdBlock(out.text), c.answer);
  assert.deepEqual(uap.verifyComposition(out.text, c.answer, c.decision), [true, 'composition is exact']);
  assert.equal(uap.verifyAnswerCommitment(out.text, c.organic_answer_digest)[0], true);
});

test('an answer edited to favour the advertiser is caught', () => {
  const c = V.composition;
  const out = uap.compose(c.answer, c.decision);
  const edited = out.text.replace('foliage', 'foliage, and Acme has the best rates');
  assert.equal(uap.verifyAnswerCommitment(edited, c.organic_answer_digest)[0], false);
  assert.equal(uap.verifyComposition(edited, c.answer, c.decision)[0], false);
});

test('predicate evaluation agrees with Python on every case', () => {
  for (const c of V.predicates) {
    assert.equal(P.evaluate(c.predicate, c.signal), c.expected,
      `predicate ${JSON.stringify(c.predicate)} against ${JSON.stringify(c.signal)}`);
  }
});

test('the compiled path agrees with the interpreted path', () => {
  for (const c of V.predicates) {
    assert.equal(P.compile(c.predicate)(P.prepare(c.signal)), c.expected,
      `predicate ${JSON.stringify(c.predicate)}`);
  }
});

test('unknown operators never match', () => {
  assert.equal(P.evaluate({ exec_shell: 'rm -rf /' }, {}), false);
  assert.equal(P.evaluate({ regex_match: '.*' }, {}), false);
  assert.equal(P.compile({ eval_js: '1' })(P.prepare({})), false);
});

test('Appendix A bounds are enforced', () => {
  let deep = { intent_any: ['x'] };
  for (let i = 0; i < 12; i++) deep = { all: [deep] };
  assert.throws(() => P.validate(deep), P.PredicateError);
  assert.equal(P.evaluate(deep, { intents: [{ id: 'x' }] }), false);

  const wide = { all: Array.from({ length: 70 }, () => ({ intent_any: ['x'] })) };
  assert.throws(() => P.validate(wide), P.PredicateError);
});

test('NaN and Infinity are refused', () => {
  assert.throws(() => uap.serialize(NaN), RangeError);
  assert.throws(() => uap.serialize(Infinity), RangeError);
});

test('duplicate object keys are rejected on parse', () => {
  assert.throws(() => uap.parse('{"a":1,"a":2}'), /duplicate/);
  assert.deepEqual(uap.parse('{"a":1,"b":2}'), { a: 1, b: 2 });
});
