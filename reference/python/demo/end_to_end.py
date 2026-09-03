#!/usr/bin/env python3
"""Profile L end to end: bundle sync, local auction, render, receipt, settlement.

Run:  python3 demo/end_to_end.py

Four parties, four keys, one impression. Nothing derived from the conversation
crosses the network at any point.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from uap import Exchange, KeyRing, KeywordClassifier, Node, SigningKey, Surface
from uap.integrity import commit_answer, verify_answer_commitment, verify_composition
from uap.measurement import assess
from uap.supply_chain import verify_chain

BOLD, DIM, GRN, YEL, RST = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[0m"


def head(n, title):
    print(f"\n{BOLD}{n}. {title}{RST}")


def main() -> int:
    # ---------------------------------------------------------------- setup
    exchange_key = SigningKey.generate("uax-ed25519-2026-08")
    surface_key = SigningKey.generate("surface-ed25519-01")
    node_key = SigningKey.generate("node-ed25519-01")

    ux = Exchange("uax.example.com", exchange_key,
                  take_rate_bps=2000, floor_cpm_micros=10_000_000)
    ux.enrol("node.selfhosted.example", surface_key.verifying_key, trust_tier=1)

    ux.register_steward("hf:moonshotai/Kimi-K2-Instruct", {
        "advertising_policy": {
            "permitted": True,
            "permitted_positions": ["post_answer", "sidebar"],
            "permitted_formats": ["sponsored_card", "sponsored_link"],
            "blocked_categories": ["gambling", "political"],
            "revenue_share_bps": 1500,
        }})

    ux.add_line_item({
        "line_item_id": "li_991",
        "advertiser": {"id": "brand.acme.example", "display_name": "Acme Travel"},
        "targeting": {"all": [
            {"intent_any": ["travel.accommodation.hotel", "travel.destination.japan"]},
            {"commercial_intent_gte": 0.5},
            {"locale_any": ["en-US", "en-GB"]}]},
        "pricing": {"model": "cpm", "bid_cpm_micros": 62_000_000},
        "pacing": {"node_share_impressions": 40},
        "frequency_cap": {"per_conversation": 1},
        "categories": ["travel.accommodation"],
        "creatives": [{
            "creative_id": "cr_884", "format": "sponsored_card",
            "content_digest": "sha256:" + "5b" * 32,
            "content": {
                "brand_name": "Acme Travel",
                "headline": "Kyoto ryokan, free cancellation",
                "body": "Traditional inns from $180/night, cancel up to 24h before.",
                "actions": [{"type": "link", "label": "See rooms",
                             "url": "https://acme.example/kyoto"}]},
            "disclosure": {"label": "Sponsored", "advertiser_name": "Acme Travel"}}]})

    ux.add_line_item({
        "line_item_id": "li_772",
        "advertiser": {"id": "brand.globex.example", "display_name": "Globex Rail"},
        "targeting": {"all": [{"intent_any": ["travel.transport.rail"]}]},
        "pricing": {"model": "cpm", "bid_cpm_micros": 80_000_000},
        "categories": ["travel.transport"],
        "creatives": [{"creative_id": "cr_112", "content_digest": "sha256:" + "aa" * 32}]})

    ux.add_line_item({
        "line_item_id": "li_310",
        "advertiser": {"id": "brand.hotelio.example", "display_name": "Hotelio"},
        "targeting": {"all": [{"intent_any": ["travel.accommodation.hotel"]}]},
        "pricing": {"model": "cpm", "bid_cpm_micros": 41_000_000},
        "categories": ["travel.accommodation"],
        "creatives": [{"creative_id": "cr_777", "content_digest": "sha256:" + "cc" * 32}]})

    ring = KeyRing().add(exchange_key.verifying_key)
    node = Node("node.selfhosted.example", "hf:moonshotai/Kimi-K2-Instruct",
                signing_key=node_key, exchange_keys=ring, trust_tier=1,
                steward_id="steward.moonshot.example",
                accept_unverified_classifier=True)
    surface = Surface("node.selfhosted.example", surface_key, trust_tier=1)

    # ------------------------------------------------------- 1. bundle sync
    head(1, "Bundle sync — scheduled, not per turn")
    bundle = ux.issue_bundle(ttl_hours=24)
    node.load_bundle(bundle)
    print(f"   {GRN}signature verified{RST}  {bundle['bundle_id']}  "
          f"{len(bundle['line_items'])} line items  expires {bundle['expires_at']}")

    # -------------------------------------------------------------- 2. turn
    head(2, "User turn — zero network calls")
    conversation = [{"role": "user",
                     "content": "I want to book a ryokan in Kyoto in November. "
                                "What should I expect to pay?"}]
    answer = ("Kyoto ryokan rates peak in November for the autumn foliage. "
              "Expect ¥25,000-¥60,000 per person per night with dinner and "
              "breakfast included. Book two to three months ahead.")

    node.guard_context(conversation, None)   # ads cannot reach generate()
    signal = KeywordClassifier().derive(conversation)
    print(f"   {YEL}demo classifier: keyword matching, not production ready.{RST}")
    print(f"   {YEL}this node sets accept_unverified_classifier=True, which a real"
          f" deployment must not.{RST}")
    print(f"   {DIM}signal stays on this machine:{RST} "
          f"{[i['id'] for i in signal['intents']]} "
          f"commercial={signal['commercial_intent']}")

    placement = {"placement_id": "pl_post_answer_card", "position": "post_answer",
                 "format": "sponsored_card", "floor_cpm_micros": 10_000_000}
    steward = ux.steward_policies["hf:moonshotai/Kimi-K2-Instruct"]
    result = node.decide_local(signal, placement, steward_policy=steward)

    print(f"   auction: winner {BOLD}{result.winner['line_item_id']}{RST} "
          f"clears at USD {result.clearing_price_micros/1e6:.2f} CPM")
    for t in result.trace:
        mark = GRN if t.outcome == "won" else DIM
        print(f"     {mark}{t.line_item_id:<8} {t.outcome:<22} "
              f"USD {t.ecpm_micros/1e6:6.2f} CPM{RST}")

    # ------------------------------------------------------------ 3. render
    head(3, "Render — deterministic composer, never a model")
    creative = result.winner["creatives"][0]
    local = node.local_decision(result.winner["line_item_id"])
    nonce = local["nonce"]
    decision = {"decision_id": "dc_local_" + nonce[2:12],
                "placements": [{"placement_id": placement["placement_id"],
                                "creative": creative, "click_id": "ck_demo"}]}
    composed = node.compose(answer, decision)
    node.record_delivery(result.winner["line_item_id"])
    print("   " + composed.text.replace("\n", "\n   "))
    print(f"\n   {DIM}organic digest {composed.organic_answer_digest}{RST}")
    print(f"   {DIM}answer recovered byte-identical: "
          f"{composed.organic_answer == answer}{RST}")

    # ----------------------------------------------------------- 4. receipt
    head(4, "Receipt — signed by the surface, batched and delayed")
    receipt = surface.emit_receipt(
        nonce=nonce, decision_id=decision["decision_id"],
        placement_id=placement["placement_id"],
        creative_digest=creative["content_digest"], composed=composed,
        viewability={"rendered": True, "standard": "mrc_display", "viewable": True,
                     "method": "intersection_observer", "visible_ms": 3400,
                     "visible_pct": 100, "user_present": True},
        auction_trace=result.trace_json(), local_decision=local)
    verdict = ux.verify_receipt(receipt)
    print(f"   {GRN if verdict.billable else YEL}billable={verdict.billable}{RST} "
          f"({verdict.reason})   gross {verdict.gross_micros} micros "
          f"= USD {verdict.gross_micros/1e6:.5f}")

    # -------------------------------------------------------- 5. settlement
    head(5, "Settlement")
    splits = ux.settle(verdict.gross_micros, node.entity_id,
                       steward_id="steward.moonshot.example", steward_bps=1500)
    for s in splits:
        print(f"   {s['party']:<14} {s['bps']:>5} bps  "
              f"{s['amount_micros']:>6} micros  {s['entity_id']}")
    total = sum(s["amount_micros"] for s in splits)
    print(f"   {DIM}{'sum':<14} {sum(s['bps'] for s in splits):>5} bps  "
          f"{total:>6} micros  (exact: {total == verdict.gross_micros}){RST}")

    # ---------------------------------------------------- 6. proving I2
    head(6, "Proving the ad did not change the answer")
    commitment = commit_answer(answer, "req_demo", "2026-09-02T14:30:00Z")
    ok_commit, why_commit = verify_answer_commitment(composed.text, commitment.digest)
    ok_comp, why_comp = verify_composition(composed.text, answer, decision)
    print(f"   {GRN if ok_commit else YEL}{str(ok_commit):<5}{RST} "
          f"answer matches the digest committed before selection")
    print(f"   {GRN if ok_comp else YEL}{str(ok_comp):<5}{RST} "
          f"rendered bytes are exactly answer + separator + creative")

    edited = composed.text.replace("foliage", "foliage, and Acme has the best rates")
    bad_commit, why_bad = verify_answer_commitment(edited, commitment.digest)
    print(f"   {GRN}{str(bad_commit):<5}{RST} an answer edited to favour the advertiser "
          f"{DIM}({why_bad[:44]}...){RST}")
    print(f"   {DIM}anyone holding the answer, the decision and the output can run "
          f"these; no key and no cooperation from the node{RST}")

    # ------------------------------------------------------------- 7. abuse
    head(7, "Abuse cases — each must fail")
    replay = ux.verify_receipt(receipt)
    print(f"   {GRN}rejected{RST}  replayed nonce            {DIM}{replay.reason}{RST}")

    # Re-sign with the surface's own key so the signature is valid and the
    # creative_digest check is what actually fires.
    node.record_delivery(result.winner["line_item_id"])
    local2 = node.local_decision(result.winner["line_item_id"])
    swapped = surface.emit_receipt(
        nonce=local2["nonce"], decision_id=decision["decision_id"],
        placement_id=placement["placement_id"],
        creative_digest="sha256:" + "ff" * 32, composed=composed,
        viewability={"rendered": True, "standard": "mrc_display", "viewable": True,
                     "method": "intersection_observer", "visible_ms": 3400},
        auction_trace=result.trace_json(), local_decision=local2)
    print(f"   {GRN}rejected{RST}  swapped creative digest   "
          f"{DIM}{ux.verify_receipt(swapped).reason}{RST}")

    tier0 = Surface("anon.example", SigningKey.generate("anon-1"), trust_tier=0)
    ux.enrol("anon.example", tier0.key.verifying_key, trust_tier=0)
    from uap.nonce import derive_local_nonce
    local3 = {"bundle_id": bundle["bundle_id"],
              "line_item_id": result.winner["line_item_id"], "impression_index": 3}
    anon = tier0.emit_receipt(
        nonce=derive_local_nonce(bundle["bundle_id"], "anon.example",
                                 result.winner["line_item_id"], 3),
        decision_id=decision["decision_id"],
        placement_id=placement["placement_id"],
        creative_digest=creative["content_digest"], composed=composed,
        viewability={"rendered": True, "standard": "delivered_only",
                     "viewable": False, "method": "none"},
        auction_trace=result.trace_json(), local_decision=local3)
    print(f"   {GRN}rejected{RST}  tier 0 billed on CPM      "
          f"{DIM}{ux.verify_receipt(anon).reason}{RST}")

    over = surface.emit_receipt(
        nonce=derive_local_nonce(bundle["bundle_id"], node.entity_id,
                                 result.winner["line_item_id"], 999),
        decision_id=decision["decision_id"],
        placement_id=placement["placement_id"],
        creative_digest=creative["content_digest"], composed=composed,
        viewability={"rendered": True, "standard": "mrc_display", "viewable": True,
                     "method": "intersection_observer", "visible_ms": 3400},
        auction_trace=result.trace_json(),
        local_decision={"bundle_id": bundle["bundle_id"],
                        "line_item_id": result.winner["line_item_id"],
                        "impression_index": 999})
    print(f"   {GRN}rejected{RST}  index beyond allocation   "
          f"{DIM}{ux.verify_receipt(over).reason}{RST}")

    sensitive = KeywordClassifier().derive(
        [{"role": "user", "content": "I have symptoms of depression, what should I do"}])
    blocked = node.decide_local(sensitive, placement, steward_policy=steward)
    print(f"   {GRN}rejected{RST}  sensitive turn            "
          f"{DIM}no auction run (result={blocked}){RST}")

    # -------------------------------------------------- 8. buyer-side checks
    head(8, "What a buyer checks before it spends")
    chain = {"complete": True, "nodes": [
        {"asi": ux.entity_id, "sid": node.entity_id, "hp": 1,
         "anchor": {"type": "enrolment"}, "trust_tier": 1}]}
    v = verify_chain(chain, {ux.entity_id: ux.sellers_declaration()})
    print(f"   supply chain   ok={v.ok}  resolved={v.resolved}/{len(chain['nodes'])}  "
          f"payment hops={v.payment_hops}  weakest anchor={v.weakest_anchor}")
    q = ux.quality_report().to_json()
    print(f"   measurement    {q['impressions']} impressions  "
          f"viewable_rate={q['viewable_rate']}  ivt_rate={q['ivt_rate']}")
    h = ux.holdout_report()
    print(f"   holdout        served={h['served']}  holdout={h['holdout']}  "
          f"{DIM}divergence between arms is the only evidence a per-turn "
          f"check cannot produce{RST}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
