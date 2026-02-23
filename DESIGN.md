# Inventory Audit — Design: Script Structure & Hosted Lookup

## 1. Script structure: one file vs separate modules

**Recommendation: split into a small package**, with a single entrypoint script. Right now everything lives in `audit_report.py` (~2200 lines). For the end goal (Snowflake → JSON → aggregated data → hosted lookup), separate layers make it easier to:

- **Ingest** from different sources (Snowflake, JSON file, future: pull from Snowflake stage)
- **Merge** new/updated tenant runs into one aggregated JSON without touching evaluation/HTML
- **Output** either HTML (current) or *only* update the aggregated JSON for the site
- **Test** evaluation and rendering in isolation

Proposed layout:

```
Inventory_Setup_Usage_Audit/
├── audit_report.py          # CLI only: argparse + orchestration (load → evaluate → output)
├── audit/
│   ├── __init__.py
│   ├── constants.py         # RESULT_KEYS, thresholds, AUDIT_AREAS, etc.
│   ├── data.py              # load from JSON/CSV/Excel/Snowflake; data_from_audit_rows; normalize
│   ├── parse.py             # parse_results (raw data → results dict)
│   ├── evaluate.py          # evaluate_audit, evaluate_audit_purchasing_only, get_action_plan
│   ├── render.py            # render_scorecard_html, render_group_summary_html
│   └── aggregate.py         # merge one or many tenant runs into aggregated JSON (for site)
├── sql/
│   └── 00_combined_audit.sql
├── css/
│   └── scorecard.css
├── _data/                   # Jekyll (or site) data
│   └── audit_aggregate.json # one big JSON: tenant_id → { tenant_name, lookback_days, results, ... }
└── (T3_Services_Group/ or other hosted output)
```

- **Keep a single entrypoint**: `audit_report.py` stays the script you run; it imports from `audit.*` and stays thin (arg parsing, one “load → parse → evaluate → render/write” flow).
- **Definitions in separate files**: constants in one place, data loading in another, evaluation in another, HTML rendering in another. “Actions” (CLI commands) stay in `audit_report.py` as different code paths that call into the same functions.

You can refactor incrementally: first extract `constants.py` and `data.py`, then `parse.py`, `evaluate.py`, `render.py`, and finally add `aggregate.py` when you’re ready for the “merge into big JSON” step.

---

## 2. End goal: Snowflake → JSON → hosted lookup

Target flow:

1. **Snowflake** runs a scheduled task that executes the combined audit (e.g. `00_combined_audit.sql`) and writes results — e.g. one JSON per tenant or one JSON with multiple tenants. For now you run/prompt manually; the code should assume “input is JSON from that pipeline.”
2. **Your side** (script or small job):
   - **Pull** the JSON (today: manual; later: sync from stage or API).
   - **Option A — Merge**: Merge this run into a single **aggregated JSON** file (e.g. `_data/audit_aggregate.json`) keyed by `tenant_id` (and/or slug by name). New tenants get added; existing tenants get updated. That file is the source of truth for the site.
   - **Option B — Regenerate HTML**: Keep current behavior (e.g. group run → T3 folder with `index.html` + `scorecard_<id>.html`). You can do both: merge into aggregate *and* write HTML for a group when needed.
3. **Hosted site**: One page where the user enters **tenant name or ID**. The page loads the **large aggregated JSON** and shows that tenant’s scorecard (or a table/detail view). No per-tenant URL required unless you want it (e.g. `/tenant/123` as a static page).

Designing the script around this means:

- **Input**: Prefer “read from JSON” as the main path (same shape Snowflake will produce). Snowflake, CSV, Excel become alternative loaders that normalize to that shape.
- **Output**: Support (1) writing HTML (current), and (2) writing or **merging** into one aggregated JSON file so the site can consume it.
- **Aggregate schema**: Decide a minimal schema for “one tenant in the big file” (e.g. `tenant_id`, `tenant_name`, `lookback_days`, `results`, `findings_by_area`, `area_statuses`, `action_plan`, `is_live`, `updated_at`) so both the script and the front-end can rely on it.

---

## 3. Jekyll vs plain static for “lookup by tenant”

**Both work.** The important part is: the site is static and the “lookup” is either (a) client-side JS reading one big JSON, or (b) pre-built static pages per tenant.

