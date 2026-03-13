"""
Parse raw audit data (from data.py) into a structured results dict for evaluate_audit().
Also contains readiness helpers (go-live check, is_live_with_inventory).
"""
from __future__ import annotations

import json
from datetime import date, datetime

from audit.constants import (
    PENDING_STATUSES,
    COMPLETED_STATUSES,
    SETTINGS_WE_CARE_ABOUT,
    INVENTORY_SETTING_LABELS,
    INVENTORY_VALUATION_NAMES,
    TRACKING_DISPOSITION_NAMES,
    PO_APPROVAL_FIELD_NAMES,
    REQUISITION_DATE_NEEDED_NAMES,
    PO_ITEM_COST_COPY_NAMES,
    TRUCK_TEMPLATE_PCT_MIN,
    WAREHOUSE_WITH_TEMPLATE_MIN,
    TEMPLATE_MIN_ACTIVE_ITEMS,
    GO_LIVE_ITEMS_INVENTORY_MIN_PCT,
    READINESS_AREAS,
)


def _int(v) -> int:
    if v is None:
        return 0
    if isinstance(v, int):
        return v
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def parse_results(data: dict) -> dict:
    """Parse combined audit data (10 result sets) into a flat results dict for evaluate_audit."""
    results: dict = {}

    # Tenant info: v1=tenant_id, v2=tenant_name
    ti = data.get("tenant_info")
    if ti is not None and isinstance(ti, list) and len(ti) >= 1:
        row = ti[0]
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            results["tenant_id"] = row[0] if row[0] is not None and str(row[0]).strip() != "" else None
            results["tenant_name"] = (str(row[1]).strip() or None) if row[1] is not None else None
            if results["tenant_id"] is not None:
                results["tenant_id"] = _int(results["tenant_id"])

    # Pricebook: v1=material_count, v2=with_cost, v3=zero_cost, v4=with_vendor_link,
    #            v5=with_primary_vendor, v6=primary_default_replenishment
    pb = data.get("pricebook")
    if pb is not None and isinstance(pb, list) and len(pb) >= 1:
        row = pb[0]
        if isinstance(row, (list, tuple)) and len(row) >= 1:
            results["pricebook"] = {
                "material_count": _int(row[0]) if len(row) > 0 else 0,
                "materials_with_cost": _int(row[1]) if len(row) > 1 else 0,
                "materials_zero_cost": _int(row[2]) if len(row) > 2 else 0,
                "materials_with_vendor_link": _int(row[3]) if len(row) > 3 else 0,
                "materials_with_primary_vendor": _int(row[4]) if len(row) > 4 else 0,
                "primary_vendor_default_replenishment": _int(row[5]) if len(row) > 5 else 0,
            }
    if "pricebook" not in results:
        results["pricebook"] = {}

    # Purchase orders summary:
    # v1=total_pending, v2=po_created_in_period, v3=earliest, v4=latest,
    # v5..v11=status_0..6, v12=po_count, v13=single_line_pos,
    # v14=total_lines, v15=placeholder_like, v16=pending_over_90
    pos = data.get("purchase_orders_summary")
    if pos is not None and isinstance(pos, list) and len(pos) >= 1:
        row = pos[0]
        if isinstance(row, (list, tuple)) and len(row) >= 11:
            results["total_pending_pos"] = _int(row[0])
            results["po_activity"] = {
                "po_created_in_period": _int(row[1]),
                "earliest_po": row[2] if len(row) > 2 else None,
                "latest_po": row[3] if len(row) > 3 else None,
            }
            by_status = {i: _int(row[4 + i]) for i in range(7) if 4 + i < len(row)}
            results["purchase_orders"] = {
                "by_status": by_status,
                "pending_count": sum(by_status.get(s, 0) for s in PENDING_STATUSES),
                "completed_count": sum(by_status.get(s, 0) for s in COMPLETED_STATUSES),
            }
            results["po_line_quality"] = {
                "po_count": _int(row[11]) if len(row) > 11 else 0,
                "pos_with_one_line_only": _int(row[12]) if len(row) > 12 else 0,
                "total_line_items": _int(row[13]) if len(row) > 13 else 0,
                "line_items_placeholder_like": _int(row[14]) if len(row) > 14 else 0,
            }
            results["pending_pos_over_90_days"] = _int(row[15]) if len(row) > 15 else 0
    if "total_pending_pos" not in results:
        results["total_pending_pos"] = 0
    if "po_activity" not in results:
        results["po_activity"] = {}
    if "purchase_orders" not in results:
        results["purchase_orders"] = {"by_status": {}, "pending_count": 0, "completed_count": 0}
    if "po_line_quality" not in results:
        results["po_line_quality"] = {}
    if "pending_pos_over_90_days" not in results:
        results["pending_pos_over_90_days"] = 0

    # Invoice materials:
    # v1..v6 = line count, invoice count, tech-added, placeholder,
    #          invoices_gt_zero, invoices_gt_zero_with_material
    # v7..v10 = IsInventory line count, zero-cost, from transfer, distinct materials used
    inv = data.get("invoice_materials")
    if inv is not None and isinstance(inv, list) and len(inv) >= 1:
        row = inv[0]
        if isinstance(row, (list, tuple)):
            results["invoice_materials"] = {
                "material_line_count": _int(row[0]) if len(row) > 0 else 0,
                "invoices_with_materials": _int(row[1]) if len(row) > 1 else 0,
                "material_lines_added_by_technician": _int(row[2]) if len(row) > 2 else 0,
                "material_lines_placeholder_like": _int(row[3]) if len(row) > 3 else 0,
                "invoices_total_gt_zero": _int(row[4]) if len(row) > 4 else 0,
                "invoices_gt_zero_with_material": _int(row[5]) if len(row) > 5 else 0,
                "material_lines_IsInventory": _int(row[6]) if len(row) > 6 else 0,
                "material_lines_zero_cost": _int(row[7]) if len(row) > 7 else 0,
                "material_lines_from_transfer": _int(row[8]) if len(row) > 8 else 0,
                "distinct_IsInventory_materials_used_90d": _int(row[9]) if len(row) > 9 else 0,
            }
    if "invoice_materials" not in results:
        results["invoice_materials"] = {}

    # Replenishment: v1=open, v2=completed in lookback, v3=used_materials_can_be_replenished
    repl = data.get("replenishment_summary")
    if repl is not None and isinstance(repl, list) and len(repl) >= 1:
        row = repl[0]
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            results["replenishment_summary"] = {
                "open_count": _int(row[0]),
                "completed_in_lookback": _int(row[1]),
                "used_materials_can_be_replenished": _int(row[2]) if len(row) >= 3 else 0,
            }
    if "replenishment_summary" not in results:
        results["replenishment_summary"] = {
            "open_count": 0,
            "completed_in_lookback": 0,
            "used_materials_can_be_replenished": 0,
        }

    # Returns: v1=total_pending, v2=in_period, v3=earliest, v4=latest,
    #          v5..v8=status_0..3, v9=pending_over_90_days
    rets = data.get("returns_summary")
    if rets is not None and isinstance(rets, list) and len(rets) >= 1:
        row = rets[0]
        if isinstance(row, (list, tuple)) and len(row) >= 5:
            results["total_pending_returns"] = _int(row[0])
            results["returns_activity"] = {
                "returns_in_period": _int(row[1]),
                "earliest_return": row[2] if len(row) > 2 else None,
                "latest_return": row[3] if len(row) > 3 else None,
            }
            results["returns_by_status"] = {i: _int(row[4 + i]) for i in range(4) if 4 + i < len(row)}
            if len(row) >= 9:
                results["pending_returns_over_90_days"] = _int(row[8])
    if "total_pending_returns" not in results:
        results["total_pending_returns"] = 0
    if "returns_by_status" not in results:
        results["returns_by_status"] = {}
    if "pending_returns_over_90_days" not in results:
        results["pending_returns_over_90_days"] = 0

    # Assessment: v1..v7 = purchasing_on, inventory_on, active_mats, active_eq,
    #             mats_isinventory, eq_isinventory, tracking_start_date
    # v8..v14 = feature gates (7 flags)
    # v15 = materials_with_unit_of_measure
    # v16 = equipment_serialized_count
    ad = data.get("assessment_data")
    if ad is not None and isinstance(ad, list) and len(ad) >= 1:
        row = ad[0]
        if isinstance(row, (list, tuple)) and len(row) >= 5:
            results["readiness_config"] = {
                "purchasing_module_on": bool(_int(row[0])),
                "inventory_module_on": bool(_int(row[1])),
            }
            results["isinventory_counts"] = {
                "active_materials_count": _int(row[2]) if len(row) > 2 else 0,
                "active_equipment_count": _int(row[3]) if len(row) > 3 else 0,
                "materials_isinventory_count": _int(row[4]) if len(row) > 4 else 0,
                "equipment_isinventory_count": _int(row[5]) if len(row) > 5 else 0,
            }
            results["inventory_tracking_start_date"] = (
                (str(row[6] or "").strip() or None) if len(row) > 6 else None
            )
            if len(row) >= 15:
                results["feature_gates"] = {
                    "item_requisitions": bool(_int(row[7])),
                    "requisition_closeout": bool(_int(row[8])),
                    "install_requisitions": bool(_int(row[9])),
                    "transfers_to_jobs": bool(_int(row[10])),
                    "consignment": bool(_int(row[11])),
                    "purchase_approval_workflow": not bool(_int(row[12])),
                    "granular_wac": bool(_int(row[13])),
                }
                results["materials_with_unit_of_measure"] = _int(row[14])
            if len(row) >= 16:
                results["equipment_serialized_count"] = _int(row[15])
    if "readiness_config" not in results:
        results["readiness_config"] = {}
    if "isinventory_counts" not in results:
        results["isinventory_counts"] = {}
    if "inventory_tracking_start_date" not in results:
        results["inventory_tracking_start_date"] = None
    if "feature_gates" not in results:
        results["feature_gates"] = {}
    if "materials_with_unit_of_measure" not in results:
        results["materials_with_unit_of_measure"] = 0
    if "equipment_serialized_count" not in results:
        results["equipment_serialized_count"] = 0

    # Inventory settings: v1 = full JSON blob from NamedValue (Inventory.Configuration)
    inv_set = data.get("inventory_settings")
    if inv_set is not None and isinstance(inv_set, list) and len(inv_set) >= 1:
        row = inv_set[0]
        if isinstance(row, (list, tuple)) and len(row) > 0 and row[0]:
            raw = str(row[0]).strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                    results["inventory_settings"] = parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    results["inventory_settings"] = None
    if "inventory_settings" not in results:
        results["inventory_settings"] = None

    # Setup data: v1=truck_total, v2=truck_with_template, v3=warehouse_total,
    #             v4=warehouse_with_template, v5=templates_under_20_active_items
    setup = data.get("setup_data")
    if setup is not None and isinstance(setup, list) and len(setup) >= 1:
        row = setup[0]
        if isinstance(row, (list, tuple)) and len(row) >= 5:
            results["setup_data"] = {
                "truck_total": _int(row[0]),
                "truck_with_template": _int(row[1]),
                "warehouse_total": _int(row[2]),
                "warehouse_with_template": _int(row[3]),
                "templates_under_20_active_items": _int(row[4]),
            }
    if "setup_data" not in results:
        results["setup_data"] = None

    # Usage checks:
    # v1=repl_old_30d, v2=transfers_old_14d, v3=requisitions_old_90d,
    # v4=past_due_counts, v5=negative_balances, v6=direct_adj_90d,
    # v7=warehouses_no_count_90d, v8=completed_transfers_90d
    uc = data.get("usage_checks")
    if uc is not None and isinstance(uc, list) and len(uc) >= 1:
        row = uc[0]
        if isinstance(row, (list, tuple)) and len(row) >= 6:
            results["usage_checks"] = {
                "replenishment_older_than_30_days": _int(row[0]),
                "pending_transfers_older_than_14_days": _int(row[1]),
                "requisitions_older_than_90_days": _int(row[2]),
                "past_due_inventory_counts": _int(row[3]),
                "negative_balance_count": _int(row[4]),
                "direct_adjustments_in_90_days": _int(row[5]),
                "warehouses_no_completed_count_90d": _int(row[6]) if len(row) > 6 else 0,
                "completed_transfers_in_90_days": _int(row[7]) if len(row) > 7 else 0,
            }
    if "usage_checks" not in results:
        results["usage_checks"] = None

    return results


