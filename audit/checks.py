"""
Audit check functions and registries.

Each check is a plain function:
    def check_*(results: dict, lookback_days: int) -> list[Finding]

Add a check to FULL_AUDIT_CHECKS or PURCHASING_ONLY_CHECKS (or both) to include it in that
audit mode.  To write a new check, add the function here then append it to the appropriate list.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from audit.constants import (
    PENDING_STATUS_WAITING_TO_SEND,
    PENDING_STATUSES,
    PENDING_PCT_OF_ALLOWED_GOOD_MAX,
    PENDING_PCT_OF_ALLOWED_OKAY_MAX,
    PENDING_PCT_OF_ALLOWED_REVIEW_MAX,
    PENDING_POS_ALLOWED_PER_TRUCK,
    TOTAL_PENDING_ABSOLUTE_RED,
    PO_RECEIVE_RATE_GOOD_MIN_PCT,
    PO_RECEIVE_RATE_OKAY_MIN_PCT,
    PO_RECEIVE_RATE_REVIEW_MIN_PCT,
    PO_MULTI_LINE_RED_MAX_PCT,
    PO_MULTI_LINE_REVIEW_MAX_PCT,
    PO_MULTI_LINE_YELLOW_MIN_PCT,
    PO_MULTI_LINE_YELLOW_MAX_PCT,
    PO_PLACEHOLDER_MAJORITY,
    INVOICE_GT_ZERO_WITH_MATERIAL_GOOD_MIN_PCT,
    INVOICE_GT_ZERO_WITH_MATERIAL_OKAY_MIN_PCT,
    INVOICE_GT_ZERO_WITH_MATERIAL_REVIEW_MIN_PCT,
    INVOICE_MATERIAL_LINES_ISINVENTORY_GOOD_MIN_PCT,
    INVOICE_MATERIAL_LINES_ISINVENTORY_OKAY_MIN_PCT,
    INVOICE_MATERIAL_LINES_ISINVENTORY_REVIEW_MIN_PCT,
    INVOICE_ZERO_COST_GOOD_MAX_PCT,
    INVOICE_ZERO_COST_OKAY_MAX_PCT,
    INVOICE_ZERO_COST_REVIEW_MAX_PCT,
    INVOICE_TECH_ADDED_GOOD_MIN_PCT,
    INVOICE_TECH_ADDED_OKAY_MIN_PCT,
    INVOICE_TECH_ADDED_REVIEW_MIN_PCT,
    REPLENISHMENT_RATE_GOOD_MIN_PCT,
    REPLENISHMENT_RATE_OKAY_MIN_PCT,
    REPLENISHMENT_RATE_REVIEW_MIN_PCT,
    USAGE_REPLENISHMENT_OLD_30D_MAX,
    RETURN_CREDIT_RECEIVED_STATUS,
    RETURN_PENDING_PCT_GOOD_MAX,
    RETURN_PENDING_PCT_OKAY_MAX,
    RETURN_PENDING_PCT_REVIEW_MAX,
    TRUCK_TEMPLATE_PCT_MIN,
    WAREHOUSE_WITH_TEMPLATE_MIN,
    TEMPLATE_MIN_ACTIVE_ITEMS,
    MATERIALS_UNUSED_90D_YELLOW_MAX_PCT,
    MATERIALS_UNUSED_90D_RED_MIN_PCT,
    TRANSFER_EXPECTED_TRUCK_FRACTION,
    USAGE_TRANSFERS_OLD_14D_MAX,
    USAGE_PAST_DUE_COUNTS_MAX,
    USAGE_DIRECT_ADJUSTMENTS_MAX,
    WAREHOUSES_NO_COUNT_90D_MAX,
    USAGE_REQUISITIONS_OLD_90D_MAX,
    PRICEBOOK_RED_PCT,
)


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single audit finding for one area at one level."""
    area: str
    level: str    # "green" | "yellow" | "review" | "red"
    message: str


# Convenience shorthand
def _f(area: str, level: str, message: str) -> Finding:
    return Finding(area=area, level=level, message=message)


# Type alias for a check function
CheckFn = Callable[[dict, int], list[Finding]]


# ---------------------------------------------------------------------------
# Purchasing checks
# ---------------------------------------------------------------------------

