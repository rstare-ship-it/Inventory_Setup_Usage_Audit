# Displaying inventory audit data for tenant groups (strategic accounts)

When a **strategic account owns multiple tenants** (a tenant group), you have a few good ways to show the data. This doc suggests display patterns and what to show at group vs tenant level.

---

## 1. Recommended: Group summary page + links to per-tenant scorecards

**Idea:** One page for the **group** with an executive summary and a table of tenants; each row links to the existing single-tenant HTML scorecard.

- **Header:** Group name (e.g. "T3 Services Group"), tenant count, date range.
- **Summary:** e.g. "3 of 5 tenants need attention in at least one area" or counts by status (green / yellow / red) across areas.
- **Table:**

  | Tenant        | Purchasing | Invoicing | Technician usage | Replenishment | Returns | Pricebook & setup | Usage & operations |
  |---------------|------------|-----------|------------------|---------------|---------|-------------------|--------------------|
  | tenant_a      | Needs attention | OK | Review | ... | ... | ... | ... |
  | tenant_b      | OK         | OK        | OK               | ... | ... | ... | ... |

- **Links:** Tenant name (or a "View scorecard" link) opens the existing `scorecard_<tenant_id>.html` for that tenant.

**Pros:** Reuses current scorecard; one place to see the whole group; drill-down stays familiar.  
**Cons:** You need to run the audit per tenant and then build the group summary (e.g. from JSON or a small aggregation query).

---

## 2. Single HTML with collapsible sections per tenant

**Idea:** One HTML file per group. Header = group name; below that, one **collapsible section per tenant**, each containing the same structure as the current scorecard (or a shortened “mini” scorecard).

- Good for: "One PDF to email the strategic account" with everything in one file.
- Structure:
  - **Group header:** Group name, last 90 days, tenant count.
  - **Per tenant:** `<details>` (or accordion) with tenant name + Tenant ID; inside, the same scorecard grid, settings summary, and findings you already have.

**Pros:** Single shareable artifact; no cross-file navigation.  
**Cons:** File can get long; you still run the audit once per tenant and merge results.

---

## 3. Group-level roll-up metrics (where they make sense)

**Idea:** At the **group** level, show only metrics that meaningfully roll up; keep setup/configuration and status **per tenant**.

- **Safe to aggregate (examples):**
  - Total POs created (sum across tenants).
  - Total invoices with material lines (sum).
  - Total replenishment open / completed (sum).
- **Keep per tenant (do not average/sum):**
  - Status badges (red / yellow / green) — show per tenant in a table.
  - Settings (e.g. inventory tracking start date, feature flags).
  - Setup (trucks, warehouses, templates) — each tenant has its own.

So: use **aggregation for volume/activity** in a group summary; use **per-tenant rows** for status and setup.

---

## 4. Implementation outline

1. **Resolve tenants in the group**  
   Use `tenant_data.MASTER_DB.TENANTGROUP` + `TENANTRECORD_GROUPS_TENANTGROUP` + `TENANTRECORD` (by group name or ID) to get `_TENANT_ID` and tenant name for all tenants in the group.

2. **Run existing audit per tenant**  
   For each tenant ID, run `00_combined_audit.sql` (or `audit_report.py --from-snowflake --tenant-id <id>`) and capture the parsed results (e.g. area statuses and key metrics). Optionally write `scorecard_<tenant_id>.html` for each.

3. **Build the group view**  
   - **Option A (summary + links):** Generate one HTML page that shows group name, summary counts, and a table of tenants with status badges and links to `scorecard_<tenant_id>.html`.
   - **Option B (collapsible):** Generate one HTML that includes the full (or mini) scorecard content per tenant inside `<details>` or an accordion.

4. **Data shape**  
   Keep a small “group run” structure, e.g. `{ "group_name": "...", "tenant_ids": [...], "tenants": [ { "tenant_id", "tenant_name", "results": {...}, "findings_by_area": {...} ] }`, so you can drive either Option A or B from the same data.

---

## 5. Running for T3 Services Group (or any group)

**Option A — Snowflake (one command):**  
Set `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, and optionally `SNOWFLAKE_REGION`. Then:

```bash
python3 audit_report.py --from-snowflake --tenant-group "T3 Services Group" --html T3_Services_Group_summary.html
```

This writes `T3_Services_Group_summary.html` (group summary) and `scorecard_<tenant_id>.html` for each tenant in the same folder. Copy `css/scorecard.css` into that folder if needed (the script does this automatically when run from the repo).

**Option B — Pre-fetched JSON (no local Snowflake login):**  
If you have audit query results (e.g. from Snowflake MCP or manual runs), put them in a JSON file with shape:

```json
{
  "group_name": "T3 Services Group",
  "lookback_days": 90,
  "tenants": [
    {
      "tenant_id": 14419777,
      "tenant_name": "radiantplumbing",
      "rows": [
        ["tenant_info", "14419777", "radiantplumbing", "", ...],
        ["purchase_orders_summary", ...],
        ...
      ]
    }
  ]
}
```

Each `rows` array must have 9 rows (tenant_info, purchase_orders_summary, invoice_materials, replenishment_summary, returns_summary, assessment_data, inventory_settings, setup_data, usage_checks) in the same order as `sql/00_combined_audit.sql`. Then:

```bash
python3 audit_report.py --from-group-json T3_Services_Group_audit_results.json --html T3_Services_Group_summary.html
```

---

## 6. Quick reference: tenant group membership (Snowflake)

```sql
-- All tenants in a group (by group name)
SELECT g.NAME AS tenant_group_name,
       r._TENANT_NAME AS tenant_name,
       r._TENANT_ID
FROM tenant_data.MASTER_DB.TENANTGROUP g
JOIN tenant_data.MASTER_DB.TENANTRECORD_GROUPS_TENANTGROUP j ON g.ID = j.TENANTGROUP
JOIN tenant_data.MASTER_DB.TENANTRECORD r ON j.TENANTRECORD = r._TENANT_ID
WHERE g.NAME = 'Your Group Name';
```

Use this to get the list of tenant IDs and names, then run the existing audit for each and combine for the group display.

---

## Summary

| Approach | Best for |
|----------|----------|
| **Group summary page + links to per-tenant scorecards** | Day-to-day use; one place to see group health and drill into any tenant. |
| **Single HTML with collapsible per-tenant sections** | One file/PDF to share with the strategic account. |
| **Roll-up metrics at group level** | High-level activity (e.g. total POs, invoices); keep status and setup per tenant. |

Recommendation: implement **Option 1** (summary table + links) first, reusing your current scorecard HTML. Add **Option 2** (collapsible single file) if you need a single shareable group report.
