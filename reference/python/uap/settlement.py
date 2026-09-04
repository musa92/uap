"""Accounts, invoices and payouts: the commercial side of the exchange.

Cryptographic identity and commercial identity are separate. A signing key
proves who sent a message; an account decides who is billed or paid. A key with
no account is trust tier 0, which may serve and be paid on CPA but may not sell
CPM. Enrolling a key against an account is what moves supply to tier 1.

Both directions live here because the lifecycle is identical. An advertiser
account accrues a payable and receives invoices; a node, supply agent or model
steward accrues a receivable and receives payouts. The two are reconciled
against the same verified receipt set, so an exchange that bills for an
impression it does not pay out on is visibly out of balance.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from .crypto import VerifyingKey

__all__ = ["Settlement", "AccountError"]

PAYEE_KINDS = {"serving_node", "supply_agent", "model_steward", "measurement_agent"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class AccountError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class Settlement:
    def __init__(self, exchange):
        self.exchange = exchange
        self.accounts: dict[str, dict] = {}
        self.by_entity: dict[str, str] = {}
        self.invoices: dict[str, dict] = {}
        self.payouts: dict[str, dict] = {}

    # -- enrolment -----------------------------------------------------------
    def create_account(self, account: dict) -> dict:
        entity = account.get("entity_id", "")
        kind = account.get("kind", "")
        if entity in self.by_entity:
            raise AccountError("UAP_ACCOUNT_EXISTS", entity)
        aid = account.get("account_id") or "acct_" + secrets.token_hex(6)
        rec = {
            "account_id": aid, "entity_id": entity, "kind": kind,
            "status": "pending_verification",
            "currency": account.get("currency", "USD"),
            "verification": {"identity": "none", "trust_tier": 0,
                             **(account.get("verification") or {})},
            "balance": {"settled_micros": 0, "pending_micros": 0,
                        "disbursed_micros": 0, "as_of": _iso()},
            "created_at": _iso(), "updated_at": _iso(),
        }
        if kind == "advertiser":
            rec["credit"] = {"terms": "prepay", "limit_micros": 0,
                             **(account.get("credit") or {})}
        elif kind in PAYEE_KINDS:
            rec["payout"] = {"minimum_micros": 10_000_000, "schedule": "monthly",
                             "on_hold": False, **(account.get("payout") or {})}
        self.accounts[aid] = rec
        self.by_entity[entity] = aid
        return rec

    def verify_account(self, account_id: str, *, identity: str = "kyb",
                       domain_verified: bool | None = None, tax_form: str | None = None,
                       trust_tier: int = 1) -> dict:
        """Record the outcome of verification. The protocol does not perform it."""
        a = self.accounts[account_id]
        v = a["verification"]
        v.update({"identity": identity, "trust_tier": trust_tier, "verified_at": _iso()})
        if domain_verified is not None:
            v["domain_verified"] = domain_verified
        if tax_form is not None:
            v["tax_form"] = tax_form
        a["status"] = "active"
        a["updated_at"] = _iso()
        # Tier is a consequence of enrolment, so the exchange's own view follows.
        if a["kind"] in PAYEE_KINDS:
            self.exchange.enrolled[a["entity_id"]] = trust_tier
        return a

    def enrol_key(self, account_id: str, key: VerifyingKey) -> dict:
        """Bind a signing key to the commercial account. This is what tier 1 means."""
        a = self.accounts[account_id]
        if a["status"] != "active":
            raise AccountError("UAP_ACCOUNT_UNVERIFIED", a["status"])
        tier = a["verification"].get("trust_tier", 1)
        self.exchange.enrol(a["entity_id"], key, tier)
        return key.to_jwk()

    # -- spend authorisation -------------------------------------------------
    def check_spend(self, entity_id: str, budget_micros: int) -> None:
        """Refuse a campaign an account cannot fund. Called before it goes live."""
        aid = self.by_entity.get(entity_id)
        if aid is None:
            raise AccountError("UAP_ACCOUNT_UNVERIFIED", f"{entity_id} has no account")
        a = self.accounts[aid]
        if a["status"] != "active":
            raise AccountError("UAP_ACCOUNT_UNVERIFIED", a["status"])
        credit = a.get("credit") or {}
        if credit.get("terms", "prepay") == "prepay":
            available = a["balance"]["settled_micros"]
            if budget_micros > available:
                raise AccountError("UAP_CREDIT_EXCEEDED",
                                   f"budget {budget_micros} exceeds prepaid balance {available}")
        elif budget_micros > credit.get("limit_micros", 0):
            raise AccountError("UAP_CREDIT_EXCEEDED",
                               f"budget {budget_micros} exceeds credit limit {credit.get('limit_micros', 0)}")

    def fund(self, account_id: str, micros: int) -> dict:
        a = self.accounts[account_id]
        a["balance"]["settled_micros"] += micros
        a["balance"]["as_of"] = _iso()
        return a["balance"]

    # -- accrual -------------------------------------------------------------
    def accrue(self, verdict, *, advertiser_entity: str | None = None) -> None:
        """Record a billable impression on both sides of the ledger."""
        if not verdict.billable:
            return
        if advertiser_entity and (aid := self.by_entity.get(advertiser_entity)):
            self.accounts[aid]["balance"]["pending_micros"] += verdict.gross_micros
        for split in verdict.splits:
            if split["party"] == "exchange":
                continue
            aid = self.by_entity.get(split.get("entity_id", ""))
            if aid:
                self.accounts[aid]["balance"]["pending_micros"] += split["amount_micros"]

    # -- period close --------------------------------------------------------
    def issue_invoice(self, account_id: str, period: dict, lines: list,
                      adjustments: list | None = None, tax: dict | None = None) -> dict:
        a = self.accounts[account_id]
        subtotal = sum(l["amount_micros"] for l in lines)
        adjustments = adjustments or []
        subtotal += sum(adj["amount_micros"] for adj in adjustments)
        tax_amount = (tax or {}).get("amount_micros", 0)
        inv = {
            "invoice_id": "inv_" + secrets.token_hex(6), "account_id": account_id,
            "period": period, "currency": a["currency"], "status": "issued",
            "lines": lines, "adjustments": adjustments,
            "subtotal_micros": max(0, subtotal),
            **({"tax": tax} if tax else {}),
            "total_micros": max(0, subtotal + tax_amount),
            "issued_at": _iso(),
        }
        self.invoices[inv["invoice_id"]] = inv
        return inv

    def dispute_invoice(self, invoice_id: str, dispute: dict) -> dict:
        inv = self.invoices[invoice_id]
        if inv["status"] not in ("issued", "disputed"):
            raise AccountError("UAP_INVOICE_NOT_DISPUTABLE", inv["status"])
        disputed = sum(l["disputed_micros"] for l in dispute["lines"])
        if disputed > inv["total_micros"]:
            raise AccountError("UAP_INVOICE_NOT_DISPUTABLE", "disputed amount exceeds invoice total")
        inv["status"] = "disputed"
        inv.setdefault("adjustments", []).append({
            "kind": "dispute_credit", "amount_micros": -disputed,
            "reason": dispute["reason"],
            "reference": "dsp_" + secrets.token_hex(4)})
        return inv

    def issue_payout(self, account_id: str, period: dict, *, gross_micros: int,
                     splits: list, receipts: dict | None = None,
                     withholding: dict | None = None) -> dict:
        a = self.accounts[account_id]
        mine = next((s for s in splits if s.get("entity_id") == a["entity_id"]), None)
        share = mine["amount_micros"] if mine else gross_micros
        withheld = (withholding or {}).get("amount_micros", 0)
        net = max(0, share - withheld)
        payout_cfg = a.get("payout") or {}

        if payout_cfg.get("on_hold"):
            status = "held"
        elif not a["verification"].get("tax_form") or a["verification"]["tax_form"] == "none":
            # Disbursing without a form on file is a reporting problem, not a
            # protocol one. The balance is still owed; it just cannot be sent.
            status = "held"
        elif net < payout_cfg.get("minimum_micros", 0):
            status = "rolled_over"
        else:
            status = "pending"

        p = {
            "payout_id": "pay_" + secrets.token_hex(6), "account_id": account_id,
            "entity_id": a["entity_id"], "party": a["kind"], "period": period,
            "currency": a["currency"], "status": status,
            "gross_micros": gross_micros, "splits": splits, "net_micros": net,
            **({"receipts": receipts} if receipts else {}),
            **({"withholding": withholding} if withholding else {}),
            **({"handler": payout_cfg["handler"]} if payout_cfg.get("handler") else {}),
        }
        if status in ("pending", "sent"):
            a["balance"]["pending_micros"] = max(0, a["balance"]["pending_micros"] - share)
            a["balance"]["settled_micros"] += net
        self.payouts[p["payout_id"]] = p
        return p

    def mark_sent(self, payout_id: str, handler_reference: str) -> dict:
        p = self.payouts[payout_id]
        if p["status"] != "pending":
            raise AccountError("UAP_ACCOUNT_UNVERIFIED", f"payout is {p['status']}")
        p.update({"status": "sent", "handler_reference": handler_reference, "sent_at": _iso()})
        a = self.accounts[p["account_id"]]
        a["balance"]["settled_micros"] = max(0, a["balance"]["settled_micros"] - p["net_micros"])
        a["balance"]["disbursed_micros"] += p["net_micros"]
        a["balance"]["as_of"] = _iso()
        return p