def check_pending_pos(results: dict, lookback_days: int) -> list[Finding]:
    """Pending PO count relative to truck count (or absolute fallback)."""
    findings: list[Finding] = []
    area = "Purchasing"
    total_pending = results.get("total_pending_pos", 0)
    pending_po_over_90 = results.get("pending_pos_over_90_days", 0)
    setup = results.get("setup_data")
    truck_total = (setup.get("truck_total", 0) or 0) if setup and isinstance(setup, dict) else 0
    allowed_pending = max(0, int(truck_total * PENDING_POS_ALLOWED_PER_TRUCK)) if truck_total > 0 else None

    msg = f"Pending POs: {total_pending} of {allowed_pending} allowed." if allowed_pending else f"Pending POs: {total_pending}."
    if pending_po_over_90 > 0:
        msg += f" {pending_po_over_90} are older than 90 days."

    if allowed_pending is not None and allowed_pending > 0:
        pct = (100 * total_pending) // allowed_pending
        if pct <= PENDING_PCT_OF_ALLOWED_GOOD_MAX:
            findings.append(_f(area, "green", msg))
        elif pct <= PENDING_PCT_OF_ALLOWED_OKAY_MAX:
            target = (allowed_pending * PENDING_PCT_OF_ALLOWED_GOOD_MAX) // 100
            findings.append(_f(area, "yellow", msg + f" Reduce to {target} or fewer to reach Good."))
        elif pct <= PENDING_PCT_OF_ALLOWED_REVIEW_MAX:
            target = (allowed_pending * PENDING_PCT_OF_ALLOWED_OKAY_MAX) // 100
            findings.append(_f(area, "review", msg + f" Reduce to {target} or fewer to reach Okay."))
        else:
            target = (allowed_pending * PENDING_PCT_OF_ALLOWED_REVIEW_MAX) // 100
            findings.append(_f(area, "red", msg + f" Reduce to {target} or fewer to reach Needs Review."))
    else:
        if total_pending > TOTAL_PENDING_ABSOLUTE_RED or pending_po_over_90 > 0:
            findings.append(_f(area, "red", msg + " Reduce pending POs and resolve aged orders."))
        else:
            findings.append(_f(area, "green", msg))

    return findings


def check_po_usage(results: dict, lookback_days: int) -> list[Finding]:
    """PO creation and receipt in the lookback period.
    To count as 'using POs', orders must be both created and received/exported.
    Rate tiers measure what % of created POs are actually completed."""
    findings: list[Finding] = []
    area = "Purchasing"
    po = results.get("purchase_orders", {})
    by_status = po.get("by_status", {})
    completed = po.get("completed_count", 0)
    po_activity = results.get("po_activity", {})
    po_created = po_activity.get("po_created_in_period", 0)
    pending_waiting = by_status.get(PENDING_STATUS_WAITING_TO_SEND, 0)

    if po_created == 0:
        findings.append(_f(area, "red", f"No POs created in the last {lookback_days} days. Start creating and receiving purchase orders."))
        return findings

    if completed == 0:
        extra = f" {pending_waiting} POs are waiting to send." if pending_waiting > 5 else ""
        findings.append(_f(area, "red", f"{po_created} POs created but none received/exported.{extra} Begin processing receipts in ServiceTitan."))
        return findings

    rate_pct = (100 * completed) // po_created
    base = f"PO usage: {po_created} created, {completed} received/exported in last {lookback_days} days ({rate_pct}% receive rate)."
    if rate_pct >= PO_RECEIVE_RATE_GOOD_MIN_PCT:
        findings.append(_f(area, "green", base))
    elif rate_pct >= PO_RECEIVE_RATE_OKAY_MIN_PCT:
        target = (po_created * PO_RECEIVE_RATE_GOOD_MIN_PCT + 99) // 100
        findings.append(_f(area, "yellow", base + f" Receive {target}+ POs ({PO_RECEIVE_RATE_GOOD_MIN_PCT}%) to reach Good."))
    elif rate_pct >= PO_RECEIVE_RATE_REVIEW_MIN_PCT:
        target = (po_created * PO_RECEIVE_RATE_OKAY_MIN_PCT + 99) // 100
        findings.append(_f(area, "review", base + f" Receive {target}+ POs ({PO_RECEIVE_RATE_OKAY_MIN_PCT}%) to reach Okay."))
    else:
        target = (po_created * PO_RECEIVE_RATE_REVIEW_MIN_PCT + 99) // 100
        findings.append(_f(area, "red", base + f" Receive {target}+ POs ({PO_RECEIVE_RATE_REVIEW_MIN_PCT}%) to reach Needs Review."))
    return findings


