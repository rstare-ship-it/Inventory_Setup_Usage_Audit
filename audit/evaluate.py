"""
Evaluation layer: thin loops over check registries.

evaluate_audit()                → full inventory audit
evaluate_audit_purchasing_only() → purchasing-only (pre-go-live) audit

Each check returns a list[Finding]; we collect them all into findings_by_area.
To add a new check to an audit mode, edit audit/checks.py — not this file.
"""
from __future__ import annotations

from audit.checks import (
    Finding,
    FULL_AUDIT_CHECKS,
    PURCHASING_ONLY_CHECKS,
)
from audit.constants import AUDIT_AREAS, AUDIT_AREAS_PURCHASING


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add(findings_by_area: dict, area: str, level: str, message: str) -> None:
    """Ensure the area dict exists and append (level → message)."""
    if area not in findings_by_area:
        findings_by_area[area] = {"green": [], "yellow": [], "review": [], "red": []}
    findings_by_area[area][level].append(message)


def _area_status(findings: dict) -> str:
    """Derive a single status from the mix of green/yellow/review/red findings.

    Rule: % green of total determines tier.
        ≥80% green → Green (Good)
        ≥60% green → Yellow (Okay)
        ≥40% green → Review (Needs review)
        <40%       → Red (Needs attention)
    """
    g = len(findings.get("green") or [])
    y = len(findings.get("yellow") or [])
    rev = len(findings.get("review") or [])
    r = len(findings.get("red") or [])
    total = g + y + rev + r
    if total == 0:
        return "Green"
    pct = (100 * g) // total
    if pct >= 80:
        return "Green"
    if pct >= 60:
        return "Yellow"
    if pct >= 40:
        return "Review"
    return "Red"


def _collect(checks, results: dict, lookback_days: int) -> dict[str, dict[str, list[str]]]:
    """Run all checks in the list; collect findings into findings_by_area."""
    findings_by_area: dict[str, dict[str, list[str]]] = {}
    for check in checks:
        for finding in check(results, lookback_days):
            _add(findings_by_area, finding.area, finding.level, finding.message)
    return findings_by_area


# ---------------------------------------------------------------------------
# Public evaluation functions
# ---------------------------------------------------------------------------

def evaluate_audit(
    results: dict,
    lookback_days: int,
) -> tuple[bool, dict[str, dict[str, list[str]]]]:
    """Full inventory audit. Returns (ok, findings_by_area).
    ok = True when no area has any red findings."""
    findings_by_area = _collect(FULL_AUDIT_CHECKS, results, lookback_days)
    ok = not any(f.get("red") for f in findings_by_area.values())
    return ok, findings_by_area


def evaluate_audit_purchasing_only(
    results: dict,
    lookback_days: int,
) -> tuple[bool, dict[str, dict[str, list[str]]], bool]:
    """Purchasing-only audit (pre-go-live).
    Returns (ok, findings_by_area, ready_for_inventory_implementation).
    ready = no red in Pricebook, Purchasing, or Invoicing areas."""
    findings_by_area = _collect(PURCHASING_ONLY_CHECKS, results, lookback_days)
    ok = not any(f.get("red") for f in findings_by_area.values())
    ready = not any(
        findings_by_area.get(a, {}).get("red")
        for a in ("Pricebook", "Purchasing", "Invoicing")
    )
    return ok, findings_by_area, ready


def get_action_plan(
    findings_by_area: dict[str, dict[str, list[str]]],
    audit_areas: list[str],
) -> list[str]:
    """Build a de-duplicated action plan from non-Green areas.

    Each area maps to one or more recommended actions.  Actions that mention
    specific findings (e.g. negative balances, zero-cost lines) are added only
    when those finding messages are present.
    """
    actions: list[str] = []
    seen: set[str] = set()

    def add(action: str) -> None:
        s = action.strip()
        if s and s not in seen:
            seen.add(s)
            actions.append(s)

    for area in audit_areas:
        findings = findings_by_area.get(area, {"green": [], "yellow": [], "review": [], "red": []})
        if _area_status(findings) == "Green":
            continue

        all_msgs = (findings.get("red") or []) + (findings.get("review") or []) + (findings.get("yellow") or [])

        if area == "Technician usage":
            add("Schedule technician training on adding materials to invoices in the field.")

        elif area == "Pricebook & setup":
            add("Review trucks and warehouses; assign inventory templates to trucks and warehouses as needed.")
            if any("20 active" in f or "fewer than" in f for f in all_msgs):
                add("Review templates with fewer than 20 active items; add items or replace with a complete template.")

        elif area == "Purchasing":
            add("Review pending POs; receive or close old POs and keep pending count within half of truck count where possible.")
            add("Use multi-line POs for stock orders; avoid single-line or placeholder-heavy POs.")

        elif area == "Invoicing":
            add("Ensure invoices with amount > $0 include inventory materials where applicable; train office and field on invoice material usage.")
            if any("Zero-cost" in f or "zero-cost" in f for f in all_msgs):
                add("Review cost flow from PO/receiving to invoice; fix zero-cost IsInventory lines where cost should flow.")

        elif area == "Replenishment":
            add("Address open replenishment requests; complete and receive replenishments to improve turnover.")

        elif area == "Returns":
            add("Process pending returns and issue credits so returns don't age.")

        elif area == "Transfers":
            add("Complete or cancel aging transfers; encourage transfer-to-job usage where appropriate.")

        elif area == "Counts and adjustments":
            count_added = False
            if any("Past due" in f or "past due" in f for f in all_msgs):
                add("Complete or reschedule past due inventory counts.")
                count_added = True
            if any("Negative" in f or "negative" in f for f in all_msgs):
                add("Run an inventory count and adjustments to resolve negative quantities.")
                count_added = True
            if any("Direct" in f and "adjustment" in f for f in all_msgs):
                add("Review direct adjustment practices; reduce manual adjustments where possible.")
                count_added = True
            if any("no completed count" in f or "no count" in f for f in all_msgs):
                add("Schedule and complete cycle counts for all warehouses.")
                count_added = True
            if not count_added:
                add("Review counts and adjustments; complete cycle counts and resolve discrepancies as needed.")

        elif area == "Other":
            add("Close or complete aging requisitions.")

    return actions


def area_statuses(
    findings_by_area: dict[str, dict[str, list[str]]],
    audit_areas: list[str],
) -> dict[str, str]:
    """Return {area: status} for every area in audit_areas (N/A when area not in findings)."""
    out: dict[str, str] = {}
    for area in audit_areas:
        if area in findings_by_area:
            out[area] = _area_status(findings_by_area[area])
        else:
            out[area] = "N/A"
    return out
