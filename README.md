# Inventory Setup / Usage Audit

Audit app for **tenants who are already using the inventory module**. Checks that they are set up well and using the module appropriately (configuration, data quality, and usage patterns).

## Purpose

- **Audience**: Tenants with the inventory module **on** (unlike the [Inventory Readiness Check](../Inventory_Prepardness_Check), which targets tenants not yet on inventory).
- **Goal**: Verify setup quality and appropriate usage—e.g. pricebook completeness, replenishment and receiving behavior, invoice material usage, returns handling, and feature configuration—so we can flag issues and recommend improvements.
- **Group runs**: When run against a **tenant group**, the script automatically branches per tenant: tenants **live on inventory** (tracking start date in the past) get the full **inventory setup & usage** audit; tenants **not yet live** get a **purchasing-only** audit (Purchasing, Invoicing, Replenishment, Returns). Inventory-only areas (Technician usage, Pricebook & setup, Usage & operations) show as **N/A** for non-inventory tenants in the group summary.

## Scope

- **Checks (from readiness, tweakable)**: Purchase orders (pending count, pending over 90 days, activity, line quality, placeholder descriptions), invoice materials (line count, % added by technician, placeholder-like descriptions), replenishment requests (open vs completed, used materials). Assessment data (inventory/purchasing on, IsInventory counts, tracking start) is included for context.
- **Future**: Pricebook, returns, or other setup/usage checks can be added.

## Setup (Python connector / .env)

To run the audit **directly from Snowflake** (single tenant or full tenant group) without manual export:

1. **Install dependencies** (includes Snowflake connector and python-dotenv):
   ```bash
   pip install -r requirements.txt
   ```
2. **Copy `.env.example` to `.env`** and set your Snowflake credentials:
   ```bash
   cp .env.example .env
   # Edit .env: set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, and SNOWFLAKE_REGION if needed
   ```
   The script loads `.env` automatically from this directory, so you don’t need to `export` vars. **Do not commit `.env`** (it’s in `.gitignore`).

3. **Single tenant:**  
   `python3 audit_report.py --from-snowflake --tenant-id <ID> --html scorecard.html`

4. **Full tenant group (e.g. T3 Services Group):**  
   `python3 audit_report.py --from-snowflake --tenant-group "T3 Services Group" --html summary.html`  
   This pulls data for every tenant in one run and writes everything into a folder named from the group (e.g. `T3_Services_Group/`): `index.html` (summary), `scorecard_<tenant_id>.html` for each tenant, and `scorecard.css`.

The first run may open the browser for Okta/SSO login.

## How to use

1. **Set tenant ID in SQL**  
   Open `sql/00_combined_audit.sql` and replace `0` in `tenant_param` with your tenant ID. The query uses the **last 90 days**.

2. **Run the query in Snowflake**  
   Run the entire statement. It returns 9 rows: `tenant_info`, `purchase_orders_summary`, `invoice_materials`, `replenishment_summary`, `returns_summary`, `assessment_data`, `inventory_settings`, `setup_data`, `usage_checks` (columns `source`, `v1`..`v16`). Tenant ID and name are in the first row for the report header; `inventory_settings` contains the Inventory.Configuration JSON for readable settings.

3. **Export** to Excel (.xlsx) or CSV (one sheet/file, header + 9 data rows).

4. **Generate the report**:
   ```bash
   python3 audit_report.py --from-excel /path/to/results.xlsx
   ```
   Tenant ID and name are read from the query results; you can override with `--tenant-id` and `--tenant-name` if needed. For CSV use `--from-excel /path/to/results.csv`. For Excel you need: `pip install openpyxl`.

5. **Optional: generate a customer-friendly HTML scorecard** (easy to read, printable, shareable):
   ```bash
   python3 audit_report.py --from-excel /path/to/results.xlsx --html scorecard.html
   ```
   Output is written into a folder (e.g. `scorecard_<id>_<tenantname>/scorecard.html` and `scorecard.css`). Opens in any browser; safe to email or attach.

6. **Optional: run directly from Snowflake** (no manual export). Ensure [Setup](#setup-python-connector--env) is done (`.env` with `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, etc.). Then:
   ```bash
   python3 audit_report.py --from-snowflake --tenant-id 257 --html scorecard.html
   ```
   For a **full tenant group** in one go:  
   `python3 audit_report.py --from-snowflake --tenant-group "T3 Services Group" --html T3_Services_Group_summary.html`

## Options

| Option | Description |
|--------|-------------|
| `--from-excel FILE` | Read from Excel (.xlsx) or CSV (combined 4-row export). |
| `--from-csv-folder FOLDER` | Read from CSVs: purchase_orders_summary.csv, invoice_materials.csv, replenishment_summary.csv, assessment_data.csv. |
| `--from-results JSON_FILE` | Read from a JSON file. |
| `--tenant-id` | Override tenant ID in header (default: from query `tenant_info` row). |
| `--tenant-name` | Override tenant name in header (default: from query `tenant_info` row). |
| `--lookback-days` | Lookback days in report text (default 90). |
| `--html FILE` | Write HTML scorecard(s). Single: creates folder `scorecard_<id>_<name>/` with `scorecard.html` and CSS. Group: creates folder from group name with `index.html`, `scorecard_<id>.html`, and CSS. |
| `--from-snowflake` | Run the audit query in Snowflake; requires `--tenant-id` or `--tenant-group`. Uses `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, and optional `SNOWFLAKE_WAREHOUSE` etc. Authenticates via Okta (external browser) by default. |
| `--tenant-group` | Run audit for all tenants in a tenant group (e.g. `"T3 Services Group"`). Requires `--from-snowflake` and `--html`. Writes everything into a folder (e.g. `T3_Services_Group/`): `index.html`, `scorecard_<id>.html`, and CSS. |
| `--from-group-json` | Read pre-fetched group audit results from a JSON file (e.g. from Snowflake MCP or manual export). Requires `--html`. See [TENANT_GROUP_DISPLAY.md](TENANT_GROUP_DISPLAY.md). |

## Tweakable thresholds

In `audit_report.py` you can adjust:

- `TOTAL_PENDING_ABSOLUTE_RED` — red if total pending POs exceeds this (default 50).
- `PO_SINGLE_LINE_MAJORITY` / `PO_PLACEHOLDER_MAJORITY` — red if > this share of POs have one line or placeholder-like lines (default 0.5).
- `INVOICE_PLACEHOLDER_GREEN_MAX_PCT` / `INVOICE_PLACEHOLDER_RED_MIN_PCT` — green &lt; 10%, red &gt; 70%.
- `REPLENISHMENT_OPEN_YELLOW` — yellow when open replenishment requests exceed this (default 300).

## Structure

```
Inventory_Setup_Usage_Audit/
├── README.md           # This file
├── sql/
│   └── 00_combined_audit.sql   # One query, 9 rows (tenant_info, POs, invoice, replenishment, returns, assessment, inventory_settings, setup_data, usage_checks)
├── audit_report.py     # Parse results and print audit report
├── requirements.txt   # openpyxl for Excel
└── .env.example        # Optional config template
```

## Data sources

Same as the readiness check: `tenant_data.DBO`, `tenant_data.FEATURE_GATE.FEATURE_GATE_FLAT`, scoped by `tenant_param` and `_TENANT_ID`. This app is for tenants already on the inventory module.

## Related

- [Inventory Readiness Check](../Inventory_Prepardness_Check) — for tenants *not* yet on inventory; this audit reuses its PO, invoice, and replenishment checks.
- [Inventory Readiness REUSE](../Inventory_Prepardness_Check/REUSE.md) and the `inventory-readiness` Cursor skill.