def check_po_line_quality(results: dict, lookback_days: int) -> list[Finding]:
    """PO line quality: multi-line rate and placeholder description rate."""
    findings: list[Finding] = []
    area = "Purchasing"
    plq = results.get("po_line_quality", {})
    po_count = plq.get("po_count", 0)
    if po_count <= 0:
        return findings
    single = plq.get("pos_with_one_line_only", 0)
    total_lines = plq.get("total_line_items", 0)
    placeholder = plq.get("line_items_placeholder_like", 0)

    multi = po_count - single
    multi_pct = (100 * multi) // po_count
    line_msg = (
        f"PO line items: {total_lines} lines across {po_count} POs; "
        f"{multi} of {po_count} ({multi_pct}%) have multiple lines."
    )
    if multi_pct < PO_MULTI_LINE_RED_MAX_PCT:
        target = (po_count * PO_MULTI_LINE_REVIEW_MAX_PCT + 99) // 100
        findings.append(_f(area, "red", line_msg + f" Use multi-line POs — reach {PO_MULTI_LINE_REVIEW_MAX_PCT}% ({target}+ POs) to move to Needs Review."))
    elif multi_pct < PO_MULTI_LINE_REVIEW_MAX_PCT:
        target = (po_count * PO_MULTI_LINE_YELLOW_MIN_PCT + 99) // 100
        findings.append(_f(area, "review", line_msg + f" Reach {PO_MULTI_LINE_YELLOW_MIN_PCT}% ({target}+ POs) to move to Okay."))
    elif PO_MULTI_LINE_YELLOW_MIN_PCT <= multi_pct <= PO_MULTI_LINE_YELLOW_MAX_PCT:
        target = (po_count * (PO_MULTI_LINE_YELLOW_MAX_PCT + 1) + 99) // 100
        findings.append(_f(area, "yellow", line_msg + f" Reach {PO_MULTI_LINE_YELLOW_MAX_PCT + 1}%+ ({target}+ POs) to reach Good."))
    else:
        findings.append(_f(area, "green", line_msg))

    if total_lines > 0 and (placeholder / total_lines) > PO_PLACEHOLDER_MAJORITY:
        findings.append(_f(area, "red", f"Majority of PO line items use placeholder/generic descriptions ({placeholder} of {total_lines}). Use specific part names."))
    elif total_lines > 0 and placeholder > 0:
        findings.append(_f(area, "green", f"PO line descriptions: {placeholder} of {total_lines} lines with placeholder-like text."))
    elif total_lines > 0:
        findings.append(_f(area, "green", "PO line descriptions: all specific part names."))

    return findings


# ---------------------------------------------------------------------------
# Invoicing checks (full audit — IsInventory-aware)
# ---------------------------------------------------------------------------

def check_invoicing_coverage(results: dict, lookback_days: int) -> list[Finding]:
    """% of invoices >$0 that have at least one IsInventory material line."""
    findings: list[Finding] = []
    area = "Invoicing"
    inv = results.get("invoice_materials", {})
    total_gt_zero = inv.get("invoices_total_gt_zero", 0)
    gt_zero_with_mat = inv.get("invoices_gt_zero_with_material", 0)

    if total_gt_zero == 0:
        findings.append(_f(area, "yellow", "No invoices with amount greater than zero in the lookback period; invoice material coverage not assessed."))
        return findings

    pct = (100 * gt_zero_with_mat) // total_gt_zero
    line = (
        f"Invoice material coverage: {gt_zero_with_mat} of {total_gt_zero} invoices ({pct}%) "
        f"include at least one IsInventory material line."
    )
    if pct >= INVOICE_GT_ZERO_WITH_MATERIAL_GOOD_MIN_PCT:
        findings.append(_f(area, "green", line))
    elif pct >= INVOICE_GT_ZERO_WITH_MATERIAL_OKAY_MIN_PCT:
        target = (total_gt_zero * INVOICE_GT_ZERO_WITH_MATERIAL_GOOD_MIN_PCT + 99) // 100
        findings.append(_f(area, "yellow", line + f" Add materials to {target - gt_zero_with_mat} more invoice(s) to reach Good ({INVOICE_GT_ZERO_WITH_MATERIAL_GOOD_MIN_PCT}%+)."))
    elif pct >= INVOICE_GT_ZERO_WITH_MATERIAL_REVIEW_MIN_PCT:
        target = (total_gt_zero * INVOICE_GT_ZERO_WITH_MATERIAL_OKAY_MIN_PCT + 99) // 100
        findings.append(_f(area, "review", line + f" Add materials to {target - gt_zero_with_mat} more invoice(s) to reach Okay ({INVOICE_GT_ZERO_WITH_MATERIAL_OKAY_MIN_PCT}%+)."))
    else:
        target = (total_gt_zero * INVOICE_GT_ZERO_WITH_MATERIAL_REVIEW_MIN_PCT + 99) // 100
        findings.append(_f(area, "red", line + f" Add materials to {target - gt_zero_with_mat} more invoice(s) to reach Needs Review ({INVOICE_GT_ZERO_WITH_MATERIAL_REVIEW_MIN_PCT}%+)."))
    return findings