- **Jekyll**
  - **Good for**: Multiple pages (landing, docs, per-tenant pages if you want), templating (e.g. one layout for scorecard), and a single `_data/audit_aggregate.json` that Jekyll can expose as a static file or inject into a page. You can add more tenants to that JSON over time and redeploy.
  - **How lookup works**: One “app” page (e.g. `lookup.html` or `index.html`) that includes or fetches `audit_aggregate.json` and uses JavaScript to filter by tenant name/ID and render the scorecard (or link to a pre-built page). Or: Jekyll loops over the aggregate and generates `/tenants/123.html` for each tenant; the “lookup” is then just linking to that URL.
  - **Verdict**: Jekyll is a **good fit** if you want to grow the site (multiple sections, consistent layout, versioned content). It’s not strictly required for “one page + one big JSON + search.”

- **Plain static (no Jekyll)**
  - **Good for**: Simplest setup: one `index.html`, one `data/audit_aggregate.json`, and JS that fetches the JSON and shows the tenant’s data when the user searches. You already have `.nojekyll`; you can keep serving static files only.
  - **Verdict**: Enough for “input tenant name/ID → load from big JSON and display.” Use this if you don’t need Jekyll’s templating or multi-page structure.

**Recommendation**: Use **Jekyll** if you plan on more than one page (e.g. landing + lookup + maybe docs or per-tenant URLs). Use **plain static** if the site will stay “one lookup page + one JSON file.” In both cases, the script should produce the same aggregated JSON; only where you put it and how you serve it changes (`_data/` for Jekyll, or a `data/` folder for static).

### How you see a specific tenant

1. **Home page** (or a dedicated lookup page) has a single input: **tenant name or ID**.
2. User types either the numeric tenant ID (e.g. `1792689863`) or a name (e.g. `acme plumbing`). The page matches against the aggregated JSON: by `tenants_by_id[id]` or `tenants_by_slug[slug]` (slug = lowercase, hyphenated name).
3. When there’s a match, the page either:
   - **Renders that tenant’s scorecard in place** (same page), or
   - **Navigates** to a pre-built URL (e.g. `/tenant/1792689863.html` if you generated static pages per tenant with Jekyll).

So yes: you enter the tenant name or ID on the home (or lookup) HTML page; the page then loads the big JSON and shows that tenant’s data. No server required—it’s all client-side JS after the static JSON is loaded.

---

## 4. Aggregated JSON shape (for the site)

So the “large JSON file” stays consistent and the script can merge into it, use a shape like:

```json
{
  "updated_at": "2025-02-20T12:00:00Z",
  "lookback_days": 90,
  "tenants": {
    "1792689863": {
      "tenant_id": 1792689863,
      "tenant_name": "Some Company",
      "lookback_days": 90,
      "is_live": true,
      "area_statuses": { "Pricebook & setup": "Green", ... },
      "action_plan": [...],
      "results": { ... },
      "findings_by_area": { ... }
    }
  }
}
```

Or key by both id and a slug for name lookup:

```json
{
  "tenants_by_id": { "1792689863": { ... } },
  "tenants_by_slug": { "some-company": "1792689863" }
}
```

The script’s **aggregate** step would: read existing `audit_aggregate.json` (if any), merge in the new run(s) by `tenant_id`, write back. That way you “keep building” the file and update specific tenants when you re-run Snowflake for them.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| One file or separate actions/definitions? | **Separate files** by concern (data, parse, evaluate, render, aggregate), with one CLI script that orchestrates. |
| Design for Snowflake scheduled task? | Yes: treat **JSON as the canonical input**; Snowflake will produce it; script only loads and optionally merges. |
| Jekyll correct for “build JSON and add tenants, then lookup”? | **Yes, Jekyll works.** Use it if you want multiple pages/templating; otherwise plain static HTML + JS + one JSON is enough. |
| How does “input tenant name/ID and load” work? | One page loads the **aggregated JSON**; JS filters by tenant and renders that tenant’s scorecard (or navigates to a pre-built static page if you generate per-tenant HTML with Jekyll). |

Next concrete steps can be: (1) add an `--output-json` (and optionally `--merge-into`) to the script that writes or merges the current run into an aggregate file, and (2) refactor the monolith into the `audit/` package over time. The design above supports both without blocking the current T3 HTML workflow.
