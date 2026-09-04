/**
 * Targeting predicate evaluation (SPEC.md Appendix A).
 *
 * A closed, total, side-effect-free boolean language over ContextSignal. Two
 * properties are load-bearing and are the reason this is worth reimplementing
 * rather than sharing: it must fail closed, and it must agree with the Python
 * evaluator on every input, or a node's local auction diverges from the
 * exchange's replay of it and settlement becomes a dispute.
 */
'use strict';

const MAX_DEPTH = 8;
const MAX_TERMS = 64;
const RISK_ORDER = { low: 0, medium: 1, high: 2 };

class PredicateError extends Error {}

function intentIds(signal) {
  if (signal && signal._intent_set) return signal._intent_set;
  const out = new Set();
  for (const i of (signal && signal.intents) || []) {
    if (i && typeof i === 'object') out.add(i.id);
  }
  return out;
}

/** Precompute derived views. Call once per turn, before evaluating a bundle. */
function prepare(signal) {
  const set = new Set();
  for (const i of (signal && signal.intents) || []) {
    if (i && typeof i === 'object') set.add(i.id);
  }
  return { ...signal, _intent_set: set };
}

function confidence(signal, id) {
  for (const i of (signal && signal.intents) || []) {
    if (i && typeof i === 'object' && i.id === id) {
      return typeof i.confidence === 'number' ? i.confidence : null;
    }
  }
  return null;
}

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

function term(op, arg, s) {
  switch (op) {
    case 'intent_any': {
      if (!Array.isArray(arg)) return false;
      const ids = intentIds(s);
      return arg.some((x) => ids.has(x));
    }
    case 'intent_all': {
      if (!Array.isArray(arg)) return false;
      const ids = intentIds(s);
      return arg.every((x) => ids.has(x));
    }
    case 'intent_confidence_gte': {
      if (!arg || typeof arg !== 'object') return false;
      const got = confidence(s, arg.id);
      return isNum(got) && isNum(arg.value) && got >= arg.value;
    }
    case 'commercial_intent_gte':
      return isNum(s && s.commercial_intent) && isNum(arg) && s.commercial_intent >= arg;
    case 'locale_any':
      return Array.isArray(arg) && arg.includes(s && s.locale);
    case 'geo_any':
      return Array.isArray(arg) && !!(s && s.geo) && typeof s.geo === 'object' && arg.includes(s.geo.value);
    case 'surface_any':
      return Array.isArray(arg) && arg.includes(s && s.surface_hint);
    case 'format_any':
      return Array.isArray(arg) && arg.includes(s && s._format);
    case 'turn_bucket_any':
      return Array.isArray(arg) && !!(s && s.turn) && typeof s.turn === 'object' && arg.includes(s.turn.index_bucket);
    case 'brand_risk_max': {
      const safety = s && s.safety;
      if (!safety || typeof safety !== 'object' || !(arg in RISK_ORDER)) return false;
      const got = safety.brand_risk;
      return got in RISK_ORDER && RISK_ORDER[got] <= RISK_ORDER[arg];
    }
    default:
      return false;                      // unknown operator: fail closed
  }
}

/** Evaluate. Never throws; never returns true by accident. */
function evaluate(predicate, signal, depth = 0) {
  if (depth > MAX_DEPTH || !predicate || typeof predicate !== 'object' || Array.isArray(predicate)) return false;
  const keys = Object.keys(predicate);
  if (keys.length !== 1) return false;
  const op = keys[0];
  const arg = predicate[op];
  if (op === 'all') return Array.isArray(arg) && arg.every((p) => evaluate(p, signal, depth + 1));
  if (op === 'any') return Array.isArray(arg) && arg.some((p) => evaluate(p, signal, depth + 1));
  if (op === 'not') return !evaluate(arg, signal, depth + 1);
  return term(op, arg, signal);
}

/** Compile once at bundle load; evaluate per turn. */
function compile(predicate, depth = 0) {
  if (depth > MAX_DEPTH || !predicate || typeof predicate !== 'object' || Array.isArray(predicate)) return () => false;
  const keys = Object.keys(predicate);
  if (keys.length !== 1) return () => false;
  const op = keys[0];
  const arg = predicate[op];

  if (op === 'all') {
    if (!Array.isArray(arg)) return () => false;
    const parts = arg.map((p) => compile(p, depth + 1));
    return (s) => { for (const f of parts) if (!f(s)) return false; return true; };
  }
  if (op === 'any') {
    if (!Array.isArray(arg)) return () => false;
    const parts = arg.map((p) => compile(p, depth + 1));
    return (s) => { for (const f of parts) if (f(s)) return true; return false; };
  }
  if (op === 'not') {
    const inner = compile(arg, depth + 1);
    return (s) => !inner(s);
  }
  return (s) => term(op, arg, s);
}

function depthOf(p) {
  if (!p || typeof p !== 'object' || Array.isArray(p)) return 0;
  const keys = Object.keys(p);
  if (keys.length !== 1) return 0;
  const [op] = keys; const arg = p[op];
  if ((op === 'all' || op === 'any') && Array.isArray(arg)) {
    return 1 + Math.max(0, ...arg.map(depthOf));
  }
  if (op === 'not') return 1 + depthOf(arg);
  return 1;
}

function countTerms(p) {
  if (!p || typeof p !== 'object' || Array.isArray(p)) return 1;
  const keys = Object.keys(p);
  if (keys.length !== 1) return 1;
  const [op] = keys; const arg = p[op];
  if ((op === 'all' || op === 'any') && Array.isArray(arg)) return arg.reduce((n, x) => n + countTerms(x), 0);
  if (op === 'not') return countTerms(arg);
  return 1;
}

/** Reject a predicate that exceeds the Appendix A bounds, before evaluating it. */
function validate(predicate) {
  const d = depthOf(predicate);
  const t = countTerms(predicate);
  if (d > MAX_DEPTH) throw new PredicateError(`predicate depth ${d} exceeds ${MAX_DEPTH}`);
  if (t > MAX_TERMS) throw new PredicateError(`predicate has ${t} terms, exceeds ${MAX_TERMS}`);
}

module.exports = { evaluate, compile, prepare, validate, PredicateError, MAX_DEPTH, MAX_TERMS };
