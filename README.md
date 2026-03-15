---
tags:
  - effort
  - inventory
  - audit
status: Active
started: 2026-03-06
goal: Audit tenants using the inventory module for setup quality, configuration, and usage patterns — flag issues and recommend improvements.
aliases:
  - "# Inventory Setup / Usage Audit"
---

# Inventory Setup / Usage Audit

Audit tool for tenants using purchasing, thinking about activating inventory, getting ready to go live with inventory, or are live on inventory. Checks setup quality, configuration, and usage patterns — flags issues and recommends improvements. Results are published as a live website on GitHub Pages.

---

## Purpose

- **Audience**: Tenants using purchasing or inventory, or getting ready for either.
- **Goal**: Verify setup quality and appropriate usage — pricebook completeness, PO discipline, invoice material usage, replenishment behavior, returns handling, transfers, cycle counts, and feature configuration — so we can flag issues and recommend improvements.

---

## How it works

### The website (three pages)

All audit data lives in `data/audit_aggregate.json` and `data/groups.json`. The website reads these files at runtime — no server required.

| Page | URL | Purpose |
|------|-----|---------|
| `index.html` | `/` | Search entry point — accepts tenant ID, tenant name, or group name |
| `group.html` | `/group.html?group=SILA` | Group summary — health stats, common struggles, recommended actions, and a per-tenant status table for all tenants in the group |
| `scorecard.html` | `/scorecard.html?tenant_id=444875142` | Individual tenant scorecard — area status tiles, findings detail, inventory settings, action plan |

Searching by tenant name or group name on `index.html` redirects to the right page automatically. New groups are supported without code changes — just run the audit for a new group name and it registers itself in `groups.json`.

### The audit pipeline

```
run_audit.sh  →  audit_report.py  →  Snowflake  →  data/raw/{id}.json  →  checks.py  →  audit_aggregate.json  →  website
```

1. `run_audit.sh "SILA"` (or `all`) triggers group runs.
2. `audit_report.py` pulls data from Snowflake for each tenant, saves raw results to `data/raw/{tenant_id}.json`, runs checks, and calls `merge_into_aggregate()`.
3. `audit/aggregate.py` merges results into `data/audit_aggregate.json` and updates `data/groups.json` with current group membership.
4. `run_audit.sh` commits and pushes both JSON files. GitHub Pages rebuilds in ~1 minute.

### Reprocessing without Snowflake

When check logic or thresholds change, re-running Snowflake is not required. Use `--reprocess` to re-run all checks against the cached raw data:

```bash
./run_audit.sh --reprocess
```

This reads `data/raw/*.json`, re-runs all Python checks, updates `data/audit_aggregate.json`, and pushes. Runs in seconds with no Okta prompt.

---

## Audit paths

The audit branches based on whether a tenant is **live with inventory** (`beginningDate` has passed):

### Full inventory audit

Runs when `is_live = true`. Evaluates 8 areas:

| Area | What's checked |
|------|----------------|
| **Pricebook & setup** | % materials with $0 cost or Default Replenishment as primary vendor; % of trucks with inventory templates; warehouses with templates; template item count (≥20 active items) |
| **Purchasing** | Pending PO count vs truck count, pending POs over 90 days, PO create + receive rate, multi-line PO rate, placeholder-heavy PO lines |
| **Invoicing** | % of $>0 invoices with ≥1 inventory material line; technician-added material %; IsInventory material %; zero-cost material line % |
| **Replenishment** | Replenishment completion rate (open vs completed); aging replenishment requests over 30 days |
| **Returns** | Pending return % of total returns in period; flags unprocessed credits |
| **Transfers** | Open transfers over 14 days; aging requisitions over 90 days; transfer-to-job usage |
| **Counts and adjustments** | Past due inventory counts; direct adjustments in the lookback period; warehouses with no completed count in 90 days |
| **Other** | Feature flags and configuration — negative quantity allowed, bin tracking, serialized tracking, TTJ, mobile app, etc. |

### Purchasing-only audit

Runs when `is_live = false` (tracking start date not yet reached). Evaluates 6 areas — the rest show as **N/A**:

| Area | What's checked |
|------|----------------|
| **Pricebook & setup** | % of materials with $0 cost; % with Default Replenishment as primary vendor |
| **Purchasing** | Same as full audit |
| **Invoicing** | Technician-added material % |
| **Replenishment** | Same as full audit |
| **Returns** | Same as full audit |
| **Readiness** | Implementation readiness (no IsInventory items yet) or go-live readiness (has IsInventory + templates) — only one fires per tenant; displayed as a banner, not a tile |

Areas not evaluated (Transfers, Counts and adjustments, Other) show as **N/A** in the group summary table.

### Readiness stages

Purchasing-only tenants fall into one of three stages:

| Stage | Condition | Check |
|-------|-----------|-------|
| **Early journey** | No IsInventory items OR no templates assigned | `check_implementation_readiness` — shows what to complete before setting up inventory |
| **Go-live setup** | Has IsInventory items AND at least one template | `check_golive_readiness` — verifies template coverage, IsInventory %, and pre-work quality |
| **Live** | `is_live = true` | Full audit — no readiness banner |

