"""
HTML rendering: scorecard and group-summary pages.
All user-facing text is HTML-escaped. Reads only from the results/findings dicts;
has no side effects (no file I/O).
"""
from __future__ import annotations

import html as _html_mod

from audit.constants import (
    AUDIT_AREAS,
    TRUCK_TEMPLATE_PCT_MIN,
    WAREHOUSE_WITH_TEMPLATE_MIN,
    TEMPLATE_MIN_ACTIVE_ITEMS,
)
from audit.evaluate import _area_status, get_action_plan
from audit.parse import (
    format_inventory_settings,
    _is_preparing_for_go_live,
    _go_live_readiness,
    _readiness_areas_needing_work,
    _format_areas_for_message,
)


def _escape(s: str) -> str:
    return _html_mod.escape(str(s), quote=True)


# Status label map (4 tiers)
STATUS_LABEL = {
    "Red": "Critical",
    "Review": "Review",
    "Yellow": "On track",
    "Green": "Good",
    "N/A": "N/A",
}


# ---------------------------------------------------------------------------
# Group summary helpers
# ---------------------------------------------------------------------------

def _group_overall_score(tenant_results: list[dict]) -> tuple[int, int, int]:
    """Return (good_cells, total_cells, pct). N/A cells are excluded from total."""
    good = total = 0
    for t in tenant_results:
        for area in AUDIT_AREAS:
            status = (t.get("area_statuses") or {}).get(area, "Green")
            if status == "N/A":
                continue
            total += 1
            if status == "Green":
                good += 1
    pct = (100 * good // total) if total else 0
    return good, total, pct


def _group_common_struggles(tenant_results: list[dict], min_tenants: int = 2) -> list[tuple[str, int, int]]:
    """Areas where at least min_tenants are not Green. Returns [(area, struggling, total_with_area)] sorted desc."""
    by_area: dict[str, list[int]] = {a: [] for a in AUDIT_AREAS}
    for t in tenant_results:
        area_statuses = t.get("area_statuses") or {}
        for area in AUDIT_AREAS:
            status = area_statuses.get(area, "Green")
            by_area[area].append(-1 if status == "N/A" else (0 if status == "Green" else 1))
    out: list[tuple[str, int, int]] = []
    for area in AUDIT_AREAS:
        vals = by_area[area]
        total_with = sum(1 for v in vals if v >= 0)
        struggling = sum(1 for v in vals if v == 1)
        if total_with > 0 and struggling >= min_tenants:
            out.append((area, struggling, total_with))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out


def _group_global_action_plan(tenant_results: list[dict], min_tenants: int = 2) -> list[tuple[str, int]]:
    """Actions appearing in at least min_tenants tenants, sorted by count desc."""
    from collections import Counter
    counts: Counter[str] = Counter()
    for t in tenant_results:
        for a in (t.get("action_plan") or []):
            if a and isinstance(a, str) and a.strip():
                counts[a.strip()] += 1
    return [(a, c) for a, c in counts.most_common() if c >= min_tenants]


# ---------------------------------------------------------------------------
# Group summary HTML
# ---------------------------------------------------------------------------

def render_group_summary_html(
    group_name: str,
    tenant_results: list[dict],
    lookback: int,
) -> str:
    """Build group summary HTML with score, common struggles, action plan, and per-tenant status table."""
    title = f"Inventory Scorecard — {_escape(group_name)} (group summary)"
    n = len(tenant_results)
    n_need = sum(1 for t in tenant_results if not t.get("ok", True))
    summary_line = (
        f"{n_need} of {n} tenant(s) need attention in at least one area."
        if n_need > 0
        else f"All {n} tenants are in good shape (no red areas)."
    )

    good_cells, total_cells, score_pct = _group_overall_score(tenant_results)
    if total_cells > 0:
        score_label = "Strong" if score_pct >= 80 else "On track" if score_pct >= 60 else "Needs focus" if score_pct >= 40 else "Critical"
        score_class = "ok" if score_pct >= 60 else "not-ok"
        summary_score_line = f'<p class="overall {score_class}">Group health: {score_pct}% — {_escape(score_label)}</p>'
    else:
        summary_score_line = ""

    common = _group_common_struggles(tenant_results, min_tenants=2)
    if common:
        items = "".join(f'<li>{_escape(area)}: {count} of {total} tenant(s) need improvement</li>' for area, count, total in common)
        common_html = f'<ul class="group-common-list">\n        {items}\n      </ul>'
    else:
        common_html = "<p>No single area stands out as a common struggle across multiple tenants.</p>"

    global_actions = _group_global_action_plan(tenant_results, min_tenants=2)
    if global_actions:
        items = "".join(
            f'<li>{_escape(action)} <span class="global-action-count">({count} tenant{"s" if count != 1 else ""})</span></li>'
            for action, count in global_actions
        )
        global_html = f'<ol class="group-action-plan-list">\n        {items}\n      </ol>'
    else:
        global_html = "<p>No actions apply to multiple tenants; review individual scorecards for tenant-specific recommendations.</p>"

    area_headers = "".join(f'<th scope="col">{_escape(a)}</th>' for a in AUDIT_AREAS)
    rows_html = []
    for t in tenant_results:
        tid = t.get("tenant_id") or 0
        tname = _escape(t.get("tenant_name") or f"Tenant {tid}")
        link = f'<a href="scorecard_{tid}.html">{tname}</a>'
        area_statuses = t.get("area_statuses") or {}
        cells = []
        for area in AUDIT_AREAS:
            status = area_statuses.get(area, "Green")
            sl = "na" if status == "N/A" else status.lower()
            label = STATUS_LABEL.get(status, status)
            cells.append(f'<td class="status-{sl}"><span class="badge badge-{sl}">{_escape(label)}</span></td>')
        rows_html.append(
            f'        <tr><td class="tenant-name">{link}</td>\n            '
            + "\n            ".join(cells)
            + "\n        </tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="scorecard.css">
  <style>
    .group-summary-wrap {{ overflow-x: auto; width: 100%; margin-top: 0.5rem; }}
    .group-summary-table {{ width: 100%; min-width: 600px; border-collapse: collapse; }}
    .group-summary-table th, .group-summary-table td {{ padding: 0.4rem 0.5rem; text-align: left; border-bottom: 1px solid var(--st-border, #dfe0e1); font-size: 0.8125rem; }}
    .group-summary-table th {{ font-weight: 600; color: var(--st-text-secondary, #3f3f46); white-space: nowrap; }}
    .group-summary-table .tenant-name {{ font-weight: 500; }}
    .group-summary-table a {{ color: var(--st-primary, #2270ee); text-decoration: none; }}
    .group-summary-table a:hover {{ text-decoration: underline; }}
    .group-summary-table td.status-red {{ background: var(--danger-muted, #fef2f2); }}
    .group-summary-table td.status-review {{ background: #fff7ed; }}
    .group-summary-table td.status-yellow {{ background: var(--warn-muted, #fffbeb); }}
    .group-summary-table td.status-green {{ background: var(--success-muted, #ecfdf5); }}
    .group-summary-table td.status-na {{ background: var(--st-surface-alt, #fafafa); color: var(--st-text-muted, #71717a); }}
    .group-summary-table .badge-review {{ background: #fed7aa; color: #9a3412; }}
    .group-summary-table .badge-na {{ background: #e5e7eb; color: #6b7280; }}
    .group-subhead {{ font-size: 0.875rem; font-weight: 600; margin: 1rem 0 0.35rem 0; color: var(--st-text-secondary, #3f3f46); }}
    .group-subhead:first-of-type {{ margin-top: 0; }}
    .group-common-list {{ margin: 0; padding-left: 1.25rem; font-size: 0.9375rem; }}
    .group-common-list li {{ margin: 0.35rem 0; }}
    .group-action-plan-list {{ margin: 0; padding-left: 1.35rem; font-size: 0.9375rem; }}
    .group-action-plan-list li {{ margin: 0.4rem 0; }}
    .global-action-count {{ color: var(--st-text-muted, #71717a); font-size: 0.8125rem; font-weight: 500; }}
    .card-desc {{ margin: 0 0 0.5rem 0; font-size: 0.8125rem; color: var(--st-text-muted, #71717a); }}
  </style>
</head>
<body>
  <div class="page">
    <header class="header">
      <h1>Inventory Setup &amp; Usage Scorecard — Group Summary</h1>
      <p class="meta">
        <span>{_escape(group_name)}</span>
        <span>Last {lookback} days</span>
        <span>{n} tenant(s)</span>
      </p>
    </header>

    <div class="card scorecard">
      <h2 class="card-title">Summary</h2>
      <p class="overall {'ok' if n_need == 0 else 'not-ok'}">{_escape(summary_line)}</p>
      {summary_score_line}
      <p>Click a tenant name to open their full scorecard.</p>
    </div>

    <section class="card block">
      <h2 class="card-title">Common struggles &amp; action plan</h2>
      <h3 class="group-subhead">Common struggles</h3>
      <p class="card-desc">Areas where multiple tenants need improvement.</p>
      {common_html}
      <h3 class="group-subhead">Recommended actions</h3>
      <p class="card-desc">Actions that apply to multiple tenants in this group.</p>
      {global_html}
    </section>

    <section class="card block">
      <h2 class="card-title">Tenants by area</h2>
      <div class="group-summary-wrap">
      <table class="group-summary-table" aria-label="Tenant scorecard status by area">
        <thead>
          <tr>
            <th scope="col">Tenant</th>
            {area_headers}
          </tr>
        </thead>
        <tbody>
{chr(10).join(rows_html)}
        </tbody>
      </table>
      </div>
    </section>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Individual scorecard HTML
# ---------------------------------------------------------------------------

def render_scorecard_html(
    tenant_id: int | None,
    tenant_name: str | None,
    lookback: int,
    results: dict,
    findings_by_area: dict[str, dict[str, list[str]]],
    ok: bool,
    audit_areas: list[str] | None = None,
    is_live: bool = True,
    ready_for_inventory_implementation: bool | None = None,
) -> str:
    """Build a self-contained HTML scorecard. All dynamic text is escaped."""
    audit_areas = audit_areas or AUDIT_AREAS
    tenant_display = _escape(tenant_name or (f"Tenant {tenant_id}" if tenant_id else "Inventory Audit"))
    title = (
        f"Inventory Setup &amp; Usage Scorecard — {tenant_display}"
        if is_live
        else f"Purchasing Audit Scorecard — {tenant_display}"
    )

    status_class = {"Red": "status-red", "Review": "status-review", "Yellow": "status-yellow", "Green": "status-green"}
    status_label = {"Red": "Critical", "Review": "Review", "Yellow": "On track", "Green": "Good"}

    # Scorecard grid
    scorecard_items = []
    for area in audit_areas:
        findings = findings_by_area.get(area, {"green": [], "yellow": [], "review": [], "red": []})
        status = _area_status(findings)
        label = status_label.get(status, status)
        scorecard_items.append(
            f'        <div class="scorecard-item status-{status.lower()}">'
            f'<span class="area-name">{_escape(area)}</span>'
            f'<span class="badge badge-{status.lower()}">{_escape(label)}</span></div>'
        )

    # Findings by area
    findings_sections = []
    for area in audit_areas:
        findings = findings_by_area.get(area, {"green": [], "yellow": [], "review": [], "red": []})
        if not any(findings.values()):
            continue
        status = _area_status(findings)
        label = status_label.get(status, status)
        lines = []
        for g in findings["green"]:
            lines.append(f'          <li class="finding-ok">{_escape(g)}</li>')
        for y in findings["yellow"]:
            lines.append(f'          <li class="finding-warn">{_escape(y)}</li>')
        for rev in (findings.get("review") or []):
            lines.append(f'          <li class="finding-review">{_escape(rev)}</li>')
        for r in findings["red"]:
            lines.append(f'          <li class="finding-err">{_escape(r)}</li>')
        border = "border-green" if status == "Green" else "border-yellow" if status == "Yellow" else "border-review" if status == "Review" else "border-red"
        findings_sections.append(
            f'      <section class="findings-area {border}">\n'
            f'        <h3 class="area-head">{_escape(area)} <span class="badge badge-{status.lower()}">{_escape(label)}</span></h3>\n'
            f'        <ul class="findings-list">\n' + "\n".join(lines) + "\n"
            f"        </ul>\n      </section>"
        )

    # Settings panel
    cfg = results.get("readiness_config") or {}
    fg = results.get("feature_gates") or {}
    settings_lines = [
        f"<p><strong>Purchasing module:</strong> {'On' if cfg.get('purchasing_module_on') else 'Off' if cfg.get('purchasing_module_on') is False else '—'}",
        f"<p><strong>Inventory module:</strong> {'On' if cfg.get('inventory_module_on') else 'Off' if cfg.get('inventory_module_on') is False else '—'}",
    ]
    if fg:
        settings_lines.append(f"<p><strong>Item requisitions:</strong> {'On' if fg.get('item_requisitions') else 'Off'}")
        settings_lines.append(f"<p><strong>Requisition closeout:</strong> {'On' if fg.get('requisition_closeout') else 'Off'}")
        settings_lines.append(f"<p><strong>Transfers to jobs:</strong> {'On' if fg.get('transfers_to_jobs') else 'Off'}")
        settings_lines.append(f"<p><strong>Consignment:</strong> {'On' if fg.get('consignment') else 'Off'}")
        settings_lines.append(f"<p><strong>Purchase approval workflow:</strong> {'On' if fg.get('purchase_approval_workflow') else 'Off'}")
        settings_lines.append(f"<p><strong>Granular WAC:</strong> {'On' if fg.get('granular_wac') else 'Off'}")
    inv_settings = results.get("inventory_settings")
    if inv_settings:
        if is_live:
            for line in format_inventory_settings(inv_settings):
                parts = line.strip().split(":", 1)
                if len(parts) == 2:
                    settings_lines.append(f"<p><strong>{_escape(parts[0].strip())}:</strong> {_escape(parts[1].strip())}")
                else:
                    settings_lines.append(f"<p>{_escape(line.strip())}")
        else:
            start = inv_settings.get("BeginningDate") or inv_settings.get("beginningDate")
            if start is not None:
                settings_lines.append(f"<p><strong>Inventory tracking start date:</strong> {_escape(str(start).strip()[:10])}</p>")
    settings_html = "\n    ".join(settings_lines) if settings_lines else "<p>Not available.</p>"

    # Setup summary (inventory audit only)
    setup_section_html = ""
    if is_live:
        isinv = results.get("isinventory_counts") or {}
        setup = results.get("setup_data")
        active_mats = isinv.get("active_materials_count")
        mat_isinv = isinv.get("materials_isinventory_count")
        uom_count = results.get("materials_with_unit_of_measure", 0)
        active_eq = isinv.get("active_equipment_count")
        eq_isinv = isinv.get("equipment_isinventory_count")
        eq_serialized = results.get("equipment_serialized_count", 0)
        setup_parts = [
            f"<p><strong>Materials:</strong> total {active_mats if active_mats is not None else '—'}; with IsInventory: {mat_isinv if mat_isinv is not None else '—'}; with unit of measure: {uom_count}.",
            f"<p><strong>Equipment:</strong> total {active_eq if active_eq is not None else '—'}; with IsInventory: {eq_isinv if eq_isinv is not None else '—'}; serialized: {eq_serialized}.",
        ]
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
            setup_parts.append(f"<p><strong>Trucks:</strong> {truck_total} total, {truck_with_tpl} with inventory template (min 80% expected) — {'OK' if truck_ok else 'Needs attention'}.")
            setup_parts.append(f"<p><strong>Warehouses:</strong> {wh_total} total, {wh_with_tpl} with template — {'OK' if wh_ok else 'Needs attention'}.")
            setup_parts.append(f"<p><strong>Templates with &lt; {TEMPLATE_MIN_ACTIVE_ITEMS} active items:</strong> {templates_under} — {'OK' if templates_ok else 'Needs attention'}.")
        setup_html = "\n    ".join(setup_parts) if setup_parts else "<p>Not available.</p>"
        setup_section_html = (
            '    <section class="card block">\n      <h2 class="card-title">Setup summary</h2>\n      '
            + setup_html
            + "\n    </section>\n\n    "
        )

    # Readiness section (purchasing audit only)
    readiness_section_html = ""
    if not is_live:
        if _is_preparing_for_go_live(results, is_live):
            go_live_ready, go_live_needs = _go_live_readiness(results)
            if go_live_ready:
                readiness_body = '<p class="overall ok">Ready to set your go live date and do inventory beginning balance counts.</p>'
            else:
                needs_list = "\n      ".join(f"<li>{_escape(n)}</li>" for n in go_live_needs)
                readiness_body = f'<ul class="readiness-needs">\n      {needs_list}\n    </ul>'
            readiness_section_html = (
                '    <section class="card block go-live-readiness">\n'
                '      <h2 class="card-title">Go Live Readiness</h2>\n      '
                + readiness_body + "\n"
                "    </section>\n\n    "
            )
        elif ready_for_inventory_implementation is not None:
            if ready_for_inventory_implementation:
                readiness_body = '<p class="overall ok">Ready to start inventory implementation.</p>'
            else:
                areas_needing_work = _readiness_areas_needing_work(findings_by_area)
                areas_str = _format_areas_for_message(areas_needing_work)
                if areas_str:
                    readiness_body = f'<p class="overall not-ok">Address red items in {_escape(areas_str)} to prepare for inventory implementation.</p>'
                else:
                    readiness_body = '<p class="overall not-ok">Address red items above to prepare for inventory implementation.</p>'
            readiness_section_html = (
                '    <section class="card block inventory-readiness">\n'
                '      <h2 class="card-title">Inventory Readiness</h2>\n      '
                + readiness_body + "\n"
                "    </section>\n\n    "
            )

    # Action plan
    action_plan = get_action_plan(findings_by_area, audit_areas)
    if action_plan:
        ap_html = '<ol class="action-plan-list">\n      ' + "\n      ".join(f"<li>{_escape(a)}</li>" for a in action_plan) + "\n    </ol>"
    else:
        ap_html = "<p>No specific actions recommended; keep up current practices.</p>"
    action_plan_section = (
        '    <section class="card block action-plan">\n'
        '      <h2 class="card-title">Recommended actions</h2>\n      '
        + ap_html
        + "\n    </section>\n\n    "
    )

    overall_msg = "No critical issues. Review any yellow areas as needed." if ok else "Address red areas to improve setup and usage."
    h1_text = "Inventory Setup &amp; Usage Scorecard" if is_live else "Purchasing Audit Scorecard"
    meta_extra = ""
    if not is_live:
        start = results.get("inventory_tracking_start_date")
        start_str = str(start).strip()[:10] if start else "—"
        meta_extra = f'<span>Not yet live with inventory (tracking start: {_escape(start_str)})</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)}</title>
  <link rel="stylesheet" href="scorecard.css">
</head>
<body>
  <div class="page">
    <header class="header">
      <h1>{h1_text}</h1>
      <p class="meta">
        <span>{tenant_display}</span>
        <span>Last {lookback} days</span>
        {f'<span>Tenant ID: {tenant_id}</span>' if tenant_id is not None else ''}
        {meta_extra}
      </p>
    </header>

    <div class="card scorecard">
      <h2 class="card-title">Scorecard by area</h2>
      <div class="scorecard-grid">
{chr(10).join(scorecard_items)}
      </div>
      <p class="overall {'ok' if ok else 'not-ok'}">{_escape(overall_msg)}</p>
    </div>

    {readiness_section_html}    <section class="card block">
      <h2 class="card-title">Settings</h2>
      {settings_html}
    </section>

    {setup_section_html}    <section class="card block">
      <h2 class="card-title">Findings by area</h2>
{chr(10).join(findings_sections)}
    </section>

    {action_plan_section}  </div>
</body>
</html>
"""
