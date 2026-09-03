"""Nonce derivation for local decisioning.

In hosted decisioning the exchange issues a random nonce with the Decision, and
the nonce is unguessable. Profile L has no round trip, so a nonce cannot be
issued. It is derived instead, from inputs the exchange already holds:

    nonce = "n_" + SHA256(tag || bundle_id || entity_id || line_item_id || index)

The exchange recomputes it at receipt time from the `local_decision` block and
rejects any receipt whose nonce does not derive. This is deliberately not a
secret, and the security does not depend on it being one.

What actually bounds a dishonest node:

  the surface signature       the receipt must be signed by an enrolled key
  the spent set               a derived nonce is single use, like an issued one
  the pacing bound            `index` must be below the line item's allocated
                              share, so minting nonces by incrementing the
                              counter runs out at the allocation, not at
                              whatever the node feels like claiming
  trace replay                the reported auction must reproduce against the
                              bundle the exchange signed
  statistical review          delivery, dwell and click distributions across the
                              node's history, which is where fabrication at
                              scale actually shows up

A node can still mint a nonce for an impression it did not render. That is true
of every impression-counting scheme without a trusted client, which is why
SPEC.md §9.3 prices unattested supply below attested supply rather than
pretending the problem is solved.
"""
from __future__ import annotations

import hashlib

__all__ = ["derive_local_nonce", "TAG"]

TAG = b"uap-local-nonce/2026-09-02"


def derive_local_nonce(bundle_id: str, entity_id: str, line_item_id: str, index: int) -> str:
    """Derive the Profile L nonce for one impression.

    `index` is the node's zero-based impression counter for this line item
    within this bundle. It is carried in the receipt so the exchange can
    reconstruct the nonce and check it against the pacing allocation.
    """
    if index < 0:
        raise ValueError("impression index must be non-negative")
    parts = b"\x00".join([
        TAG,
        bundle_id.encode("utf-8"),
        entity_id.encode("utf-8"),
        line_item_id.encode("utf-8"),
        str(index).encode("ascii"),
    ])
    return "n_" + hashlib.sha256(parts).hexdigest()[:32]