---

## Scoring

Each area rolls up to one of four statuses:

| Status | Meaning |
|--------|---------|
| 🔴 **Critical** | One or more red findings — immediate action needed |
| 🟠 **Review** | Borderline findings — worth investigating |
| 🟡 **On track** | Minor or yellow findings — monitor |
| 🟢 **Good** | No significant issues |

Group health % = green area-cells ÷ total non-N/A area-cells across all tenants in the group.

All thresholds live in `audit/constants.py` — edit there, no changes needed elsewhere. Threshold rationale is documented in [`THRESHOLD_VALIDATION.md`](THRESHOLD_VALIDATION.md).

---

## Running the audit

### Prerequisites

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER
```

### Run a group (standard workflow)

```bash
./run_audit.sh "SILA"
./run_audit.sh "T3 Services Group"
./run_audit.sh all              # runs all groups defined in AUDIT_GROUPS
./run_audit.sh --no-push "SILA" # dry run, no git push
```

Each run: pulls Snowflake data for all tenants → saves raw cache → merges into `data/audit_aggregate.json` → updates `data/groups.json` → commits and pushes.

### Run a single tenant

```bash
./run_audit.sh --tenant-id 444875142
```

Updates the aggregate for that tenant only; does not update group membership.

### Reprocess (no Snowflake — check logic or threshold changes only)

```bash
./run_audit.sh --reprocess                    # all cached tenants
./run_audit.sh --reprocess --tenant-id 12345  # single tenant
```

Re-runs all checks against `data/raw/*.json` without querying Snowflake. Use whenever you change `checks.py`, `constants.py`, or `evaluate.py`.

### Manual export workflow (no Snowflake connector)

1. Set tenant ID in `sql/00_combined_audit.sql` and run it in Snowflake (returns 10 rows).
2. Export to Excel or CSV.
3. Merge into the aggregate:
   ```bash
   python3 audit_report.py --from-excel /path/to/results.xlsx --output-aggregate data/audit_aggregate.json
   ```

---

## CLI options

| Option | Description |
|--------|-------------|
| `--from-snowflake` | Pull live data from Snowflake; requires `--tenant-id` or `--tenant-group` |
| `--reprocess` | Re-run checks against cached raw data (no Snowflake); requires `--output-aggregate` |
| `--tenant-id ID` | Single tenant ID |
| `--tenant-group NAME` | Run all tenants in a named group (e.g. `"T3 Services Group"`) |
| `--from-excel FILE` | Read from `.xlsx` or combined CSV |
| `--from-csv-folder FOLDER` | Read from a folder of per-query CSV files |
| `--from-results JSON` | Read from a saved results JSON |
| `--output-aggregate FILE` | Merge this run into the aggregate JSON |
| `--lookback-days N` | Lookback window (default: 90) |
| `--html FILE` | Write a static HTML scorecard (legacy — not used by standard workflow) |
| `--tenant-name NAME` | Override tenant name in output |

---

## Website (GitHub Pages)

The site is hosted at:
```
https://rstare-ship-it.github.io/Inventory_Setup_Usage_Audit/
```

Key links:
- Home / search: `/`
- SILA group: `/group.html?group=SILA`
- T3 Services Group: `/group.html?group=T3_Services_Group`
- Individual tenant: `/scorecard.html?tenant_id=444875142`

To enable (first time): **Settings → Pages → Source: Deploy from branch → main / root → Save**.

---

## Project structure

```
Inventory_Setup_Usage_Audit/
├── index.html                  # Search entry point
├── group.html                  # Dynamic group summary page (?group=SILA)
├── scorecard.html              # Dynamic per-tenant scorecard (?tenant_id=444875142)
├── data/
│   ├── audit_aggregate.json    # All tenant audit results (keyed by tenant_id)
│   ├── groups.json             # Group membership (tenant ID lists per group)
│   └── raw/                    # Cached raw Snowflake results per tenant ({tenant_id}.json)
├── audit/
│   ├── aggregate.py            # Merge tenant runs into aggregate; update groups.json
│   ├── checks.py               # Individual check functions
│   ├── constants.py            # All thresholds and area lists — edit here
│   ├── data.py                 # Data loading (Snowflake, Excel, CSV)
│   ├── evaluate.py             # Area evaluation logic
│   ├── parse.py                # Parse raw query results into structured data
│   └── render.py               # HTML rendering (legacy static scorecard)
├── audit_report.py             # CLI entrypoint
├── run_audit.sh                # Orchestrate group/tenant runs + git commit/push
├── sql/
│   └── 00_combined_audit.sql   # Combined audit query (10 rows)
├── requirements.txt            # Python deps: snowflake-connector, openpyxl, python-dotenv
├── .env.example                # Snowflake credentials template
├── THRESHOLD_VALIDATION.md     # Threshold rationale and validation
└── README.md                   # This file
```

---

## Related

- [Inventory Readiness Check](../Inventory_Prepardness_Check) — for tenants *not yet on* inventory; this audit reuses its PO, invoice, and replenishment checks.
