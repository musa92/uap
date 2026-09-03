"""UAP — Universal Ads Protocol reference implementation.

Minimal Profile L integration (SPEC.md Appendix B):

    from uap import Node, Surface, ContextClassifier

    node = Node("node.example", "hf:moonshotai/Kimi-K2-Instruct",
                signing_key=key, exchange_keys=ring)
    node.load_bundle(bundle)                       # scheduled, not per turn

    answer = model.generate(conversation)          # ads cannot reach this call
    signal = ContextClassifier.derive(conversation)  # stays on this machine
    result = node.decide_local(signal, placement)    # zero network calls
    composed = node.compose(answer, decision)        # deterministic, non-model

Note what is absent: any call taking `conversation` and a network address in the
same expression.
"""
from .version import UAP_VERSION, __version__
from .canonical import canonicalize, serialize
from .crypto import SigningKey, VerifyingKey, KeyRing, sign_object, verify_object
from .integrity import (compose, answer_digest, strip_ad_block, commit_answer,
                        verify_composition, verify_answer_commitment, IntegrityError)
from .measurement import assess, meets_mrc
from .supply_chain import verify_chain
from .node import Node, Surface, ContextClassifier, KeywordClassifier
from .exchange import Exchange
from . import auction, predicate

__all__ = [
    "UAP_VERSION", "__version__",
    "Node", "Surface", "ContextClassifier", "KeywordClassifier", "Exchange",
    "SigningKey", "VerifyingKey", "KeyRing", "sign_object", "verify_object",
    "canonicalize", "serialize",
    "compose", "answer_digest", "strip_ad_block", "commit_answer",
    "verify_composition", "verify_answer_commitment", "IntegrityError",
    "assess", "meets_mrc", "verify_chain",
    "auction", "predicate",
]