def is_live_with_inventory(results: dict) -> bool:
    """True if inventory tracking start date (BeginningDate) is today or in the past."""
    start = results.get("inventory_tracking_start_date")
    if not start:
        return False
    s = str(start).strip()[:10]
    if len(s) < 10:
        return False
    try:
        return datetime.strptime(s, "%Y-%m-%d").date() <= date.today()
    except (ValueError, TypeError):
        return False


def _is_preparing_for_go_live(results: dict, is_live: bool) -> bool:
    """True when not live but inventory module is on, has IsInventory items, and has templates."""
    if is_live:
        return False
    cfg = results.get("readiness_config") or {}
    if not cfg.get("inventory_module_on"):
        return False
    isinv = results.get("isinventory_counts") or {}
    if _int(isinv.get("materials_isinventory_count")) == 0 and _int(isinv.get("equipment_isinventory_count")) == 0:
        return False
    setup = results.get("setup_data")
    if not setup or not isinstance(setup, dict):
        return False
    return _int(setup.get("truck_with_template")) > 0 or _int(setup.get("warehouse_with_template")) > 0


def _go_live_readiness(results: dict) -> tuple[bool, list[str]]:
    """Check whether ready for go-live. Returns (ready, list_of_blockers)."""
    isinv = results.get("isinventory_counts") or {}
    setup = results.get("setup_data") or {}
    active_mats = _int(isinv.get("active_materials_count"))
    mat_isinv = _int(isinv.get("materials_isinventory_count"))
    truck_total = _int(setup.get("truck_total"))
    truck_with_tpl = _int(setup.get("truck_with_template"))
    wh_total = _int(setup.get("warehouse_total"))
    wh_with_tpl = _int(setup.get("warehouse_with_template"))
    templates_under_20 = _int(setup.get("templates_under_20_active_items"))

    needs: list[str] = []
    if active_mats > 0:
        pct = (100 * mat_isinv) / active_mats
        if pct < GO_LIVE_ITEMS_INVENTORY_MIN_PCT:
            needs.append(
                f"Mark at least half of pricebook materials as inventory "
                f"(currently {mat_isinv} of {active_mats}, {pct:.0f}%)."
            )
    else:
        needs.append("Mark at least half of pricebook materials as inventory.")
    if truck_total > 0:
        truck_pct = (100 * truck_with_tpl) / truck_total
        if truck_pct < TRUCK_TEMPLATE_PCT_MIN:
            needs.append(
                f"Assign inventory templates to at least 80% of trucks "
                f"(currently {truck_with_tpl} of {truck_total}, {truck_pct:.0f}%)."
            )
    if wh_total > 0 and wh_with_tpl < WAREHOUSE_WITH_TEMPLATE_MIN:
        needs.append("Assign an inventory template to at least one warehouse.")
    if templates_under_20 > 0:
        needs.append(
            f"Ensure all inventory templates have at least {TEMPLATE_MIN_ACTIVE_ITEMS} active items "
            f"({templates_under_20} template(s) have fewer)."
        )
    return (len(needs) == 0, needs)


