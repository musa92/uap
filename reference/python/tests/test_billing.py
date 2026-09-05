"""Invoice disputes, credit notes, make-goods, and ledger reconciliation.

The property that matters here is the one in the settlement module's own
docstring: an exchange that bills for an impression it does not pay out on is
out of balance. Crediting a disputed impression without clawing back the shares
paid on it breaks that, so most of these tests are about the reversal rather
than the dispute.
"""
import pathlib
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

from uap import Exchange, SigningKey
from uap.billing import ADJUDICATION_DAYS, DISPUTE_WINDOW_DAYS, Billing, DisputeError
from uap.settlement import Settlement

GROSS = 60_000_000          # $60 CPM, one thousand impressions, in micros
CPM = 60_000_000


@pytest.fixture
def env():
    ux = Exchange("uax.test", SigningKey.generate("uax"), floor_cpm_micros=10_000_000)
    st = Settlement(ux)
    adv = st.create_account({"entity_id": "brand.acme", "kind": "advertiser", "currency": "USD"})
    node = st.create_account({"entity_id": "node.a", "kind": "serving_node", "currency": "USD"})
    st.verify_account(adv["account_id"], identity="kyb")
    st.verify_account(node["account_id"], identity="kyb", tax_form="w9")
    splits = ux.settle(GROSS, "node.a")
    st.issue_payout(node["account_id"], {"start": "2026-09-01", "end": "2026-09-30"},
                    gross_micros=GROSS, splits=splits)
    inv = st.issue_invoice(adv["account_id"], {"start": "2026-09-01", "end": "2026-09-30"},
                           [{"line_item_id": "li_1", "amount_micros": GROSS,
                             "impressions": 1000, "description": "September"}])
    return {"ux": ux, "st": st, "b": Billing(st), "adv": adv, "node": node,
            "inv": inv, "splits": splits}


def _dispute(n=100, micros=6_000_000, reason="not_delivered"):
    return {"reason_code": reason,
            "lines": [{"line_item_id": "li_1",
                       "receipt_ids": [f"rcpt_{i}" for i in range(n)],
                       "disputed_micros": micros}]}


def _all_fail(_rid):
    return False, "receipt not in the verified set", 60_000


def _all_pass(_rid):
    return True, "verified", 60_000


# -- filing ------------------------------------------------------------------

def test_opening_a_dispute_marks_the_invoice(env):
    d = env["b"].open_dispute(env["inv"]["invoice_id"], _dispute())
    assert d["status"] == "open"
    assert env["inv"]["status"] == "disputed"


def test_a_dispute_must_cite_receipts(env):
    bad = _dispute()
    bad["lines"][0]["receipt_ids"] = []
    with pytest.raises(DisputeError) as e:
        env["b"].open_dispute(env["inv"]["invoice_id"], bad)
    assert e.value.code == "UAP_DISPUTE_NO_RECEIPTS"


def test_cannot_dispute_more_than_the_invoice(env):
    with pytest.raises(DisputeError) as e:
        env["b"].open_dispute(env["inv"]["invoice_id"], _dispute(micros=GROSS * 2))
    assert e.value.code == "UAP_DISPUTE_EXCEEDS_INVOICE"


def test_dispute_window_closes(env):
    late = datetime.now(timezone.utc) + timedelta(days=DISPUTE_WINDOW_DAYS + 1)
    with pytest.raises(DisputeError) as e:
        env["b"].open_dispute(env["inv"]["invoice_id"], _dispute(), now=late)
    assert e.value.code == "UAP_DISPUTE_WINDOW_CLOSED"


def test_the_same_impressions_cannot_be_credited_twice(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute(micros=GROSS))
    b.adjudicate(d["dispute_id"], _all_fail)
    b.resolve(d["dispute_id"])
    # The invoice is now fully credited; nothing is left to dispute.
    with pytest.raises(DisputeError) as e:
        b.open_dispute(env["inv"]["invoice_id"], _dispute(micros=GROSS))
    assert e.value.code == "UAP_DISPUTE_EXCEEDS_INVOICE"


# -- adjudication ------------------------------------------------------------

def test_receipts_that_still_verify_defeat_the_dispute(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute())
    out = b.adjudicate(d["dispute_id"], _all_pass)
    assert out["status"] == "rejected"
    assert out["adjudication"]["upheld_micros"] == 0
    assert env["inv"]["status"] == "issued"     # released, payable stands


def test_receipts_that_fail_reverification_uphold_it(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute())
    out = b.adjudicate(d["dispute_id"], _all_fail)
    assert out["status"] == "upheld"
    assert len(out["adjudication"]["per_receipt"]) == 100


def test_mixed_receipts_are_partially_upheld(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute())
    out = b.adjudicate(d["dispute_id"],
                       lambda rid: (int(rid.split("_")[1]) % 2 == 0, "mixed", 60_000))
    assert out["status"] == "partially_upheld"
    a = out["adjudication"]
    assert a["upheld_micros"] > 0 and a["rejected_micros"] > 0


def test_upheld_amount_is_capped_at_what_was_disputed(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute(n=100, micros=1_000_000))
    out = b.adjudicate(d["dispute_id"], _all_fail)   # receipts sum to 6,000,000
    assert out["adjudication"]["upheld_micros"] == 1_000_000


def test_ignoring_a_dispute_resolves_it_for_the_advertiser(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute())
    late = datetime.now(timezone.utc) + timedelta(days=ADJUDICATION_DAYS + 1)
    out = b.adjudicate(d["dispute_id"], _all_pass, now=late)
    assert out["status"] == "expired"
    assert out["adjudication"]["upheld_micros"] == 6_000_000


