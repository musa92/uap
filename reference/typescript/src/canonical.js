/**
 * RFC 8785 JSON Canonicalization Scheme.
 *
 * Independent of the Python implementation on purpose. Two implementations
 * that agree byte for byte are evidence the specification is unambiguous; two
 * that share a codebase are evidence of nothing. `test/cross.test.js` asserts
 * the agreement against vectors Python produced.
 */
'use strict';

const ESCAPES = { 0x08: '\\b', 0x09: '\\t', 0x0a: '\\n', 0x0c: '\\f', 0x0d: '\\r', 0x22: '\\"', 0x5c: '\\\\' };

/**
 * Serialize a number the way ECMAScript does, which RFC 8785 §3.2.2.1 requires.
 * JavaScript's own Number#toString already implements that algorithm, so the
 * only work here is refusing what JSON cannot represent and normalising -0.
 */
function formatNumber(value) {
  if (!Number.isFinite(value)) throw new RangeError('NaN and Infinity are not representable in JSON');
  if (value === 0) return '0';                       // also collapses -0
  return String(value);
}

function formatString(value) {
  let out = '"';
  for (const ch of value) {
    const cp = ch.codePointAt(0);
    if (ESCAPES[cp] !== undefined) out += ESCAPES[cp];
    else if (cp < 0x20) out += '\\u' + cp.toString(16).padStart(4, '0');
    else out += ch;
  }
  return out + '"';
}

/**
 * Sort by UTF-16 code unit, not by code point. The two orders disagree above
 * the BMP: a supplementary character sorts before U+E000 as surrogate pairs
 * but after it as code points. JavaScript's default string comparison is
 * already UTF-16 code unit order, which is why this is a bare comparison.
 */
function compareKeys(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

function write(value, out) {
  if (value === null) { out.push('null'); return; }
  const t = typeof value;
  if (t === 'boolean') { out.push(value ? 'true' : 'false'); return; }
  if (t === 'number') { out.push(formatNumber(value)); return; }
  if (t === 'string') { out.push(formatString(value)); return; }
  if (Array.isArray(value)) {
    out.push('[');
    value.forEach((item, i) => { if (i) out.push(','); write(item, out); });
    out.push(']');
    return;
  }
  if (t === 'object') {
    out.push('{');
    const keys = Object.keys(value).sort(compareKeys);
    keys.forEach((k, i) => {
      if (i) out.push(',');
      out.push(formatString(k), ':');
      write(value[k], out);
    });
    out.push('}');
    return;
  }
  throw new TypeError(`${t} is not JSON-serializable`);
}

/** Canonical JSON text. */
function serialize(value) {
  const out = [];
  write(value, out);
  return out.join('');
}

/** Canonical JSON bytes, which is what every signature and digest covers. */
function canonicalize(value) {
  return Buffer.from(serialize(value), 'utf8');
}

/**
 * Parse, rejecting duplicate object keys. Most parsers accept them and resolve
 * last-wins, which lets a signed object and its verified form differ.
 */
function parse(text) {
  const seen = [];
  const value = JSON.parse(text, function reviver(key, val) {
    return val;
  });
  // JSON.parse gives no hook for duplicates, so re-scan the source.
  const dup = /"((?:[^"\\]|\\.)*)"\s*:/g;
  const stack = [];
  let m;
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '{') { stack.push(new Set()); depth++; }
    else if (c === '}') { stack.pop(); depth--; }
    else if (c === '"' && depth > 0) {
      dup.lastIndex = i;
      const hit = dup.exec(text);
      if (hit && hit.index === i && stack.length) {
        const key = hit[1];
        if (stack[stack.length - 1].has(key)) throw new SyntaxError(`duplicate object key ${key}`);
        stack[stack.length - 1].add(key);
      }
      // skip the string body
      i++;
      while (i < text.length && text[i] !== '"') { if (text[i] === '\\') i++; i++; }
    }
  }
  return value;
}

module.exports = { serialize, canonicalize, parse, formatNumber };
