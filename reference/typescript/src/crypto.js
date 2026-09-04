/**
 * Ed25519 signing and detached object signatures.
 *
 * Uses node:crypto, which implements Ed25519 natively, so this file has no
 * dependencies for the same reason the Python side has none: it should be
 * vendorable into a surface without dragging in a tree.
 *
 * Signatures are detached and domain-separated. The signing input is
 *
 *     tag || 0x00 || JCS(object without "signature")
 *
 * identical to the Python implementation. Without the tag, a signature over
 * one object type replays as another wherever the two share a field subset.
 */
'use strict';

const crypto = require('node:crypto');
const { canonicalize } = require('./canonical');

const DOMAINS = {
  decision: 'uap-decision/2026-09-02',
  receipt: 'uap-receipt/2026-09-02',
  bundle: 'uap-bundle/2026-09-02',
  bid: 'uap-bid/2026-09-02',
  sellers: 'uap-sellers/2026-09-02',
  supply_chain: 'uap-supplychain/2026-09-02',
  settlement: 'uap-settlement/2026-09-02',
};

const PKCS8_PREFIX = Buffer.from('302e020100300506032b657004220420', 'hex');
const SPKI_PREFIX_LEN = 12;

function b64uEncode(buf) {
  return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function b64uDecode(text) {
  if (text.endsWith('=')) throw new Error('base64url MUST be unpadded (RFC 4648 §5)');
  return Buffer.from(text.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
}

class SigningKey {
  constructor(kid, seed) {
    if (seed.length !== 32) throw new Error('an Ed25519 seed is 32 bytes');
    this.kid = kid;
    this.seed = seed;
    this._key = crypto.createPrivateKey({
      key: Buffer.concat([PKCS8_PREFIX, seed]), format: 'der', type: 'pkcs8',
    });
    this.publicKey = crypto.createPublicKey(this._key)
      .export({ format: 'der', type: 'spki' }).subarray(SPKI_PREFIX_LEN);
  }

  static generate(kid) { return new SigningKey(kid, crypto.randomBytes(32)); }
  static fromSeedHex(kid, hex) { return new SigningKey(kid, Buffer.from(hex, 'hex')); }

  sign(message) { return crypto.sign(null, message, this._key); }

  verifyingKey() { return new VerifyingKey(this.kid, this.publicKey); }
}

class VerifyingKey {
  constructor(kid, raw) {
    if (raw.length !== 32) throw new Error('an Ed25519 public key is 32 bytes');
    this.kid = kid;
    this.raw = raw;
    this._key = crypto.createPublicKey({
      key: Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), raw]),
      format: 'der', type: 'spki',
    });
  }

  verify(message, signature) {
    try { return crypto.verify(null, message, this._key, signature); }
    catch { return false; }
  }

  toJwk() {
    return { kty: 'OKP', crv: 'Ed25519', kid: this.kid, x: b64uEncode(this.raw), alg: 'EdDSA', use: 'sig' };
  }

  static fromJwk(jwk) {
    if (jwk.kty !== 'OKP' || jwk.crv !== 'Ed25519') throw new Error('expected an OKP/Ed25519 JWK');
    return new VerifyingKey(jwk.kid, b64uDecode(jwk.x));
  }
}

class KeyRing {
  constructor() { this.keys = new Map(); }
  add(key) { this.keys.set(key.kid, key); return this; }
  get(kid) { return this.keys.get(kid); }
  toJwks() { return { keys: [...this.keys.values()].map((k) => k.toJwk()) }; }
}

function signingInput(obj, domain) {
  const tag = DOMAINS[domain];
  if (!tag) throw new Error(`unknown signature domain ${domain}`);
  const body = { ...obj };
  delete body.signature;
  return Buffer.concat([Buffer.from(tag, 'utf8'), Buffer.from([0]), canonicalize(body)]);
}

function signObject(obj, key, domain, created) {
  const signature = {
    kid: key.kid, alg: 'EdDSA',
    value: b64uEncode(key.sign(signingInput(obj, domain))),
    domain: DOMAINS[domain],
  };
  if (created) signature.created = created;
  return { ...obj, signature };
}

function verifyObject(obj, keyring, domain) {
  const sig = obj && obj.signature;
  if (!sig || typeof sig !== 'object') return [false, 'no signature member'];
  if (sig.alg !== 'EdDSA') return [false, `unsupported alg ${sig.alg}`];
  const key = keyring.get(sig.kid);
  if (!key) return [false, `kid ${sig.kid} not enrolled`];
  let raw;
  try { raw = b64uDecode(sig.value || ''); }
  catch (e) { return [false, `malformed signature value: ${e.message}`]; }
  if (!key.verify(signingInput(obj, domain), raw)) return [false, 'signature did not verify'];
  return [true, 'ok'];
}

module.exports = { SigningKey, VerifyingKey, KeyRing, signObject, verifyObject, signingInput, b64uEncode, b64uDecode, DOMAINS };
