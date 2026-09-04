"""The integrity boundary (SPEC.md §7, invariant I2).

Ads are data. This module is the only place creative text becomes output, and
it is deliberately not a template engine: it escapes, concatenates, and digests.

The composer is a pure function. It MUST NOT be a language model, and nothing
here may be given access to a model handle.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

__all__ = ["compose", "ComposedTurn", "answer_digest", "strip_ad_block",
           "assert_creative_absent", "verify_composition", "verify_answer_commitment",
           "AnswerCommitment", "IntegrityError", "SEPARATOR"]

SEPARATOR = "--- Sponsored ---"

# Markdown control characters, escaped rather than interpreted: creative text is
# attacker-controlled input arriving over the network.
#
# Escaped everywhere, because these change meaning mid-line.
_MD_INLINE = re.compile(r"([\\`*_\[\]<>|~])")
# Escaped only at the start of a line, where they open a block. Escaping "." or
# "-" everywhere turns "cancel up to 24 hours before arrival." into
# "arrival\." in the rendered ad, which reads as broken copy to a user. The
# safety property is unchanged: nothing here is ever interpreted as markup.
_MD_LEADING = re.compile(r"^(\s*)(?:([#+\-])|(\d+)([.)]))", re.M)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class IntegrityError(RuntimeError):
    """Raised when an operation would breach the integrity boundary."""


def escape(text: str, renderer: str) -> str:
    """Render creative text as an inert text node for the target renderer."""
    text = _CONTROL.sub("", str(text))
    if renderer == "markdown":
        text = _MD_INLINE.sub(r"\\\1", text)
        # For an ordered marker the punctuation is what opens the list, so
        # "1." becomes "1\." and not "\1." which would leave it a list.
        return _MD_LEADING.sub(
            lambda m: m.group(1) + ("\\" + m.group(2) if m.group(2)
                                    else m.group(3) + "\\" + m.group(4)), text)
    if renderer == "plaintext":
        return text.replace("\r", "")
    if renderer in ("native", "structured", "voice"):
        # The surface renders from structured fields with its own chrome; no
        # in-band escaping applies because there is no markup to escape into.
        return text
    raise IntegrityError(f"unknown renderer {renderer!r}; refusing to render")


def answer_digest(answer: str) -> str:
    """SHA-256 over the exact answer bytes, excluding ad block and separator."""
    return "sha256:" + hashlib.sha256(answer.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ComposedTurn:
    text: str
    organic_answer_digest: str
    headers: dict
    uap_placements: list

    @property
    def organic_answer(self) -> str:
        return strip_ad_block(self.text)


def compose(answer: str, decision: dict | None, *, renderer: str = "markdown") -> ComposedTurn:
    """Join the organic answer and any creative deterministically.

    The answer bytes above the separator are byte-identical to model output.
    Returns the composed text, the digest committed in the receipt, and the
    machine-readable placement list downstream agents use to strip or attribute.
    """
    digest = answer_digest(answer)
    placements = decision.get("placements") if decision else None
    if not placements:
        return ComposedTurn(answer, digest, {}, [])

    blocks, manifest = [], []
    for p in placements:
        creative = p.get("creative") or {}
        content = creative.get("content") or {}
        disclosure = creative.get("disclosure") or {}
        if not content.get("headline"):
            # A creative with no headline has nothing to render. Emitting a bare
            # disclosure separator would show the user a sponsored block with no
            # sponsor, which is worse than a no-fill.
            continue
        brand = escape(content.get("brand_name") or disclosure.get("advertiser_name") or "", renderer)
        headline = escape(content.get("headline") or "", renderer)
        body = escape(content.get("body") or "", renderer)

        lines = [SEPARATOR, f"{brand} — {headline}" if brand else headline]
        if body:
            lines.append(body)
        for action in (content.get("actions") or []):
            label = escape(action.get("label") or "", renderer)
            url = action.get("url") or ""
            if not url.startswith("https://"):
                raise IntegrityError(f"action URL must be https: {url!r}")
            lines.append(f"[{label}] {url}")
        blocks.append("\n".join(lines))

        manifest.append({
            "placement_id": p.get("placement_id"),
            "creative_digest": creative.get("content_digest"),
            "advertiser": (creative.get("disclosure") or {}).get("advertiser_name"),
            "disclosure": disclosure.get("label", "Sponsored"),
            "click_id": p.get("click_id"),
        })

    if not blocks:
        return ComposedTurn(answer, digest, {}, [])
    text = answer + "\n\n" + "\n\n".join(blocks)
    return ComposedTurn(text, digest, {"X-UAP-Sponsored": "1"}, manifest)


def strip_ad_block(composed: str) -> str:
    """Recover the organic answer. Called before any re-feed into the model."""
    return composed.split("\n\n" + SEPARATOR)[0]


def assert_creative_absent(messages, decision: dict | None) -> None:
    """Fail closed if creative text reached the model context (SPEC.md §7.2).

    Called immediately before generate(). A system that interpolates purchased
    text into a prompt has granted write access to its own reasoning.
    """
    if not decision:
        return
    haystack = "\n".join(
        m.get("content", "") if isinstance(m, dict) else str(m) for m in messages)
    for p in decision.get("placements") or []:
        content = (p.get("creative") or {}).get("content") or {}
        for field in ("headline", "body", "brand_name"):
            needle = content.get(field)
            if needle and len(needle) > 8 and needle in haystack:
                raise IntegrityError(
                    f"creative field {field!r} present in model context; "
                    f"this breaches SPEC.md §7.2 and voids the impression")


# ---------------------------------------------------------------------------
# Proving the ad did not change the answer
# ---------------------------------------------------------------------------
#
# A digest in the receipt proves nothing on its own: the node computes it after
# the fact and can compute it over whatever it likes. Three mechanisms turn the
# claim into something checkable, and they are honest about what each one can
# and cannot establish.
#
#   1. Ordering.     The node commits to the answer digest inside the AdRequest,
#                    before the exchange runs the auction. The exchange holds the
#                    commitment before a winner exists, so an answer matching it
#                    demonstrably did not depend on the outcome. This is a real
#                    proof and it applies to hosted decisioning.
#
#   2. Composition.  compose() is deterministic and non-generative. Given the
#                    answer and the decision, anyone can recompute the exact
#                    bytes and compare. Byte equality proves the composer
#                    concatenated and did not rewrite.
#
#   3. Holdout.      The exchange marks a fraction of requests as holdout: the
#                    node runs the identical path but no ad is served, and still
#                    reports the answer digest. Systematic divergence between
#                    served and holdout answers is evidence of influence that no
#                    per-turn check can produce.
#
# Local decisioning has no round trip, so mechanism 1 is unavailable and the
# guarantee degrades to 2 and 3 plus, at trust tier 2, an attestation covering
# the code path that enforces ordering. SPEC.md §9.3 prices the difference.


@dataclass(frozen=True)
class AnswerCommitment:
    """A node's commitment to an answer, made before selection runs."""

    digest: str
    committed_at: str
    request_id: str

    def to_json(self) -> dict:
        return {"organic_answer_digest": self.digest,
                "committed_at": self.committed_at,
                "request_id": self.request_id}