def check_invoicing_isinventory_lines(results: dict, lookback_days: int) -> list[Finding]:
    """% of all invoice material lines that are IsInventory."""
    findings: list[Finding] = []
    area = "Invoicing"
    inv = results.get("invoice_materials", {})
    mat_total = inv.get("material_line_count", 0)
    mat_isinv = inv.get("material_lines_IsInventory", 0)
    if mat_total <= 0 or mat_isinv is None:
        return findings
    pct = (100 * mat_isinv) // mat_total
    line = (
        f"Invoice IsInventory lines: {mat_isinv} of {mat_total} material lines ({pct}%) are IsInventory."
    )
    if pct >= INVOICE_MATERIAL_LINES_ISINVENTORY_GOOD_MIN_PCT:
        findings.append(_f(area, "green", line))
    elif pct >= INVOICE_MATERIAL_LINES_ISINVENTORY_OKAY_MIN_PCT:
        target = (mat_total * INVOICE_MATERIAL_LINES_ISINVENTORY_GOOD_MIN_PCT + 99) // 100
        findings.append(_f(area, "yellow", line + f" Convert {target - mat_isinv} more line(s) to IsInventory to reach Good ({INVOICE_MATERIAL_LINES_ISINVENTORY_GOOD_MIN_PCT}%+)."))
    elif pct >= INVOICE_MATERIAL_LINES_ISINVENTORY_REVIEW_MIN_PCT:
        target = (mat_total * INVOICE_MATERIAL_LINES_ISINVENTORY_OKAY_MIN_PCT + 99) // 100
        findings.append(_f(area, "review", line + f" Convert {target - mat_isinv} more line(s) to IsInventory to reach Okay ({INVOICE_MATERIAL_LINES_ISINVENTORY_OKAY_MIN_PCT}%+)."))
    else:
        target = (mat_total * INVOICE_MATERIAL_LINES_ISINVENTORY_REVIEW_MIN_PCT + 99) // 100
        findings.append(_f(area, "red", line + f" Convert {target - mat_isinv} more line(s) to IsInventory to reach Needs Review ({INVOICE_MATERIAL_LINES_ISINVENTORY_REVIEW_MIN_PCT}%+)."))
    return findings


def check_invoicing_zero_cost(results: dict, lookback_days: int) -> list[Finding]:
    """Zero-cost IsInventory lines as a % of all IsInventory lines."""
    findings: list[Finding] = []
    area = "Invoicing"
    inv = results.get("invoice_materials", {})
    mat_isinv = inv.get("material_lines_IsInventory", 0)
    if not mat_isinv or mat_isinv <= 0:
        return findings
    zero_cost = inv.get("material_lines_zero_cost", 0)
    pct = (100 * zero_cost) // mat_isinv
    base = f"Zero-cost IsInventory lines: {zero_cost} of {mat_isinv} ({pct}%)."
    if pct < INVOICE_ZERO_COST_GOOD_MAX_PCT:
        findings.append(_f(area, "green", base))
    elif pct < INVOICE_ZERO_COST_OKAY_MAX_PCT:
        target_zero = (mat_isinv * INVOICE_ZERO_COST_GOOD_MAX_PCT) // 100
        findings.append(_f(area, "yellow", base + f" Fix {zero_cost - target_zero} line(s) to reach Good (under {INVOICE_ZERO_COST_GOOD_MAX_PCT}%)."))
    elif pct < INVOICE_ZERO_COST_REVIEW_MAX_PCT:
        target_zero = (mat_isinv * INVOICE_ZERO_COST_OKAY_MAX_PCT) // 100
        findings.append(_f(area, "review", base + f" Fix {zero_cost - target_zero} line(s) to reach Okay (under {INVOICE_ZERO_COST_OKAY_MAX_PCT}%). Review cost flow from PO receiving."))
    else:
        target_zero = (mat_isinv * INVOICE_ZERO_COST_REVIEW_MAX_PCT) // 100
        findings.append(_f(area, "red", base + f" Fix {zero_cost - target_zero} line(s) to reach Needs Review (under {INVOICE_ZERO_COST_REVIEW_MAX_PCT}%). Review cost flow from PO receiving."))
    return findings