# -- the ledger --------------------------------------------------------------

def test_a_credit_claws_back_the_payees_shares(env):
    b, st = env["b"], env["st"]
    # Give the node a real pending balance so this exercises deduction rather
    # than the carried-forward path, which its own test covers below.
    node_split = next(s for s in env["splits"] if s["entity_id"] == "node.a")
    st.accounts[env["node"]["account_id"]]["balance"]["pending_micros"] = node_split["amount_micros"]
    node_bal = st.accounts[env["node"]["account_id"]]["balance"]["pending_micros"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute(micros=6_000_000))
    b.adjudicate(d["dispute_id"], _all_fail)
    out = b.resolve(d["dispute_id"], remedy="credit")

    assert out["remedy"]["kind"] == "credit"
    # Every payee gives back its own share of the credit, at the bps it was paid.
    # Derived from the period's split table rather than hardcoded, so the test
    # does not quietly encode one take rate.
    by_entity = {s["entity_id"]: s["bps"] for s in env["splits"]}
    for c in out["remedy"]["clawback"]:
        assert c["amount_micros"] == 6_000_000 * by_entity[c["entity_id"]] // 10000
    node_share = next(c for c in out["remedy"]["clawback"] if c["entity_id"] == "node.a")
    assert node_share["recovered_from"] == "pending_balance"
    after = st.accounts[env["node"]["account_id"]]["balance"]["pending_micros"]
    assert after == node_bal - node_share["amount_micros"]


def test_the_ledger_stays_balanced_after_a_credit(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute(micros=6_000_000))
    b.adjudicate(d["dispute_id"], _all_fail)
    b.resolve(d["dispute_id"], remedy="credit")
    assert b.imbalance() == 0


def test_a_credit_reduces_the_invoice_total(env):
    b, inv = env["b"], env["inv"]
    before = inv["total_micros"]
    d = b.open_dispute(inv["invoice_id"], _dispute(micros=6_000_000))
    b.adjudicate(d["dispute_id"], _all_fail)
    b.resolve(d["dispute_id"], remedy="credit")
    assert inv["total_micros"] == before - 6_000_000
    assert any(a["kind"] == "dispute_credit" for a in inv["adjustments"])


def test_clawback_beyond_the_pending_balance_is_carried_forward(env):
    """A payout already disbursed leaves nothing to deduct from.

    The amount is still owed. Writing it off would be the exchange absorbing a
    loss it did not cause.
    """
    b, st = env["b"], env["st"]
    st.accounts[env["node"]["account_id"]]["balance"]["pending_micros"] = 0
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute(micros=6_000_000))
    b.adjudicate(d["dispute_id"], _all_fail)
    out = b.resolve(d["dispute_id"], remedy="credit")
    node_share = next(c for c in out["remedy"]["clawback"] if c["entity_id"] == "node.a")
    assert node_share["recovered_from"] == "carried_forward"
    bal = st.accounts[env["node"]["account_id"]]["balance"]
    assert bal["owed_back_micros"] == node_share["amount_micros"]
    assert b.imbalance() == 0


# -- make-goods --------------------------------------------------------------

def test_a_make_good_leaves_the_invoice_standing(env):
    b, inv = env["b"], env["inv"]
    before = inv["total_micros"]
    d = b.open_dispute(inv["invoice_id"], _dispute(micros=6_000_000))
    b.adjudicate(d["dispute_id"], _all_fail)
    out = b.resolve(d["dispute_id"], remedy="make_good", cpm_micros=CPM)
    assert inv["total_micros"] == before
    # 6,000,000 micros at a $60 CPM is a hundred impressions.
    assert out["remedy"]["make_good"]["impressions"] == 100
    assert b.imbalance() == 0        # nothing credited, so nothing to claw back


def test_make_good_delivery_is_tracked(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute(micros=6_000_000))
    b.adjudicate(d["dispute_id"], _all_fail)
    b.resolve(d["dispute_id"], remedy="make_good", cpm_micros=CPM)
    mg_id = next(iter(b.make_goods))
    b.deliver_make_good(mg_id, 60)
    b.deliver_make_good(mg_id, 60)      # over-delivery does not overshoot
    assert b.make_goods[mg_id]["delivered"] == 100


def test_a_make_good_needs_a_price_to_be_sized(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute(micros=6_000_000))
    b.adjudicate(d["dispute_id"], _all_fail)
    with pytest.raises(DisputeError) as e:
        b.resolve(d["dispute_id"], remedy="make_good")
    assert e.value.code == "UAP_MAKE_GOOD_NEEDS_PRICE"


# -- state machine -----------------------------------------------------------

def test_a_dispute_resolves_once(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute(micros=6_000_000))
    b.adjudicate(d["dispute_id"], _all_fail)
    b.resolve(d["dispute_id"])
    with pytest.raises(DisputeError) as e:
        b.resolve(d["dispute_id"])
    assert e.value.code == "UAP_DISPUTE_ALREADY_RESOLVED"


def test_withdrawing_releases_the_invoice(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute())
    b.withdraw(d["dispute_id"])
    assert env["inv"]["status"] == "issued"


def test_an_unadjudicated_dispute_cannot_be_resolved(env):
    b = env["b"]
    d = b.open_dispute(env["inv"]["invoice_id"], _dispute())
    with pytest.raises(DisputeError) as e:
        b.resolve(d["dispute_id"])
    assert e.value.code == "UAP_DISPUTE_NOT_RESOLVABLE"
