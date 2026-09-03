"""Supply chain verification (IAB SupplyChain, adapted).

A chain a buyer cannot resolve is a chain a buyer discards. These checks are the
ones a supply path optimisation system runs before it will spend: every hop
names a seller that the named system admits to paying, the chain is complete, no
hop repeats, and every hop declares what authorises it to sell.

The UAP-specific check is the anchor. On the open web ads.txt ties a seller to a
domain it controls. Core UAP supply is a self-hosted binary with no domain, so a
hop must instead name the authority vouching for it, and `none` is a permitted
answer that buyers may price accordingly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["ChainVerdict", "verify_chain", "resolve_seller"]

MAX_HOPS = 16


@dataclass
class ChainVerdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    resolved: int = 0
    unresolvable: int = 0
    payment_hops: int = 0
    weakest_anchor: str = "none"

    def to_json(self) -> dict:
        return {"ok": self.ok, "reasons": self.reasons, "resolved": self.resolved,
                "unresolvable": self.unresolvable, "payment_hops": self.payment_hops,
                "weakest_anchor": self.weakest_anchor}


# Ordered weakest to strongest. A chain is only as good as its weakest hop.
ANCHOR_STRENGTH = ["none", "enrolment", "domain", "model_steward", "attestation"]


def resolve_seller(declaration: dict, seller_id: str) -> dict | None:
    """Find a seller in a uap-sellers.json document."""
    for seller in declaration.get("sellers") or []:
        if seller.get("seller_id") == seller_id:
            return seller
    return None


def verify_chain(chain: dict, declarations: dict[str, dict]) -> ChainVerdict:
    """Verify a SupplyChain against the seller declarations available.

    `declarations` maps an advertising system identifier to its parsed
    uap-sellers.json. Hops naming a system not present are counted as
    unresolvable rather than rejected: a verifier legitimately does not hold
    every declaration, and reporting that honestly is more useful to a buyer
    than a false pass or a false fail.
    """
    verdict = ChainVerdict(ok=True)

    if not isinstance(chain, dict):
        return ChainVerdict(False, ["supply chain is missing"])

    nodes = chain.get("nodes") or []
    if not nodes:
        return ChainVerdict(False, ["supply chain has no hops"])
    if len(nodes) > MAX_HOPS:
        verdict.ok = False
        verdict.reasons.append(f"chain has {len(nodes)} hops, exceeds {MAX_HOPS}")

    if not chain.get("complete"):
        verdict.ok = False
        verdict.reasons.append(
            "chain is marked incomplete; a hop between the impression and this "
            "request is undeclared")

    seen = set()
    weakest = len(ANCHOR_STRENGTH) - 1

    for i, hop in enumerate(nodes):
        asi, sid = hop.get("asi"), hop.get("sid")
        where = f"hop {i} ({asi}/{sid})"

        if not asi or not sid:
            verdict.ok = False
            verdict.reasons.append(f"hop {i} is missing asi or sid")
            continue

        key = (asi, sid)
        if key in seen:
            verdict.ok = False
            verdict.reasons.append(f"{where} appears more than once; chain loops")
        seen.add(key)

        if hop.get("hp") == 1:
            verdict.payment_hops += 1

        anchor = (hop.get("anchor") or {}).get("type")
        if anchor not in ANCHOR_STRENGTH:
            verdict.ok = False
            verdict.reasons.append(f"{where} declares no recognised anchor")
        else:
            weakest = min(weakest, ANCHOR_STRENGTH.index(anchor))

        declaration = declarations.get(asi)
        if declaration is None:
            verdict.unresolvable += 1
            continue

        seller = resolve_seller(declaration, sid)
        if seller is None:
            verdict.ok = False
            verdict.reasons.append(
                f"{where} is not listed in the seller declaration for {asi}; "
                f"unauthorized supply")
            continue

        verdict.resolved += 1
        if seller.get("anchor_type") != anchor:
            verdict.ok = False
            verdict.reasons.append(
                f"{where} claims anchor {anchor!r} but {asi} records "
                f"{seller.get('anchor_type')!r}")
        claimed = hop.get("trust_tier")
        recorded = seller.get("trust_tier")
        if claimed is not None and recorded is not None and claimed > recorded:
            verdict.ok = False
            verdict.reasons.append(
                f"{where} asserts trust tier {claimed} but {asi} substantiates "
                f"{recorded}")

    if verdict.payment_hops == 0:
        verdict.ok = False
        verdict.reasons.append("no hop is in the payment flow; nobody would be paid")

    verdict.weakest_anchor = ANCHOR_STRENGTH[weakest]
    return verdict
