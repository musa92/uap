/**
 * The integrity boundary (SPEC.md §7).
 *
 * This is the module a surface actually runs, because surfaces are JavaScript:
 * they render the turn, measure viewability and sign the receipt. Having it
 * here rather than only in Python is the point.
 *
 * The composer is a pure function. It must never be a language model and
 * nothing here may be given a model handle.
 */
'use strict';

const crypto = require('node:crypto');

const SEPARATOR = '--- Sponsored ---';

// Escaped everywhere: these change meaning mid-line.
const MD_INLINE = /([\\`*_[\]<>|~])/g;
// Escaped only at line start, where they open a block. Escaping "." or "-"
// everywhere renders "arrival." as "arrival\." in live ad copy.
const MD_LEADING = /^(\s*)(?:([#+-])|(\d+)([.)]))/gm;
const CONTROL = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;

class IntegrityError extends Error {}

function escapeText(text, renderer) {
  let out = String(text).replace(CONTROL, '');
  if (renderer === 'markdown') {
    out = out.replace(MD_INLINE, '\\$1');
    return out.replace(MD_LEADING, (m, ws, block, digits, punct) =>
      ws + (block ? '\\' + block : digits + '\\' + punct));
  }
  if (renderer === 'plaintext') return out.replace(/\r/g, '');
  if (renderer === 'native' || renderer === 'structured' || renderer === 'voice') return out;
  throw new IntegrityError(`unknown renderer ${renderer}; refusing to render`);
}

function answerDigest(answer) {
  return 'sha256:' + crypto.createHash('sha256').update(answer, 'utf8').digest('hex');
}

/** Join the organic answer and any creative deterministically. */
function compose(answer, decision, { renderer = 'markdown' } = {}) {
  const digest = answerDigest(answer);
  const placements = decision && decision.placements;
  if (!placements || !placements.length) {
    return { text: answer, organicAnswerDigest: digest, headers: {}, uapPlacements: [] };
  }

  const blocks = [];
  const manifest = [];
  for (const p of placements) {
    const creative = p.creative || {};
    const content = creative.content || {};
    const disclosure = creative.disclosure || {};
    if (!content.headline) continue;      // nothing to render; a bare separator is worse than no fill

    const brand = escapeText(content.brand_name || disclosure.advertiser_name || '', renderer);
    const headline = escapeText(content.headline || '', renderer);
    const body = escapeText(content.body || '', renderer);

    const lines = [SEPARATOR, brand ? `${brand} — ${headline}` : headline];
    if (body) lines.push(body);
    for (const action of content.actions || []) {
      const url = action.url || '';
      if (!url.startsWith('https://')) throw new IntegrityError(`action URL must be https: ${url}`);
      lines.push(`[${escapeText(action.label || '', renderer)}] ${url}`);
    }
    blocks.push(lines.join('\n'));
    manifest.push({
      placement_id: p.placement_id,
      creative_digest: creative.content_digest,
      advertiser: disclosure.advertiser_name,
      disclosure: disclosure.label || 'Sponsored',
      click_id: p.click_id,
    });
  }

  if (!blocks.length) return { text: answer, organicAnswerDigest: digest, headers: {}, uapPlacements: [] };
  return {
    text: answer + '\n\n' + blocks.join('\n\n'),
    organicAnswerDigest: digest,
    headers: { 'X-UAP-Sponsored': '1' },
    uapPlacements: manifest,
  };
}

/** Recover the organic answer. Call before re-feeding into a model. */
function stripAdBlock(composed) {
  return composed.split('\n\n' + SEPARATOR)[0];
}

/** Prove the composer concatenated and nothing else. */
function verifyComposition(composedText, answer, decision, { renderer = 'markdown' } = {}) {
  const expected = compose(answer, decision, { renderer }).text;
  if (composedText === expected) return [true, 'composition is exact'];
  if (stripAdBlock(composedText) !== answer) return [false, 'the answer shown differs from the answer committed to'];
  return [false, 'the ad block differs from the decision that was issued'];
}

/** Check the answer shown matches what was committed before selection. */
function verifyAnswerCommitment(composedText, committedDigest) {
  const actual = answerDigest(stripAdBlock(composedText));
  if (actual === committedDigest) return [true, 'answer matches the pre-selection commitment'];
  return [false, `answer digest ${actual} does not match commitment ${committedDigest}`];
}

module.exports = {
  compose, escapeText, answerDigest, stripAdBlock,
  verifyComposition, verifyAnswerCommitment, IntegrityError, SEPARATOR,
};