def _readiness_areas_needing_work(findings_by_area: dict[str, dict[str, list[str]]]) -> list[str]:
    """Return list of READINESS_AREAS that have any red findings."""
    return [a for a in READINESS_AREAS if findings_by_area.get(a, {}).get("red")]


def _format_areas_for_message(areas: list[str]) -> str:
    """Format area names for a natural-language verdict: 'A', 'A and B', or 'A, B, and C'."""
    if not areas:
        return ""
    if len(areas) == 1:
        return areas[0]
    if len(areas) == 2:
        return f"{areas[0]} and {areas[1]}"
    return f"{areas[0]}, {areas[1]}, and {areas[2]}"


def format_inventory_settings(config: dict | None) -> list[str]:
    """Turn Inventory.Configuration JSON into readable lines (only SETTINGS_WE_CARE_ABOUT)."""
    if not config or not isinstance(config, dict):
        return []
    lines: list[str] = []
    seen_keys_lower: set[str] = set()
    for key in SETTINGS_WE_CARE_ABOUT:
        if key not in config:
            continue
        value = config[key]
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            continue
        key_lower = (key or "").lower()
        if key_lower in seen_keys_lower:
            continue
        seen_keys_lower.add(key_lower)
        label = INVENTORY_SETTING_LABELS.get(key, key[:1].upper() + key[1:] if key else key)
        if isinstance(value, bool):
            lines.append(f"    {label}: {'Yes' if value else 'No'}")
        elif key_lower == "beginningdate" and value:
            lines.append(f"    {label}: {str(value)[:10]}")
        elif key_lower == "inventoryvaluationmethod":
            lines.append(f"    {label}: {INVENTORY_VALUATION_NAMES.get(value, value)}")
        elif key_lower == "trackingdisposition":
            lines.append(f"    {label}: {TRACKING_DISPOSITION_NAMES.get(value, value)}")
        elif key_lower == "purchaseorderapprovalfield":
            lines.append(f"    {label}: {PO_APPROVAL_FIELD_NAMES.get(value, value)}")
        elif key_lower == "requisitiondateneededbytype":
            lines.append(f"    {label}: {REQUISITION_DATE_NEEDED_NAMES.get(value, value)}")
        elif key_lower == "poitemcostcopyoption":
            lines.append(f"    {label}: {PO_ITEM_COST_COPY_NAMES.get(value, value)}")
        else:
            lines.append(f"    {label}: {value}")
    return lines