# ---------------------------------------------------------------------------
# Technician usage check
# ---------------------------------------------------------------------------

def check_tech_usage(results: dict, lookback_days: int) -> list[Finding]:
    """% of invoice material lines added by a technician."""
    findings: list[Finding] = []
    area = "Invoicing"
    inv = results.get("invoice_materials", {})
    mat_lines = inv.get("material_line_count", 0)
    added_by_tech = inv.get("material_lines_added_by_technician", 0)
    if mat_lines <= 0:
        findings.append(_f(area, "red", "No invoice material lines found; technician usage cannot be assessed."))
        return findings
    pct = (100 * added_by_tech) // mat_lines
    line = (
        f"Technician-added materials: {added_by_tech} of {mat_lines} invoice material line(s) ({pct}%) added by a technician."
    )
    if pct >= INVOICE_TECH_ADDED_GOOD_MIN_PCT:
        findings.append(_f(area, "green", line))
    elif pct >= INVOICE_TECH_ADDED_OKAY_MIN_PCT:
        target = (mat_lines * INVOICE_TECH_ADDED_GOOD_MIN_PCT + 99) // 100
        findings.append(_f(area, "yellow", line + f" Reach {target}+ tech-added lines ({INVOICE_TECH_ADDED_GOOD_MIN_PCT}%) to reach Good."))
    elif pct >= INVOICE_TECH_ADDED_REVIEW_MIN_PCT:
        target = (mat_lines * INVOICE_TECH_ADDED_OKAY_MIN_PCT + 99) // 100
        findings.append(_f(area, "review", line + f" Reach {target}+ tech-added lines ({INVOICE_TECH_ADDED_OKAY_MIN_PCT}%) to reach Okay."))
    else:
        target = (mat_lines * INVOICE_TECH_ADDED_REVIEW_MIN_PCT + 99) // 100
        findings.append(_f(area, "red", line + f" Reach {target}+ tech-added lines ({INVOICE_TECH_ADDED_REVIEW_MIN_PCT}%) to reach Needs Review."))
    return findings


# ---------------------------------------------------------------------------
# Replenishment checks
# ---------------------------------------------------------------------------

def check_replenishment(results: dict, lookback_days: int) -> list[Finding]:
    """Replenishment open/completed rate and aging requests."""
    findings: list[Finding] = []
    area = "Replenishment"
    repl = results.get("replenishment_summary", {})
    repl_open = repl.get("open_count", 0)
    repl_completed = repl.get("completed_in_lookback", 0)
    msg = f"Replenishment: {repl_open} open, {repl_completed} completed in last {lookback_days} days."

    if repl_completed > 0:
        rate_pct = 100 * (1 - (repl_open / repl_completed))
        if rate_pct >= REPLENISHMENT_RATE_GOOD_MIN_PCT:
            findings.append(_f(area, "green", msg))
        elif rate_pct >= REPLENISHMENT_RATE_OKAY_MIN_PCT:
            target_open = (repl_completed * (100 - REPLENISHMENT_RATE_GOOD_MIN_PCT)) // 100
            findings.append(_f(area, "yellow", msg + f" Reduce open to {target_open} or fewer to reach Good."))
        elif rate_pct >= REPLENISHMENT_RATE_REVIEW_MIN_PCT:
            target_open = (repl_completed * (100 - REPLENISHMENT_RATE_OKAY_MIN_PCT)) // 100
            findings.append(_f(area, "review", msg + f" Reduce open to {target_open} or fewer to reach Okay."))
        else:
            target_open = (repl_completed * (100 - REPLENISHMENT_RATE_REVIEW_MIN_PCT)) // 100
            findings.append(_f(area, "red", msg + f" Reduce open to {target_open} or fewer to reach Needs Review."))
    elif repl_open > 0:
        findings.append(_f(area, "red", msg + " Complete open replenishments before a rate can be measured."))
    else:
        findings.append(_f(area, "red", msg + " No replenishment activity in lookback period."))

    uc = results.get("usage_checks")
    if uc and isinstance(uc, dict):
        repl_30 = uc.get("replenishment_older_than_30_days", 0)
        if repl_30 > USAGE_REPLENISHMENT_OLD_30D_MAX:
            findings.append(_f(area, "red", f"Replenishment requests older than 30 days: {repl_30}. Address aging requests."))

    return findings


# ---------------------------------------------------------------------------
# Returns checks
# ---------------------------------------------------------------------------

