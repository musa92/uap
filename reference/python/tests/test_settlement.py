"""Accounts, invoices and payouts: enrolment, spend control, and disbursement."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest

from uap import Exchange, SigningKey
from uap.settlement import AccountError, Settlement


@pytest.fixture
def st():
    ux = Exchange("uax.test", SigningKey.generate("uax"), floor_cpm_micros=10_000_000)
    return Settlement(ux)


def _advertiser(st, **over):
    return st.create_account({"entity_id": "brand.acme", "kind": "advertiser",
                              "currency": "USD", **over})


def _node(st, **over):
    return st.create_account({"entity_id": "node.a", "kind": "serving_node",
                              "currency": "USD", **over})


# -- enrolment ---------------------------------------------------------------

def test_new_account_starts_unverified_and_at_tier_zero(st):
    a = _node(st)
    assert a["status"] == "pending_verification"
    assert a["verification"]["trust_tier"] == 0


def test_duplicate_entity_is_refused(st):
    _advertiser(st)
    with pytest.raises(AccountError) as e:
        _advertiser(st)
    assert e.value.code == "UAP_ACCOUNT_EXISTS"


def test_key_cannot_be_enrolled_before_verification(st):
    a = _node(st)
    with pytest.raises(AccountError) as e:
        st.enrol_key(a["account_id"], SigningKey.generate("k").verifying_key)
    assert e.value.code == "UAP_ACCOUNT_UNVERIFIED"


def test_verification_is_what_grants_the_tier(st):
    a = _node(st)
    st.verify_account(a["account_id"], identity="kyc", tax_form="w9", trust_tier=1)
    st.enrol_key(a["account_id"], SigningKey.generate("k").verifying_key)
    assert st.exchange.enrolled["node.a"] == 1


# -- spend control -----------------------------------------------------------

def test_prepay_account_cannot_outspend_its_balance(st):
    a = _advertiser(st)
    st.verify_account(a["account_id"], identity="kyb", domain_verified=True)
    with pytest.raises(AccountError) as e:
        st.check_spend("brand.acme", 5_000_000_000)
    assert e.value.code == "UAP_CREDIT_EXCEEDED"

    st.fund(a["account_id"], 5_000_000_000)
    st.check_spend("brand.acme", 5_000_000_000)          # now affordable


def test_net_terms_check_the_credit_limit_not_the_balance(st):
    a = _advertiser(st, credit={"terms": "net30", "limit_micros": 10**10})
    st.verify_account(a["account_id"], identity="kyb")
    st.check_spend("brand.acme", 9 * 10**9)              # under the limit, unfunded
    with pytest.raises(AccountError):
        st.check_spend("brand.acme", 2 * 10**10)


def test_entity_with_no_account_cannot_spend(st):
    with pytest.raises(AccountError) as e:
        st.check_spend("brand.unknown", 1)
    assert e.value.code == "UAP_ACCOUNT_UNVERIFIED"


# -- invoicing ---------------------------------------------------------------

PERIOD = {"start": "2026-10-01", "end": "2026-10-31"}
LINES = [{"campaign_id": "cmp_1", "line_item_id": "li_1", "pricing_model": "cpm",
          "billable_events": 120_000, "rejected_events": 4_000,
          "rejection_reasons": {"givt": 3_500, "nonce_spent": 500},
          "unit_price_micros": 40_000_000, "amount_micros": 4_800_000}]


def test_invoice_totals_include_adjustments(st):
    a = _advertiser(st)
    inv = st.issue_invoice(a["account_id"], PERIOD, LINES,
                           adjustments=[{"kind": "ivt_credit", "amount_micros": -140_000,
                                         "reason": "GIVT filtered post-billing"}])
    assert inv["subtotal_micros"] == 4_800_000 - 140_000
    assert inv["total_micros"] == inv["subtotal_micros"]
    assert inv["status"] == "issued"


def test_invoice_carries_rejection_reasons(st):
    """A buyer told only a total has nothing to reconcile against."""
    a = _advertiser(st)
    inv = st.issue_invoice(a["account_id"], PERIOD, LINES)
    assert inv["lines"][0]["rejection_reasons"]["givt"] == 3_500


def test_dispute_holds_the_amount_and_marks_the_invoice(st):
    a = _advertiser(st)
    inv = st.issue_invoice(a["account_id"], PERIOD, LINES)
    out = st.dispute_invoice(inv["invoice_id"], {
        "lines": [{"line_item_id": "li_1", "disputed_micros": 200_000}],
        "reason": "count_mismatch"})
    assert out["status"] == "disputed"
    # Held, not credited. Filing a dispute must not decide it: crediting here
    # would pre-judge the outcome and leave the payout side unreversed.
    assert out["held_micros"] == 200_000
    assert out["collectible_micros"] == out["total_micros"] - 200_000
    assert not any(a["kind"] == "dispute_credit" for a in out.get("adjustments", []))


def test_cannot_dispute_more_than_the_invoice(st):
    a = _advertiser(st)
    inv = st.issue_invoice(a["account_id"], PERIOD, LINES)
    with pytest.raises(AccountError) as e:
        st.dispute_invoice(inv["invoice_id"], {
            "lines": [{"line_item_id": "li_1", "disputed_micros": 99_000_000}],
            "reason": "other"})
    assert e.value.code == "UAP_INVOICE_NOT_DISPUTABLE"


# -- payouts -----------------------------------------------------------------

SPLITS = [{"party": "serving_node", "entity_id": "node.a", "bps": 6500, "amount_micros": 650_000},
          {"party": "model_steward", "entity_id": "steward.x", "bps": 1500, "amount_micros": 150_000},
          {"party": "exchange", "entity_id": "uax.test", "bps": 2000, "amount_micros": 200_000}]


def test_payout_without_a_tax_form_is_held_not_sent(st):
    a = _node(st, payout={"handler": "dev.uap.payout.ap2", "minimum_micros": 0})
    st.verify_account(a["account_id"], identity="kyc", trust_tier=1)   # no tax_form
    p = st.issue_payout(a["account_id"], PERIOD, gross_micros=1_000_000, splits=SPLITS)
    assert p["status"] == "held" and p["net_micros"] == 650_000


def test_payout_below_the_minimum_rolls_over(st):
    a = _node(st, payout={"handler": "dev.uap.payout.ap2", "minimum_micros": 10_000_000})
    st.verify_account(a["account_id"], identity="kyc", tax_form="w9")
    p = st.issue_payout(a["account_id"], PERIOD, gross_micros=1_000_000, splits=SPLITS)
    assert p["status"] == "rolled_over"


def test_withholding_reduces_the_net_not_the_share(st):
    a = _node(st, payout={"handler": "dev.uap.payout.ap2", "minimum_micros": 0})
    st.verify_account(a["account_id"], identity="kyc", tax_form="w8ben")
    p = st.issue_payout(a["account_id"], PERIOD, gross_micros=1_000_000, splits=SPLITS,
                        withholding={"scheme": "treaty", "rate_bps": 1000,
                                     "amount_micros": 65_000, "form": "w8ben"})
    assert p["net_micros"] == 650_000 - 65_000
    assert p["splits"][0]["amount_micros"] == 650_000      # the share is unchanged


def test_sending_a_payout_moves_settled_to_disbursed(st):
    a = _node(st, payout={"handler": "dev.uap.payout.ap2", "minimum_micros": 0})
    st.verify_account(a["account_id"], identity="kyc", tax_form="w9")
    p = st.issue_payout(a["account_id"], PERIOD, gross_micros=1_000_000, splits=SPLITS)
    assert p["status"] == "pending"
    assert st.accounts[a["account_id"]]["balance"]["settled_micros"] == 650_000
    st.mark_sent(p["payout_id"], "stripe:tr_123")
    bal = st.accounts[a["account_id"]]["balance"]
    assert bal["settled_micros"] == 0 and bal["disbursed_micros"] == 650_000


def test_a_held_payout_cannot_be_marked_sent(st):
    a = _node(st, payout={"minimum_micros": 0, "on_hold": True})
    st.verify_account(a["account_id"], identity="kyc", tax_form="w9")
    p = st.issue_payout(a["account_id"], PERIOD, gross_micros=1_000_000, splits=SPLITS)
    with pytest.raises(AccountError):
        st.mark_sent(p["payout_id"], "x")


# -- both sides reconcile ------------------------------------------------------

def test_accrual_credits_payee_and_debits_advertiser(st):
    adv = _advertiser(st)
    node = _node(st)
    st.verify_account(adv["account_id"], identity="kyb")
    st.verify_account(node["account_id"], identity="kyc", tax_form="w9")

    class V:
        billable = True
        gross_micros = 1_000_000
        splits = SPLITS
    st.accrue(V(), advertiser_entity="brand.acme")

    assert st.accounts[adv["account_id"]]["balance"]["pending_micros"] == 1_000_000
    assert st.accounts[node["account_id"]]["balance"]["pending_micros"] == 650_000


def test_unbillable_receipts_accrue_nothing(st):
    adv = _advertiser(st)

    class V:
        billable = False
        gross_micros = 0
        splits = []
    st.accrue(V(), advertiser_entity="brand.acme")
    assert st.accounts[adv["account_id"]]["balance"]["pending_micros"] == 0
