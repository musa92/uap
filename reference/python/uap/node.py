"""Serving node and surface (SPEC.md §2, §8.2, §9).

The node runs the model and, in Profile L, the auction. The surface renders to a
human and signs the receipt. They are separate classes because they are separate
trust domains: the node has both the means and the motive to inflate its own
impression counts, so it is not permitted to sign the billable artefact.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from . import auction, integrity
from .nonce import derive_local_nonce
from .crypto import SigningKey, sign_object, verify_object, KeyRing

__all__ = ["Node", "Surface", "ContextClassifier"]


def _iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ContextClassifier:
    """Contract for deriving a ContextSignal locally (SPEC.md §6.2).

    Subclass this. The contract is that derivation runs on the node, its output
    reduces to the published intent taxonomy, and nothing it sees is
    transmitted.

    `sensitive_category` is three-valued on purpose. True suppresses the turn,
    False permits it, and None means the classifier could not decide. The
    normative rule in source/taxonomy/sensitive-1.0.json is that a category the
    classifier cannot confidently exclude is treated as sensitive, so None
    suppresses exactly as True does. A two-valued flag makes that rule
    impossible to honour, because "no keyword matched" and "confidently not
    sensitive" become the same value.

    `production_ready` gates use. A classifier that has not been evaluated
    against the sensitive taxonomy must not silently decide whether a health or
    financial-distress turn carries advertising.
    """

    production_ready = False
    classifier_id = "uap.classifier.abstract"

    def derive(self, conversation, *, locale="en-US", surface_hint="chat") -> dict:
        raise NotImplementedError


class KeywordClassifier(ContextClassifier):
    """Demonstration classifier. Not fit for production and says so.

    Keyword matching detects some sensitive categories and excludes none with
    any confidence. It returns None whenever it has no evidence either way, and
    the node treats None exactly as it treats True.

    The False it does return, on a recognised commercial intent with no
    sensitive marker, is a weak exclusion offered only so the flow can be
    demonstrated end to end. `production_ready` is False, so a node refuses to
    act on it unless the operator passes accept_unverified_classifier=True. Do
    not ship this.
    """

    production_ready = False
    classifier_id = "uap.classifier.keyword_demo"

    INTENTS = {
        "travel.accommodation.hotel": ("hotel", "ryokan", "inn", "stay"),
        "travel.destination.japan": ("kyoto", "tokyo", "japan", "osaka"),
        "travel.transport.rail": ("train", "rail", "shinkansen"),
        "software.developer_tools.observability": ("tracing", "metrics", "observability"),
    }
    COMMERCIAL = ("book", "buy", "price", "pay", "cheap", "deal",
                  "cost", "reserve", "rate", "budget")
    SENSITIVE = ("symptom", "diagnos", "depress", "suicide", "pregnan", "therapy",
                 "bankrupt", "evict", "foreclos", "debt", "arrest", "lawsuit",
                 "deport", "asylum", "immigration", "abortion", "contracept")

    def derive(self, conversation, *, locale="en-US", surface_hint="chat") -> dict:
        text = " ".join(
            m.get("content", "") if isinstance(m, dict) else str(m)
            for m in conversation).lower()

        intents = []
        for intent_id, words in self.INTENTS.items():
            hits = sum(w in text for w in words)
            if hits:
                intents.append({"id": intent_id,
                                "confidence": round(min(0.35 + 0.2 * hits, 0.95), 2)})
        intents.sort(key=lambda i: -i["confidence"])
        commercial = round(min(0.2 + 0.18 * sum(w in text for w in self.COMMERCIAL), 0.95), 2)

        if any(w in text for w in self.SENSITIVE):
            sensitive = True   # positive detection
        elif intents:
            # A recognised commercial intent with no sensitive marker is a weak
            # exclusion. It is nowhere near sufficient on its own, which is why
            # production_ready is False and a node must opt in explicitly before
            # this value is honoured at all.
            sensitive = False
        else:
            sensitive = None   # no evidence either way; the node fails closed

        return {
            "signal_version": "uap.intent/1.0",
            "signal_class": "local_only",
            "intents": intents[:5],
            "commercial_intent": commercial,
            "locale": locale,
            "surface_hint": surface_hint,
            "safety": {"sensitive_category": sensitive, "brand_risk": "low",
                       "classifier_id": self.classifier_id,
                       "production_ready": self.production_ready},
        }


class Node:
    """A serving node. Mirrors SPEC.md Appendix B."""

    def __init__(self, entity_id: str, model_id: str, *, signing_key: SigningKey,
                 exchange_keys: KeyRing, profiles=None, trust_tier: int = 1,
                 steward_id: str | None = None,
                 accept_unverified_classifier: bool = False):
        self.entity_id = entity_id
        self.model_id = model_id
        self.key = signing_key
        self.exchange_keys = exchange_keys
        self.profiles = profiles or ["uap.core", "uap.decision.local", "uap.measure"]
        self.trust_tier = trust_tier
        self.steward_id = steward_id
        self.accept_unverified_classifier = accept_unverified_classifier
        self.bundle: dict | None = None
        self._frequency: dict[str, int] = {}
        self._pacing: dict[str, int] = {}

    # -- Profile L ---------------------------------------------------------
    def load_bundle(self, bundle: dict) -> None:
        """Verify and cache a signed CampaignBundle. Refuses an expired bundle."""
        ok, reason = verify_object(bundle, self.exchange_keys, "bundle")
        if not ok:
            raise ValueError(f"bundle signature invalid: {reason}")
        if bundle.get("expires_at", "") < _iso():
            raise ValueError("UAP_BUNDLE_EXPIRED")
        self.bundle = bundle

    def decide_local(self, signal: dict, placement: dict, *, steward_policy=None):
        """Run the auction locally. Zero network calls.

        Returns None when the turn is sensitive or nothing is eligible. A
        no-fill renders nothing; there are no house ads and no default creative.
        """
        if self.bundle is None:
            return None
        if not self.may_monetise(signal):
            return None
        return auction.run(
            self.bundle.get("line_items") or [], signal, placement,
            steward_policy=steward_policy,
            floor_cpm_micros=self.bundle.get("floor_cpm_micros", 0),
            frequency_state=self._frequency, pacing_state=self._pacing,
        )

    def may_monetise(self, signal: dict) -> bool:
        """Fail closed. Only an explicit False permits a turn to carry advertising.

        None means the classifier could not exclude a sensitive category, which
        source/taxonomy/sensitive-1.0.json requires be treated as sensitive. A
        missing safety block is treated the same way.
        """
        safety = signal.get("safety")
        if not isinstance(safety, dict):
            return False
        if safety.get("sensitive_category") is not False:
            return False
        if not safety.get("production_ready", False) and not self.accept_unverified_classifier:
            return False
        return True

    def record_delivery(self, line_item_id: str) -> None:
        self._frequency[line_item_id] = self._frequency.get(line_item_id, 0) + 1
        self._pacing[line_item_id] = self._pacing.get(line_item_id, 0) + 1

    def local_decision(self, line_item_id: str) -> dict:
        """Claim the next impression slot for a line item.

        Returns the block the receipt carries so the exchange can reconstruct
        the nonce. Call once per rendered impression, before record_delivery.
        """
        if self.bundle is None:
            raise ValueError("no bundle loaded")
        index = self._pacing.get(line_item_id, 0)
        bundle_id = self.bundle["bundle_id"]
        return {
            "bundle_id": bundle_id,
            "line_item_id": line_item_id,
            "impression_index": index,
            "nonce": derive_local_nonce(bundle_id, self.entity_id, line_item_id, index),
        }

    # -- composition -------------------------------------------------------
    def compose(self, answer: str, decision: dict | None, *, renderer="markdown"):
        return integrity.compose(answer, decision, renderer=renderer)

    def guard_context(self, messages, decision) -> None:
        """Call immediately before generate(). Fails closed on §7.2 breach."""
        integrity.assert_creative_absent(messages, decision)

    def ad_request(self, signal: dict, placements: list, *, answer: str,
                   supply_chain=None) -> dict:
        """Build a hosted-profile AdRequest.

        `answer` is required, and only its digest is sent. Committing to the
        answer before the exchange selects a winner is what makes the ordering
        provable rather than asserted, so there is deliberately no way to build
        a request without having generated the answer first.
        """
        return {
            "id": secrets.token_hex(12),
            "integrity": {"organic_answer_digest": integrity.answer_digest(answer)},
            "uap_version": "2026-09-02",
            "supply": {"entity_id": self.entity_id, "trust_tier": self.trust_tier,
                       "model": {"id": self.model_id, "steward_id": self.steward_id}},
            "placements": placements,
            "context": signal,
            "auction": {"mechanism": "uap.auction.second_price",
                        "currency": "USD", "timeout_ms": 80},
            "supply_chain": supply_chain,
            "test": False,
        }


class Surface:
    """The component with a screen and a human in front of it.

    Signs the ImpressionReceipt. Distinct from the node at trust tier 1 and
    above, because a node signing its own impression counts is an unverified
    claim, not a measurement.
    """

    def __init__(self, entity_id: str, signing_key: SigningKey, *, trust_tier: int = 1):
        self.entity_id = entity_id
        self.key = signing_key
        self.trust_tier = trust_tier

    def emit_receipt(self, *, nonce: str, decision_id: str, placement_id: str,
                     creative_digest: str, composed, viewability: dict,
                     auction_trace=None, local_decision=None) -> dict:
        receipt = {
            "receipt_id": "rc_" + secrets.token_hex(10),
            "decision_id": decision_id,
            "nonce": nonce,
            "placement_id": placement_id,
            "creative_digest": creative_digest,
            "rendered_at": _iso(),
            "viewability": viewability,
            "integrity": {
                "organic_answer_digest": composed.organic_answer_digest,
                "no_decode_influence": True,
                "ad_excluded_from_context": True,
                "disclosure_rendered": integrity.SEPARATOR in composed.text,
            },
            "auction_trace": auction_trace,
            "trust_tier": self.trust_tier,
        }
        if local_decision is not None:
            receipt["local_decision"] = {
                k: v for k, v in local_decision.items() if k != "nonce"}
        return sign_object(receipt, self.key, "receipt", created=_iso())