def check_returns(results: dict, lookback_days: int) -> list[Finding]:
    """Returns credit-received rate and aging pending returns."""
    findings: list[Finding] = []
    area = "Returns"
    ret_by_status = results.get("returns_by_status", {})
    ret_received = ret_by_status.get(RETURN_CREDIT_RECEIVED_STATUS, 0)
    total_pending = results.get("total_pending_returns", 0)
    pending_over_90 = results.get("pending_returns_over_90_days", 0)
    ret_activity = results.get("returns_activity") or {}
    returns_in_period = ret_activity.get("returns_in_period", 0)

    msg = f"Returns: {ret_received} credit received of {returns_in_period} in last {lookback_days} days. {total_pending} pending."
    if returns_in_period > 0 and total_pending > 0:
        pct_pending = (100 * total_pending) // returns_in_period
        msg += f" ({pct_pending}% of period returns still pending)"
    if pending_over_90 > 0:
        msg += f"; {pending_over_90} older than 90 days."

    if pending_over_90 > 0:
        findings.append(_f(area, "yellow", msg + " Resolve aged returns to reach Good."))
    elif returns_in_period > 0 and total_pending > 0:
        pct_pending = (100 * total_pending) // returns_in_period
        if pct_pending <= RETURN_PENDING_PCT_GOOD_MAX:
            findings.append(_f(area, "green", msg))
        elif pct_pending <= RETURN_PENDING_PCT_OKAY_MAX:
            target_pending = (returns_in_period * RETURN_PENDING_PCT_GOOD_MAX) // 100
            findings.append(_f(area, "yellow", msg + f" Resolve {total_pending - target_pending} return(s) to reach Good ({RETURN_PENDING_PCT_GOOD_MAX}% or fewer pending)."))
        elif pct_pending <= RETURN_PENDING_PCT_REVIEW_MAX:
            target_pending = (returns_in_period * RETURN_PENDING_PCT_OKAY_MAX) // 100
            findings.append(_f(area, "review", msg + f" Resolve {total_pending - target_pending} return(s) to reach Okay ({RETURN_PENDING_PCT_OKAY_MAX}% or fewer pending)."))
        else:
            target_pending = (returns_in_period * RETURN_PENDING_PCT_REVIEW_MAX) // 100
            findings.append(_f(area, "red", msg + f" Resolve {total_pending - target_pending} return(s) to reach Needs Review ({RETURN_PENDING_PCT_REVIEW_MAX}% or fewer pending)."))
    elif total_pending > 0:
        findings.append(_f(area, "yellow", msg + " Resolve pending returns."))
    elif returns_in_period == 0:
        findings.append(_f(area, "red", msg + " No returns activity in lookback period."))
    else:
        findings.append(_f(area, "green", msg))

    return findings


# ---------------------------------------------------------------------------
# Pricebook & setup checks (full audit — combined area)
# ---------------------------------------------------------------------------