def commit_answer(answer: str, request_id: str, committed_at: str) -> AnswerCommitment:
    """Commit to a generated answer. Call before building the AdRequest."""
    return AnswerCommitment(answer_digest(answer), committed_at, request_id)


def verify_composition(composed_text: str, answer: str, decision: dict | None,
                       *, renderer: str = "markdown") -> tuple[bool, str]:
    """Prove the composer concatenated and nothing else.

    Recomputes the composition from the answer and the decision and compares
    bytes. compose() is deterministic and never calls a model, so an exact match
    establishes that the rendered output is the organic answer followed by the
    disclosed creative, with nothing interleaved, rewritten, or removed.

    Anyone holding the answer, the decision and the rendered output can run this.
    It needs no key and no cooperation from the node.
    """
    expected = compose(answer, decision, renderer=renderer).text
    if composed_text == expected:
        return True, "composition is exact"
    if strip_ad_block(composed_text) != answer:
        return False, "the answer shown differs from the answer committed to"
    return False, "the ad block differs from the decision that was issued"


def verify_answer_commitment(composed_text: str, committed_digest: str) -> tuple[bool, str]:
    """Check the answer shown matches what was committed before selection.

    Strips the ad block from the rendered output and compares the digest. A
    mismatch means the answer changed between commitment and render, which is
    the exact failure the integrity boundary exists to make detectable.
    """
    shown = strip_ad_block(composed_text)
    actual = answer_digest(shown)
    if actual == committed_digest:
        return True, "answer matches the pre-selection commitment"
    return False, f"answer digest {actual} does not match commitment {committed_digest}"
