"""Measurement quality, in the vocabulary buyers reconcile against.

Media Rating Council definitions, restated: a display impression is viewable
when at least 50% of its pixels are in view for at least one continuous second,
video at 50% for two seconds, and large formats at 30% for one second. Invalid
traffic splits into GIVT, which list-based filtration catches, and SIVT, which
requires analytics and multi-point corroboration.

None of that is novel. It is here because a bespoke viewability definition
cannot be priced against a rate card, and a seller reporting metrics a buyer
cannot map onto its existing reconciliation is a seller that gets discounted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev

__all__ = ["MRC_THRESHOLDS", "meets_mrc", "QualityReport", "assess"]

# standard -> (minimum visible fraction, minimum continuous milliseconds)
MRC_THRESHOLDS = {
    "mrc_display": (0.50, 1000),
    "mrc_video": (0.50, 2000),
    "mrc_large_display": (0.30, 1000),
    "audible_playback": (1.00, 0),
}


def meets_mrc(viewability: dict) -> tuple[bool, str]:
    """Check a viewability block against the threshold it claims."""
    standard = viewability.get("standard")
    if standard == "delivered_only":
        if viewability.get("viewable"):
            return False, "a surface that cannot observe visibility claimed a viewable impression"
        return False, "delivered_only is not a viewability claim"
    if standard not in MRC_THRESHOLDS:
        return False, f"unknown measurement standard {standard!r}"
    if not viewability.get("viewable"):
        return False, "not claimed viewable"

    min_pct, min_ms = MRC_THRESHOLDS[standard]
    pct = viewability.get("visible_pct")
    ms = viewability.get("visible_ms")
    if ms is None:
        return False, "viewable asserted without visible_ms to support it"
    if ms < min_ms:
        return False, f"{ms} ms is below the {min_ms} ms threshold for {standard}"
    if pct is not None and pct / 100 < min_pct:
        return False, f"{pct}% is below the {int(min_pct*100)}% threshold for {standard}"
    return True, "meets the MRC threshold"


@dataclass
class QualityReport:
    impressions: int = 0
    viewable: int = 0
    givt: int = 0
    sivt: int = 0
    unclassified: int = 0
    anomalies: list[str] = field(default_factory=list)

    @property
    def viewable_rate(self) -> float:
        return self.viewable / self.impressions if self.impressions else 0.0

    @property
    def ivt_rate(self) -> float:
        return (self.givt + self.sivt) / self.impressions if self.impressions else 0.0

    def to_json(self) -> dict:
        return {"impressions": self.impressions, "viewable": self.viewable,
                "viewable_rate": round(self.viewable_rate, 4),
                "givt": self.givt, "sivt": self.sivt,
                "unclassified": self.unclassified,
                "ivt_rate": round(self.ivt_rate, 4),
                "anomalies": self.anomalies}


def assess(receipts: list[dict]) -> QualityReport:
    """Aggregate measurement quality across a node's receipts.

    The dwell check is the one that matters. Fabricated impressions are cheap to
    generate one at a time and hard to generate with a plausible distribution,
    so a dwell time distribution that is too tight is stronger evidence than any
    individual receipt.
    """
    report = QualityReport()
    dwells = []

    for receipt in receipts:
        view = receipt.get("viewability") or {}
        report.impressions += 1
        if meets_mrc(view)[0]:
            report.viewable += 1
        classification = (view.get("ivt") or {}).get("classification", "unclassified")
        if classification == "givt":
            report.givt += 1
        elif classification == "sivt":
            report.sivt += 1
        elif classification != "valid":
            report.unclassified += 1
        if isinstance(view.get("visible_ms"), int):
            dwells.append(view["visible_ms"])

        if receipt.get("trust_tier") == 0 and classification == "valid":
            report.anomalies.append(
                "tier 0 traffic reported as valid; unattested supply is "
                "indistinguishable from GIVT by construction")

    if len(dwells) >= 30:
        spread = pstdev(dwells)
        centre = mean(dwells)
        if centre and spread / centre < 0.05:
            report.anomalies.append(
                f"dwell distribution is implausibly tight (sd/mean "
                f"{spread/centre:.3f} over {len(dwells)} impressions); "
                f"real human dwell is not this uniform")
        if len(set(dwells)) == 1:
            report.anomalies.append("every impression reports an identical dwell time")

    report.anomalies = sorted(set(report.anomalies))
    return report
