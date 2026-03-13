#!/usr/bin/env python3
"""
Inventory Setup / Usage Audit — CLI entrypoint.

Run `python audit_report.py --help` for usage.
All evaluation logic lives in the audit/ package.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from audit.constants import (
    AUDIT_AREAS,
    AUDIT_AREAS_PURCHASING,
    RESULT_KEYS,
    TEMPLATE_MIN_ACTIVE_ITEMS,
    TRUCK_TEMPLATE_PCT_MIN,
    WAREHOUSE_WITH_TEMPLATE_MIN,
)
from audit.data import (
    _int,
    _snowflake_conn,
    data_from_audit_rows,
    get_tenant_group_members,
    load_results_from_combined_csv,
    load_results_from_csv_folder,
    load_results_from_excel,
    load_results_from_snowflake,
)
from audit.evaluate import (
    _area_status,
    evaluate_audit,
    evaluate_audit_purchasing_only,
    get_action_plan,
)
from audit.parse import (
    _format_areas_for_message,
    _go_live_readiness,
    _is_preparing_for_go_live,
    _readiness_areas_needing_work,
    format_inventory_settings,
    is_live_with_inventory,
    parse_results,
)
from audit.render import render_group_summary_html, render_scorecard_html


def _sanitize_folder_name(s: str, max_len: int = 80) -> str:
    """Safe folder name: alphanumeric, underscore, hyphen only; collapse runs; strip."""
    if not s or not isinstance(s, str):
        return "report"
    name = re.sub(r"[^\w\-]+", "_", s.strip())
    name = re.sub(r"_+", "_", name).strip("_")
    return (name[:max_len] if len(name) > max_len else name) or "report"


# Load .env from project directory so SNOWFLAKE_* are set when using --from-snowflake
try:
    from dotenv import load_dotenv
    _script_dir = Path(__file__).resolve().parent
    load_dotenv(_script_dir / ".env")
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory Setup/Usage Audit: report on POs, invoices, and replenishment for tenants on the inventory module."
    )
    parser.add_argument("--tenant-id", type=int, default=None, help="Tenant ID for report header")
    parser.add_argument("--tenant-name", type=str, default=None, help="Tenant name for report header")
    parser.add_argument("--lookback-days", type=int, default=90, help="Lookback days (default 90)")
    parser.add_argument("--from-excel", type=str, default=None, metavar="FILE", help="Read from Excel (.xlsx) or CSV (combined 4-row export)")
    parser.add_argument("--from-csv-folder", type=str, default=None, metavar="FOLDER", help="Read from CSVs in a folder (purchase_orders_summary.csv, etc.)")
    parser.add_argument("--from-results", type=str, default=None, metavar="JSON_FILE", help="Read from a JSON file")
    parser.add_argument("--from-group-json", type=str, default=None, metavar="JSON_FILE", help="Read group audit results from JSON (see TENANT_GROUP_DISPLAY.md); requires --html for group summary path")
    parser.add_argument("--from-snowflake", action="store_true", help="Run the audit query in Snowflake (requires --tenant-id or --tenant-group; uses Okta via SNOWFLAKE_* env)")
    parser.add_argument("--tenant-group", type=str, default=None, metavar="NAME", help="Run audit for all tenants in this tenant group (requires --from-snowflake and --html)")
    parser.add_argument("--html", type=str, default=None, metavar="FILE", help="Write a customer-friendly HTML scorecard to FILE (for --tenant-group, write group summary here and scorecard_<id>.html alongside)")
    parser.add_argument("--output-aggregate", type=str, default=None, metavar="FILE", help="Merge this run into an aggregated JSON file (for hosted lookup by tenant). Use with single or group run.")
    args = parser.parse_args()

    data = None
    lookback = args.lookback_days

    # --- Group JSON mode: load pre-fetched audit rows (e.g. from MCP) and write group summary + per-tenant scorecards ---
    if args.from_group_json and args.html:
        path = Path(args.from_group_json)
        if not path.is_file():
            print(f"Group JSON file not found: {path}", file=sys.stderr)
            return 1
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Invalid JSON in {path}: {e}", file=sys.stderr)
            return 1
        group_name = raw.get("group_name") or "Tenant group"
        lookback = _int(raw.get("lookback_days")) or args.lookback_days
        tenants_in = raw.get("tenants") or []
        if not isinstance(tenants_in, list):
            print("Group JSON must have 'tenants' array.", file=sys.stderr)
            return 1
        base = Path(args.html).resolve().parent
        output_dir = base / _sanitize_folder_name(group_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        css_src = Path(__file__).resolve().parent / "css" / "scorecard.css"
        if css_src.is_file():
            (output_dir / "scorecard.css").write_text(css_src.read_text(encoding="utf-8"), encoding="utf-8")
        tenant_results = []
        for t_in in tenants_in:
            tid = _int(t_in.get("tenant_id"))
            tname = (t_in.get("tenant_name") or "").strip() or f"Tenant {tid}"
            rows = t_in.get("rows") or []
            if not rows:
                print(f"  Skipping {tname} (no rows).", file=sys.stderr)
                continue
            data = data_from_audit_rows(rows, lookback)
            results = parse_results(data)
            is_live = is_live_with_inventory(results)
            if is_live:
                ok, findings_by_area = evaluate_audit(results, lookback)
                audit_areas = AUDIT_AREAS
            else:
                ok, findings_by_area, ready_for_inventory = evaluate_audit_purchasing_only(results, lookback)
                audit_areas = AUDIT_AREAS_PURCHASING
            area_statuses = {}
            for area in AUDIT_AREAS:
                if not is_live and area not in audit_areas:
                    area_statuses[area] = "N/A"
                else:
                    area_statuses[area] = _area_status(findings_by_area.get(area, {"green": [], "yellow": [], "review": [], "red": []}))
            action_plan = get_action_plan(findings_by_area, audit_areas)
            group_folder = _sanitize_folder_name(group_name)
            tenant_results.append({
                "tenant_id": tid, "tenant_name": tname, "area_statuses": area_statuses, "ok": ok, "action_plan": action_plan,
                "results": results, "findings_by_area": findings_by_area, "is_live": is_live, "lookback_days": lookback,
                "scorecard_path": f"{group_folder}/scorecard_{tid}.html",
            })
            html_content = render_scorecard_html(tid, tname, lookback, results, findings_by_area, ok, audit_areas=audit_areas, is_live=is_live, ready_for_inventory_implementation=(ready_for_inventory if not is_live else None))
            (output_dir / f"scorecard_{tid}.html").write_text(html_content, encoding="utf-8")
        group_html = render_group_summary_html(group_name, tenant_results, lookback)
        (output_dir / "index.html").write_text(group_html, encoding="utf-8")
        print(f"Wrote group summary to {output_dir / 'index.html'} and {len(tenant_results)} scorecards to {output_dir}", file=sys.stderr)
        if args.output_aggregate and tenant_results:
            from audit.aggregate import merge_into_aggregate
            merge_into_aggregate(Path(args.output_aggregate), tenant_results, lookback)
            print(f"Merged {len(tenant_results)} tenants into {args.output_aggregate}", file=sys.stderr)
        return 0

    # --- Tenant group mode: run audit for each tenant in the group, then write group summary + per-tenant scorecards ---
    if args.tenant_group and args.from_snowflake and args.html:
        conn = _snowflake_conn()
        try:
            members = get_tenant_group_members(conn, args.tenant_group)
            if not members:
                print(f"No tenants found for group: {args.tenant_group}", file=sys.stderr)
                return 1
            base = Path(args.html).resolve().parent
            output_dir = base / _sanitize_folder_name(args.tenant_group)
            output_dir.mkdir(parents=True, exist_ok=True)
            css_src = Path(__file__).resolve().parent / "css" / "scorecard.css"
            if css_src.is_file():
                (output_dir / "scorecard.css").write_text(css_src.read_text(encoding="utf-8"), encoding="utf-8")
            tenant_results = []
            for i, (tenant_id, tenant_name) in enumerate(members):
                print(f"  [{i+1}/{len(members)}] {tenant_name} ({tenant_id}) ...", file=sys.stderr)
                data = load_results_from_snowflake(tenant_id, args.lookback_days, conn=conn)
                lookback = _int(data.get("lookback_days")) or args.lookback_days
                results = parse_results(data)
                is_live = is_live_with_inventory(results)
                if is_live:
                    ok, findings_by_area = evaluate_audit(results, lookback)
                    audit_areas = AUDIT_AREAS
                else:
                    ok, findings_by_area, ready_for_inventory = evaluate_audit_purchasing_only(results, lookback)
                    audit_areas = AUDIT_AREAS_PURCHASING
                area_statuses = {}
                for area in AUDIT_AREAS:
                    if not is_live and area not in audit_areas:
                        area_statuses[area] = "N/A"
                    else:
                        area_statuses[area] = _area_status(findings_by_area.get(area, {"green": [], "yellow": [], "review": [], "red": []}))
                action_plan = get_action_plan(findings_by_area, audit_areas)
                group_folder = _sanitize_folder_name(args.tenant_group)
                tenant_results.append({
                    "tenant_id": tenant_id,
                    "tenant_name": tenant_name,
                    "area_statuses": area_statuses,
                    "ok": ok,
                    "action_plan": action_plan,
                    "results": results,
                    "findings_by_area": findings_by_area,
                    "is_live": is_live,
                    "lookback_days": lookback,
                    "scorecard_path": f"{group_folder}/scorecard_{tenant_id}.html",
                })
                html_content = render_scorecard_html(tenant_id, tenant_name, lookback, results, findings_by_area, ok, audit_areas=audit_areas, is_live=is_live, ready_for_inventory_implementation=(ready_for_inventory if not is_live else None))
                (output_dir / f"scorecard_{tenant_id}.html").write_text(html_content, encoding="utf-8")
        finally:
            conn.close()
        group_html = render_group_summary_html(args.tenant_group, tenant_results, lookback)
        (output_dir / "index.html").write_text(group_html, encoding="utf-8")
        print(f"Wrote group summary to {output_dir / 'index.html'} and {len(tenant_results)} scorecards to {output_dir}", file=sys.stderr)
        if args.output_aggregate and tenant_results:
            from audit.aggregate import merge_into_aggregate
            merge_into_aggregate(Path(args.output_aggregate), tenant_results, lookback)
            print(f"Merged {len(tenant_results)} tenants into {args.output_aggregate}", file=sys.stderr)
        return 0

    if args.from_snowflake:
        tid = args.tenant_id
        if tid is None:
            print("--from-snowflake requires --tenant-id (or use --tenant-group for a group run).", file=sys.stderr)
            return 1
        data = load_results_from_snowflake(int(tid), args.lookback_days)
        lookback = _int(data.get("lookback_days")) or args.lookback_days
    elif args.from_csv_folder:
        folder = Path(args.from_csv_folder)
        if not folder.is_dir():
            print(f"CSV folder not found: {folder}", file=sys.stderr)
            return 1
        data = load_results_from_csv_folder(folder, args.lookback_days)
        lookback = _int(data.get("lookback_days")) or args.lookback_days
    elif args.from_excel:
        path = Path(args.from_excel)
        if not path.is_file():
            print(f"File not found: {path}", file=sys.stderr)
            return 1
        if path.suffix.lower() == ".csv":
            data = load_results_from_combined_csv(path, args.lookback_days)
        else:
            data = load_results_from_excel(path, args.lookback_days)
        lookback = _int(data.get("lookback_days")) or args.lookback_days
    elif args.from_results:
        path = Path(args.from_results)
        if not path.is_file():
            print(f"Results file not found: {path}", file=sys.stderr)
            return 1
        try:
            raw = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"Invalid JSON in {path}: {e}", file=sys.stderr)
            return 1
        data = raw.get("results", raw) if isinstance(raw, dict) else raw
        if not isinstance(data, dict):
            print("JSON must be an object (results dict).", file=sys.stderr)
            return 1
        lookback = _int(data.get("lookback_days")) or args.lookback_days

    if data is None:
        parser.print_help()
        print("\nTo run: set tenant_id in sql/00_combined_audit.sql, run in Snowflake, export to Excel/CSV, then use --from-excel. See README.", file=sys.stderr)
        return 1

    # CSV folder: each file has one or more data rows (header already skipped). Use first row per key; pad PO row to 16 cols for parse_results.
    if args.from_csv_folder and data:
        normalized = {"lookback_days": data.get("lookback_days", lookback)}
        for key in RESULT_KEYS:
            rows = data.get(key)
            if not rows or not isinstance(rows, list):
                continue
            row = rows[0] if rows else []
            if isinstance(row, (list, tuple)):
                need = 2 if key == "tenant_info" else (6 if key == "pricebook" else (16 if key == "purchase_orders_summary" else (10 if key == "invoice_materials" else (3 if key == "replenishment_summary" else (9 if key == "returns_summary" else (16 if key == "assessment_data" else (5 if key == "setup_data" else (8 if key == "usage_checks" else (1 if key == "inventory_settings" else 4)))))))))
                normalized[key] = [list(row) + [None] * max(0, need - len(row))]
            else:
                normalized[key] = [row]
        data = normalized

    results = parse_results(data)
    is_live = is_live_with_inventory(results)
    ready_for_inventory = None
    if is_live:
        ok, findings_by_area = evaluate_audit(results, lookback)
        audit_areas = AUDIT_AREAS
    else:
        ok, findings_by_area, ready_for_inventory = evaluate_audit_purchasing_only(results, lookback)
        audit_areas = AUDIT_AREAS_PURCHASING

    # --- Output: tenant, scorecard, Settings, Setup, then findings by area ---
    tenant_id = args.tenant_id if args.tenant_id is not None else results.get("tenant_id")
    tenant_name = args.tenant_name if args.tenant_name else results.get("tenant_name")

    if args.html:
        base = Path(args.html).resolve().parent
        folder_name = f"scorecard_{tenant_id or 0}_{_sanitize_folder_name(tenant_name or 'tenant')}"
        output_dir = base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        html_content = render_scorecard_html(tenant_id, tenant_name, lookback, results, findings_by_area, ok, audit_areas=audit_areas, is_live=is_live, ready_for_inventory_implementation=(ready_for_inventory if not is_live else None))
        (output_dir / "scorecard.html").write_text(html_content, encoding="utf-8")
        css_src = Path(__file__).resolve().parent / "css" / "scorecard.css"
        if css_src.is_file():
            (output_dir / "scorecard.css").write_text(css_src.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Wrote scorecard to {output_dir / 'scorecard.html'} and CSS to {output_dir}", file=sys.stderr)
        else:
            print(f"Wrote scorecard to {output_dir / 'scorecard.html'} (no css/scorecard.css found)", file=sys.stderr)

    if args.output_aggregate and data is not None:
        action_plan = get_action_plan(findings_by_area, audit_areas)
        area_statuses_single = {}
        for area in AUDIT_AREAS:
            if not is_live and area not in audit_areas:
                area_statuses_single[area] = "N/A"
            else:
                area_statuses_single[area] = _area_status(findings_by_area.get(area, {"green": [], "yellow": [], "review": [], "red": []}))
        scorecard_path = None
        if args.html:
            folder_name = f"scorecard_{tenant_id or 0}_{_sanitize_folder_name(tenant_name or 'tenant')}"
            scorecard_path = f"{folder_name}/scorecard.html"
        from audit.aggregate import merge_into_aggregate
        merge_into_aggregate(Path(args.output_aggregate), [{
            "tenant_id": tenant_id, "tenant_name": tenant_name, "lookback_days": lookback,
            "is_live": is_live, "results": results, "findings_by_area": findings_by_area,
            "area_statuses": area_statuses_single, "action_plan": action_plan,
            "scorecard_path": scorecard_path,
        }], lookback)
        print(f"Merged 1 tenant into {args.output_aggregate}", file=sys.stderr)

    width = 62
    print("=" * width)
    print("  INVENTORY SETUP / USAGE AUDIT — CUSTOMER SCORECARD")
    print("=" * width)
    if tenant_id is not None:
        print(f"  Tenant ID:   {tenant_id}")
    if tenant_name:
        print(f"  Tenant:      {tenant_name}")
    print(f"  Lookback:    {lookback} days")
    print()

    # --- Scorecard: one row per area with status ---
    if not is_live:
        print("  (Purchasing audit — not yet live with inventory)")
    print("  SCORECARD BY AREA")
    print("  " + "-" * (width - 2))
    status_symbol = {"Red": "[!]", "Review": "[~]", "Yellow": "[~]", "Green": "[OK]"}
    for area in audit_areas:
        findings = findings_by_area.get(area, {"green": [], "yellow": [], "red": []})
        status = _area_status(findings)
        sym = status_symbol.get(status, "•")
        print(f"  {sym}  {area:<28}  {status}")
    print("  " + "-" * (width - 2))
    overall = "No critical issues" if ok else "Address red items to improve setup and usage"
    print(f"  Overall: {overall}")
    if not is_live:
        if _is_preparing_for_go_live(results, is_live):
            go_live_ready, go_live_needs = _go_live_readiness(results)
            if go_live_ready:
                print("  Go Live Readiness: Ready to set your go live date and do inventory beginning balance counts.")
            else:
                print("  Go Live Readiness:")
                for n in go_live_needs:
                    print(f"    • {n}")
        else:
            if ready_for_inventory:
                print("  Inventory Readiness: Ready to start inventory implementation.")
            else:
                areas_needing_work = _readiness_areas_needing_work(findings_by_area)
                areas_str = _format_areas_for_message(areas_needing_work)
                if areas_str:
                    print(f"  Inventory Readiness: Address red items in {areas_str} to prepare for inventory implementation.")
                else:
                    print("  Inventory Readiness: Address red items above to prepare for inventory implementation.")
    print()

    print("  --- Settings ---")
    cfg = results.get("readiness_config") or {}
    fg = results.get("feature_gates") or {}
    print("    Feature gates:")
    print(f"      Purchasing module: {'On' if cfg.get('purchasing_module_on') else 'Off' if cfg.get('purchasing_module_on') is False else '—'}")
    print(f"      Inventory module:  {'On' if cfg.get('inventory_module_on') else 'Off' if cfg.get('inventory_module_on') is False else '—'}")
    if fg:
        print(f"      Item requisitions: {'On' if fg.get('item_requisitions') else 'Off'}")
        print(f"      Requisition - Closeout: {'On' if fg.get('requisition_closeout') else 'Off'}")
        print(f"      Enable Requisition Workflow for Service Job: {'On' if fg.get('install_requisitions') else 'Off'}")
        print(f"      Transfers to jobs: {'On' if fg.get('transfers_to_jobs') else 'Off'}")
        print(f"      Consignment: {'On' if fg.get('consignment') else 'Off'}")
        print(f"      Purchase approval workflow: {'On' if fg.get('purchase_approval_workflow') else 'Off'}")
        print(f"      Granular WAC: {'On' if fg.get('granular_wac') else 'Off'}")
        if fg.get('stock_optimizer') is not None:
            print(f"      Stock Optimizer: {'On' if fg.get('stock_optimizer') else 'Off'}")
    print()
    if is_live:
        print("    Inventory Settings (in UI) — customer-controllable:")
        inv_settings = results.get("inventory_settings")
        if inv_settings:
            for line in format_inventory_settings(inv_settings):
                print(line)
        else:
            print("      (not found or not available)")
        print()
    else:
        inv_settings = results.get("inventory_settings")
        if inv_settings:
            start = inv_settings.get("BeginningDate") or inv_settings.get("beginningDate")
            if start is not None:
                print(f"    Inventory tracking start date: {str(start).strip()[:10]}")
        print()
    if is_live:
        print("  --- Setup (counts) ---")
        isinv = results.get("isinventory_counts") or {}
        active_mats = isinv.get("active_materials_count")
        mat_isinv = isinv.get("materials_isinventory_count")
        uom_count = results.get("materials_with_unit_of_measure", 0)
        active_eq = isinv.get("active_equipment_count")
        eq_isinv = isinv.get("equipment_isinventory_count")
        eq_serialized = results.get("equipment_serialized_count", 0)
        print(f"    Materials: total {active_mats if active_mats is not None else '—'}; with IsInventory: {mat_isinv if mat_isinv is not None else '—'}; with unit of measure: {uom_count}")
        print(f"    Equipment: total {active_eq if active_eq is not None else '—'}; with IsInventory: {eq_isinv if eq_isinv is not None else '—'}; serialized: {eq_serialized}")
        setup = results.get("setup_data")
        if setup and isinstance(setup, dict):
            truck_total = setup.get("truck_total", 0)
            truck_with_tpl = setup.get("truck_with_template", 0)
            wh_total = setup.get("warehouse_total", 0)
            wh_with_tpl = setup.get("warehouse_with_template", 0)
            templates_under = setup.get("templates_under_20_active_items", 0)
            truck_pct = (100 * truck_with_tpl // truck_total) if truck_total > 0 else 0
            truck_ok = truck_total == 0 or truck_pct >= TRUCK_TEMPLATE_PCT_MIN
            wh_ok = wh_total == 0 or wh_with_tpl >= WAREHOUSE_WITH_TEMPLATE_MIN
            templates_ok = templates_under == 0
            print(f"    {'[OK]' if truck_ok else '[!!]'} Trucks: {truck_total} total (active), {truck_with_tpl} with inventory template (min 80% expected)")
            print(f"    {'[OK]' if wh_ok else '[!!]'} Warehouses: {wh_total} total (active), {wh_with_tpl} with inventory template (at least 1 expected)")
            print(f"    {'[OK]' if templates_ok else '[!!]'} Templates with < {TEMPLATE_MIN_ACTIVE_ITEMS} active items: {templates_under}")
        print()

    # --- Findings by area ---
    print("  --- Findings by area ---")
    for area in audit_areas:
        findings = findings_by_area.get(area, {"green": [], "yellow": [], "review": [], "red": []})
        if not any(findings.values()):
            continue
        status = _area_status(findings)
        sym = status_symbol.get(status, "•")
        print(f"    [{sym} {area}]")
        for g in findings["green"]:
            print(f"      [OK]    {g}")
        for y in findings["yellow"]:
            print(f"      [WARN]  {y}")
        for rev in findings.get("review") or []:
            print(f"      [REV]   {rev}")
        for r in findings["red"]:
            print(f"      [!!]    {r}")
        print()

    print("  " + "=" * (width - 2))
    if ok:
        print("  Audit: No critical issues. Review warnings as needed.")
    else:
        print("  Audit: Address red items to improve setup and usage.")
    print("=" * width)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
