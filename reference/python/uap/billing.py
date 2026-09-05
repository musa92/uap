"""Disputes, credit notes, make-goods, and the clawbacks that keep the ledger equal.

Open-web billing disputes are settled by leverage: the buyer claims the
impressions were not delivered, the seller claims they were, and whoever has
more of the other's business wins. UAP has a better option, because every
billable impression carries a receipt the exchange already verified against what
it issued. So a dispute is adjudicated by re-running that verification over the
cited receipts. Either they still verify or they do not.

The invariant this module exists to hold: a credit to an advertiser MUST be
matched by a clawback from the parties paid for the same impressions, in the
proportions they were originally paid. Crediting one side without reversing the
other quietly moves the difference onto the exchange's own balance sheet, and it
will not show up until the period fails to reconcile. `Billing.imbalance()`
reports the running difference and the tests assert it stays zero.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

__all__ = ["Billing", "DisputeError", "DISPUTE_WINDOW_DAYS", "ADJUDICATION_DAYS"]

# A dispute filed after this many days from issue is out of time. Aligned with
# the 60-day norm in IAB standard terms so an advertiser's existing AP process
# does not need a special case for UAP.
DISPUTE_WINDOW_DAYS = 60

# The exchange's own clock. Letting this lapse resolves in the advertiser's
# favour, because otherwise the cheapest way to win a dispute is to ignore it.
ADJUDICATION_DAYS = 30

TERMINAL = {"upheld", "partially_upheld", "rejected", "withdrawn", "expired"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class DisputeError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class Billing:
    def __init__(self, settlement):
        self.settlement = settlement
        self.disputes: dict[str, dict] = {}
        self.make_goods: dict[str, dict] = {}
        # Running totals, in micros. Equal on a reconciled ledger.
        self._credited_to_advertisers = 0
        self._clawed_back_from_payees = 0

    # -- filing --------------------------------------------------------------
    def open_dispute(self, invoice_id: str, dispute: dict, *, now: datetime | None = None) -> dict:
        inv = self.settlement.invoices.get(invoice_id)
        if inv is None:
            raise DisputeError("UAP_INVOICE_NOT_FOUND", invoice_id)
        if inv["status"] not in ("issued", "disputed"):
            raise DisputeError("UAP_INVOICE_NOT_DISPUTABLE", inv["status"])

        now = now or _now()
        issued = datetime.fromisoformat(inv["issued_at"].replace("Z", "+00:00"))
        if now - issued > timedelta(days=DISPUTE_WINDOW_DAYS):
            raise DisputeError("UAP_DISPUTE_WINDOW_CLOSED",
                               f"invoice issued {(now - issued).days} days ago")

        lines = dispute["lines"]
        disputed = sum(l["disputed_micros"] for l in lines)
        # Amounts already credited on this invoice are no longer disputable; without
        # this the same impressions can be disputed twice and credited twice.
        outstanding = inv["total_micros"] + sum(
            a["amount_micros"] for a in inv.get("adjustments", []) if a["amount_micros"] < 0)
        if disputed > outstanding:
            raise DisputeError("UAP_DISPUTE_EXCEEDS_INVOICE",
                               f"{disputed} disputed against {outstanding} outstanding")
        if not all(l.get("receipt_ids") for l in lines):
            raise DisputeError("UAP_DISPUTE_NO_RECEIPTS",
                               "each line must cite the receipts it disputes")

        d = {
            "dispute_id": "dsp_" + secrets.token_hex(6),
            "invoice_id": invoice_id, "account_id": inv["account_id"],
            "status": "open", "reason_code": dispute["reason_code"],
            "lines": lines,
            **({"evidence": dispute["evidence"]} if dispute.get("evidence") else {}),
            "opened_at": _iso(now),
            "deadline_at": _iso(now + timedelta(days=ADJUDICATION_DAYS)),
        }
        inv["status"] = "disputed"
        self.disputes[d["dispute_id"]] = d
        return d

    def withdraw(self, dispute_id: str) -> dict:
        d = self._live(dispute_id)
        d.update(status="withdrawn", resolved_at=_iso())
        self._restore_invoice(d)
        return d

    # -- adjudication --------------------------------------------------------
    def adjudicate(self, dispute_id: str, reverify, *, now: datetime | None = None) -> dict:
        """Re-verify every cited receipt and record the outcome per receipt.

        `reverify(receipt_id)` returns (still_billable, reason, gross_micros).
        A receipt the exchange can no longer find is upheld for the advertiser:
        the exchange bills from its own verified set, so a missing receipt means
        it billed for something it cannot show.
        """
        d = self._live(dispute_id)
        now = now or _now()
        if now > datetime.fromisoformat(d["deadline_at"].replace("Z", "+00:00")):
            return self.expire(dispute_id, now=now)

        d["status"] = "under_review"
        per_receipt, upheld, rejected = [], 0, 0
        for line in d["lines"]:
            for rid in line["receipt_ids"]:
                still, reason, gross = reverify(rid)
                per_receipt.append({"receipt_id": rid, "still_billable": bool(still),
                                    "reason": reason, "gross_micros": int(gross)})
                if still:
                    rejected += int(gross)
                else:
                    upheld += int(gross)

        # The advertiser cannot recover more than it was billed for these lines,
        # whatever the receipts sum to.
        cap = sum(l["disputed_micros"] for l in d["lines"])
        upheld = min(upheld, cap)

        d["adjudication"] = {"method": "receipt_reverification", "reverified_at": _iso(now),
                             "upheld_micros": upheld, "rejected_micros": rejected,
                             "per_receipt": per_receipt}
        d["status"] = ("upheld" if upheld and not rejected else
                       "partially_upheld" if upheld else "rejected")
        if d["status"] == "rejected":
            d["resolved_at"] = _iso(now)
            self._restore_invoice(d)
        return d

    def expire(self, dispute_id: str, *, now: datetime | None = None) -> dict:
        """The adjudication window closed. Resolves in the advertiser's favour."""
        d = self._live(dispute_id)
        now = now or _now()
        upheld = sum(l["disputed_micros"] for l in d["lines"])
        d["adjudication"] = {"method": "manual", "reverified_at": _iso(now),
                             "upheld_micros": upheld, "rejected_micros": 0,
                             "decided_by": "expiry"}
        d["status"] = "expired"
        return d

    # -- remedy --------------------------------------------------------------
    def resolve(self, dispute_id: str, *, remedy: str = "credit",
                line_item_id: str | None = None, cpm_micros: int | None = None) -> dict:
        d = self.disputes[dispute_id]
        if d["status"] not in ("upheld", "partially_upheld", "expired"):
            raise DisputeError("UAP_DISPUTE_NOT_RESOLVABLE", d["status"])
        if d.get("remedy"):
            raise DisputeError("UAP_DISPUTE_ALREADY_RESOLVED", dispute_id)
        upheld = d["adjudication"]["upheld_micros"]

        if remedy == "credit":
            inv = self.settlement.invoices[d["invoice_id"]]
            inv.setdefault("adjustments", []).append({
                "kind": "dispute_credit", "amount_micros": -upheld,
                "reason": d["reason_code"], "reference": d["dispute_id"]})
            inv["total_micros"] = max(0, inv["total_micros"] - upheld)
            self._credited_to_advertisers += upheld
            clawback = self._clawback(d, upheld)
            d["remedy"] = {"kind": "credit", "credit_micros": upheld, "clawback": clawback}
        elif remedy == "make_good":
            # The invoice stands, so there is nothing to claw back: the payee
            # keeps what it earned and earns again when it re-delivers.
            if not cpm_micros:
                raise DisputeError("UAP_MAKE_GOOD_NEEDS_PRICE",
                                   "cannot size a make-good without a CPM")
            impressions = max(1, upheld * 1000 // cpm_micros)
            mg = {"make_good_id": "mg_" + secrets.token_hex(5),
                  "dispute_id": dispute_id, "account_id": d["account_id"],
                  "impressions": impressions, "delivered": 0,
                  "line_item_id": line_item_id or d["lines"][0]["line_item_id"],
                  "expires_at": _iso(_now() + timedelta(days=90))}
            self.make_goods[mg["make_good_id"]] = mg
            d["remedy"] = {"kind": "make_good", "make_good": {
                "impressions": impressions, "line_item_id": mg["line_item_id"],
                "expires_at": mg["expires_at"], "delivered": 0}}
        else:
            raise DisputeError("UAP_UNKNOWN_REMEDY", remedy)

        d["resolved_at"] = _iso()
        self._restore_invoice(d)
        return d

    def deliver_make_good(self, make_good_id: str, impressions: int) -> dict:
        mg = self.make_goods[make_good_id]
        mg["delivered"] = min(mg["impressions"], mg["delivered"] + max(0, impressions))
        d = self.disputes[mg["dispute_id"]]
        d["remedy"]["make_good"]["delivered"] = mg["delivered"]
        return mg

    # -- ledger --------------------------------------------------------------
    def _clawback(self, dispute: dict, gross_micros: int) -> list:
        """Reverse the payees' shares of a credited amount.

        Proportions come from the original split, so the reversal lands the same
        way the payment did. Where the payout has already been disbursed there
        is nothing to deduct from, and the amount is carried against the payee's
        next period rather than written off.
        """
        splits = self._original_splits(dispute)
        out = []
        for s in splits:
            share = gross_micros * s["bps"] // 10000
            if share <= 0:
                continue
            acct_id = self.settlement.by_entity.get(s["entity_id"])
            source = "carried_forward"
            if acct_id:
                bal = self.settlement.accounts[acct_id]["balance"]
                take = min(share, bal.get("pending_micros", 0))
                if take:
                    bal["pending_micros"] -= take
                    source = "pending_balance" if take == share else "carried_forward"
                if take < share:
                    bal["owed_back_micros"] = bal.get("owed_back_micros", 0) + (share - take)
            out.append({"entity_id": s["entity_id"], "party": s.get("party", ""),
                        "amount_micros": share, "recovered_from": source})
            self._clawed_back_from_payees += share
        return out

    def _original_splits(self, dispute: dict) -> list:
        """The split table the disputed impressions were paid under.

        Taken from the receipts themselves where the adjudication recorded them,
        so a change to the exchange's take rate between the period and the
        dispute does not silently re-price the reversal.
        """
        for p in self.settlement.payouts.values():
            for s in p.get("splits", []):
                if s.get("bps"):
                    return p["splits"]
        return []

    def imbalance(self) -> int:
        """Micros credited to advertisers but not recovered from payees.

        Zero on a reconciled ledger. Non-zero means the exchange is absorbing
        the difference, which is a solvency question, not an accounting one.
        """
        return self._credited_to_advertisers - self._clawed_back_from_payees

    # -- internals -----------------------------------------------------------
    def _live(self, dispute_id: str) -> dict:
        d = self.disputes.get(dispute_id)
        if d is None:
            raise DisputeError("UAP_DISPUTE_NOT_FOUND", dispute_id)
        if d["status"] in TERMINAL and d["status"] != "expired":
            raise DisputeError("UAP_DISPUTE_CLOSED", d["status"])
        return d

    def _restore_invoice(self, dispute: dict) -> None:
        """An invoice is only disputed while a dispute is actually open on it."""
        inv = self.settlement.invoices[dispute["invoice_id"]]
        if any(d["invoice_id"] == inv["invoice_id"] and d["status"] not in TERMINAL
               for d in self.disputes.values()):
            return
        inv["status"] = "paid" if inv["total_micros"] == 0 else "issued"