def check_setup(results: dict, lookback_days: int) -> list[Finding]:
    """Trucks/warehouses with templates; template item counts. Full audit only."""
    findings: list[Finding] = []
    area = "Pricebook & setup"
    setup = results.get("setup_data")
    if not setup or not isinstance(setup, dict):
        return findings

    truck_total = setup.get("truck_total", 0)
    truck_with_tpl = setup.get("truck_with_template", 0)
    wh_total = setup.get("warehouse_total", 0)
    wh_with_tpl = setup.get("warehouse_with_template", 0)
    templates_under = setup.get("templates_under_20_active_items", 0)

    if truck_total > 0:
        truck_pct = (100 * truck_with_tpl) // truck_total
        if truck_pct >= TRUCK_TEMPLATE_PCT_MIN:
            findings.append(_f(area, "green", f"Trucks: {truck_with_tpl} of {truck_total} have an inventory template."))
        else:
            need = ((truck_total * TRUCK_TEMPLATE_PCT_MIN + 99) // 100) - truck_with_tpl
            findings.append(_f(area, "red", f"Trucks: {truck_with_tpl} of {truck_total} have an inventory template. Assign templates to {need} more truck(s) to reach Good."))

    if wh_total > 0:
        if wh_with_tpl < WAREHOUSE_WITH_TEMPLATE_MIN:
            findings.append(_f(area, "red", f"Warehouses: {wh_with_tpl} of {wh_total} have an inventory template. Assign a template to at least {WAREHOUSE_WITH_TEMPLATE_MIN} warehouse."))
        else:
            findings.append(_f(area, "green", f"Warehouses: {wh_with_tpl} of {wh_total} have an inventory template."))

    if templates_under > 0:
        findings.append(_f(area, "red", f"{templates_under} template(s) have fewer than {TEMPLATE_MIN_ACTIVE_ITEMS} active items. Add items or replace with a complete template."))
    elif truck_total + wh_total > 0:
        findings.append(_f(area, "green", f"All templates have at least {TEMPLATE_MIN_ACTIVE_ITEMS} active items."))

    return findings


def check_unused_materials(results: dict, lookback_days: int) -> list[Finding]:
    """IsInventory materials with no invoice usage in the lookback window."""
    findings: list[Finding] = []
    area = "Pricebook & setup"
    isinv = (results.get("isinventory_counts") or {})
    mat_isinv_total = isinv.get("materials_isinventory_count", 0)
    inv = results.get("invoice_materials", {})
    distinct_used = inv.get("distinct_IsInventory_materials_used_90d", 0)

    if mat_isinv_total <= 0 or distinct_used is None:
        return findings
    unused = mat_isinv_total - distinct_used
    if unused <= 0:
        return findings
    pct = (100 * unused) // mat_isinv_total
    line = f"IsInventory materials unused in last {lookback_days} days: {unused} of {mat_isinv_total} ({pct}%)."
    if pct >= MATERIALS_UNUSED_90D_RED_MIN_PCT:
        findings.append(_f(area, "red", line + f" Reduce unused below {MATERIALS_UNUSED_90D_RED_MIN_PCT}% to reach Yellow — archive pricebook items that are no longer used."))
    elif pct > MATERIALS_UNUSED_90D_YELLOW_MAX_PCT:
        findings.append(_f(area, "yellow", line + f" Reduce unused to {MATERIALS_UNUSED_90D_YELLOW_MAX_PCT}% or fewer to reach Good — review pricebook for low-use items."))
    else:
        findings.append(_f(area, "green", line))
    return findings


# ---------------------------------------------------------------------------
# Transfers checks
# ---------------------------------------------------------------------------

def check_transfers(results: dict, lookback_days: int) -> list[Finding]:
    """Aging pending transfers and completed transfer volume vs expected."""
    findings: list[Finding] = []
    area = "Transfers"
    uc = results.get("usage_checks")
    if not uc or not isinstance(uc, dict):
        return findings

    trans_14 = uc.get("pending_transfers_older_than_14_days", 0)
    completed_transfers = uc.get("completed_transfers_in_90_days", 0)
    setup = results.get("setup_data") or {}
    truck_total = setup.get("truck_total", 0)
    expected_min = max(0, int(truck_total * TRANSFER_EXPECTED_TRUCK_FRACTION * (lookback_days / 7))) if truck_total else 0

    if trans_14 > USAGE_TRANSFERS_OLD_14D_MAX:
        findings.append(_f(area, "red", f"Pending transfers older than 14 days: {trans_14}. Complete or cancel aging transfers."))
    else:
        findings.append(_f(area, "green", f"Pending transfers older than 14 days: {trans_14}."))

    if truck_total > 0:
        if completed_transfers >= expected_min:
            findings.append(_f(area, "green",
                f"Completed transfers in last {lookback_days} days: {completed_transfers} (expected {expected_min}+)."))
        else:
            findings.append(_f(area, "red",
                f"Completed transfers in last {lookback_days} days: {completed_transfers} (expected {expected_min}+). Increase transfer usage."))

    return findings


# ---------------------------------------------------------------------------
# Counts and adjustments checks
# ---------------------------------------------------------------------------

def check_counts(results: dict, lookback_days: int) -> list[Finding]:
    """Past-due counts, negative balances, direct adjustments, warehouses missing recent count."""
    findings: list[Finding] = []
    area = "Counts and adjustments"
    uc = results.get("usage_checks")
    if not uc or not isinstance(uc, dict):
        return findings

    past_due = uc.get("past_due_inventory_counts", 0)
    neg_bal = uc.get("negative_balance_count", 0)
    direct_adj = uc.get("direct_adjustments_in_90_days", 0)
    wh_no_count = uc.get("warehouses_no_completed_count_90d", 0)
    setup = results.get("setup_data") or {}

    if past_due > USAGE_PAST_DUE_COUNTS_MAX:
        findings.append(_f(area, "red", f"Past due inventory counts: {past_due}. Complete or reschedule counts."))
    else:
        findings.append(_f(area, "green", f"Past due inventory counts: {past_due}."))

    if neg_bal > 0:
        findings.append(_f(area, "red", f"Negative inventory balances: {neg_bal} location/SKU combination(s). Run a count or adjustment to resolve."))

    if direct_adj > USAGE_DIRECT_ADJUSTMENTS_MAX:
        findings.append(_f(area, "red", f"Direct (quantity) adjustments in last 90 days: {direct_adj}. High volume may indicate process or data issues."))
    else:
        findings.append(_f(area, "green", f"Direct (quantity) adjustments in last 90 days: {direct_adj}."))

    if wh_no_count > WAREHOUSES_NO_COUNT_90D_MAX:
        findings.append(_f(area, "red", f"Warehouses with no completed count in last 90 days: {wh_no_count}. Schedule and complete cycle counts."))
    elif setup.get("warehouse_total", 0) > 0:
        findings.append(_f(area, "green", "All warehouses have had a completed count in the last 90 days."))

    return findings


# ---------------------------------------------------------------------------
# Other / requisitions check
# ---------------------------------------------------------------------------

def check_other(results: dict, lookback_days: int) -> list[Finding]:
    """Aging item requisitions (flagged when ≥ threshold)."""
    findings: list[Finding] = []
    area = "Other"
    uc = results.get("usage_checks")
    if not uc or not isinstance(uc, dict):
        return findings
    req_90 = uc.get("requisitions_older_than_90_days", 0)
    if req_90 >= USAGE_REQUISITIONS_OLD_90D_MAX:
        findings.append(_f(area, "red", f"Requisitions older than 90 days: {req_90}. Resolve or close aging requisitions."))
    else:
        findings.append(_f(area, "green", f"Requisitions older than 90 days: {req_90}."))
    return findings


# ---------------------------------------------------------------------------
# Pricebook readiness check (purchasing-only audit)
# ---------------------------------------------------------------------------

def check_pricebook_readiness(results: dict, lookback_days: int) -> list[Finding]:
    """Purchasing-only: pricebook zero-cost % and Default Replenishment vendor % (area='Pricebook')."""
    findings: list[Finding] = []
    area = "Pricebook"
    pb = results.get("pricebook", {})
    mat_count = pb.get("material_count", 0)
    zero_cost = pb.get("materials_zero_cost", 0)
    def_repl = pb.get("primary_vendor_default_replenishment", 0)

    if mat_count == 0:
        findings.append(_f(area, "red", "Pricebook has no materials. Add materials before starting inventory implementation."))
        return findings

    zero_pct = zero_cost / mat_count
    if zero_cost > 0 and zero_pct > PRICEBOOK_RED_PCT:
        findings.append(_f(area, "red", f"{zero_cost} material(s) ({zero_pct:.0%}) have $0 cost. Assign costs before inventory go-live."))
    elif zero_cost > 0:
        findings.append(_f(area, "green", f"{zero_cost} material(s) have $0 cost ({zero_pct:.1%}) — within acceptable range."))
    else:
        findings.append(_f(area, "green", "All materials have a cost assigned."))

    def_repl_pct = def_repl / mat_count
    if def_repl > 0 and def_repl_pct > PRICEBOOK_RED_PCT:
        findings.append(_f(area, "red", f"{def_repl} material(s) ({def_repl_pct:.0%}) use Default or Imported Default Replenishment as primary vendor. Assign a real vendor before go-live."))
    elif def_repl > 0:
        findings.append(_f(area, "green", f"{def_repl} material(s) use Default/Imported Default Replenishment as primary ({def_repl_pct:.1%}) — within acceptable range."))
    else:
        findings.append(_f(area, "green", "No materials use Default or Imported Default Replenishment Vendor as primary."))

    return findings


# ---------------------------------------------------------------------------
# Check registries
# These lists are THE source-of-truth for what runs in each audit mode.
# Add, remove, or reorder checks here.
# ---------------------------------------------------------------------------

FULL_AUDIT_CHECKS: list[CheckFn] = [
    # Purchasing
    check_pending_pos,
    check_po_usage,
    check_po_line_quality,
    # Invoicing (IsInventory-aware)
    check_invoicing_coverage,
    check_invoicing_isinventory_lines,
    check_invoicing_zero_cost,
    # Technician usage (under Invoicing)
    check_tech_usage,
    # Replenishment
    check_replenishment,
    # Returns
    check_returns,
    # Pricebook & setup (templates + unused materials)
    check_setup,
    check_unused_materials,
    # Transfers
    check_transfers,
    # Counts and adjustments
    check_counts,
    # Other (requisitions)
    check_other,
]

PURCHASING_ONLY_CHECKS: list[CheckFn] = [
    # Pricebook readiness
    check_pricebook_readiness,
    # Purchasing
    check_pending_pos,
    check_po_usage,
    check_po_line_quality,
    # Replenishment
    check_replenishment,
    # Returns
    check_returns,
    # Invoicing
    check_tech_usage,
]
