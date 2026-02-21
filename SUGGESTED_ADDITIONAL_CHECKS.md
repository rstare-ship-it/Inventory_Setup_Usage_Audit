# Suggested Additional Data Point Checks — Inventory Setup & Usage Audit

This document lists **additional data point checks** you could add to assess a customer’s usage or setup of inventory. They complement the existing scorecard (purchasing, invoicing, technician usage, replenishment, returns, pricebook & setup, usage & operations).

**Implemented (as of latest update):** The following are now in the audit SQL and report: **% of material lines that are IsInventory**, **zero-cost IsInventory lines**, **% of material lines from transfer**, **PO receive rate**, **materials with no UoM**, **IsInventory materials with no invoice usage in 90 days**, **warehouses with no completed count in 90 days.** Re-run the combined audit query (and use the resulting 9-row export) to populate the extended invoice and usage columns.

---

## Purchasing & receiving

| Check | What to measure | Why it helps |
|-------|------------------|--------------|
| **PO receive rate / time** | % of POs (or PO lines) fully received within N days of creation; or median days from PO created to last receive. | Surfaces slow or incomplete receiving; complements “pending POs” and “completed in period.” |
| **Bills from POs** | Count or % of received POs that have a linked bill (or bill lines from PO) in the period. | Validates that “received” inventory is being matched to AP (three-way match). |
| **Single-vendor vs multi-line POs** | Distribution of POs by number of vendors or by number of lines (you already have single-line; could add “POs with 10+ lines” as a positive signal). | More lines per PO often indicates better batching and process maturity. |
| **PO approval workflow usage** | When purchase approval is on: count POs in PendingApproval (status 6) and avg time in that status. | Highlights bottlenecks in approval. |

*Relevant tables (tenant_data.DBO):* `PurchaseOrder`, `PurchaseOrderItem`, `Bill`, `BillItem` (or equivalent AP tables); join by PO reference where available.

---

## Invoicing & material flow

| Check | What to measure | Why it helps |
|-------|------------------|--------------|
| **% of material lines that are IsInventory** | Of all invoice material lines (SKU type = Material), what % reference an IsInventory material? | You already have “% of $>0 invoices with ≥1 IsInventory line”; this adds “how much of what they invoice is actually tracked in inventory.” |
| **Invoice lines from transfer vs added manually** | Count material lines that came from a job transfer vs added directly (e.g. by `INVENTORYTRANSFER` or similar linkage). | High “from transfer” suggests techs are using truck stock and transfers; low may mean office add or workarounds. |
| **Zero-cost inventory lines** | Count of invoice material lines where the material is IsInventory but cost/price is 0 (or below a threshold). | May indicate “Add items at $0” from PO or cost not flowing from inventory. |
| **Estimates vs invoices** | For jobs with estimates: do material lines on the invoice exist on the estimate (or vice versa)? Count jobs where invoice has materials but estimate had none. | Surfaces whether materials are being added only at invoice (no estimate discipline). |

*Relevant tables:* `InvoiceItem`, `Material`, `Invoice`; `INVENTORYTRANSFER` (link to job/invoice if available); estimate/quote tables if present.

---

## Technician & field usage

| Check | What to measure | Why it helps |
|-------|------------------|--------------|
| **Transfers per job / per tech** | Count of completed transfers to jobs in the period; per tech or per job. | Complements “technician-added %” by showing whether transfers (truck → job) are actually used. |
| **Mobile inventory usage** | If you have a flag or audit for “created via mobile” (e.g. on InvoiceItem or transfer): % of material adds or transfers from mobile. | Indicates field adoption of the inventory mobile app. |
| **Trucks with recent transfer activity** | Of trucks with a template, how many had at least one transfer (to job or replenishment) in the last 30 days? | Identifies trucks that are set up but never used. |

*Relevant tables:* `INVENTORYTRANSFER` (and link to `USER`/technician if available), `TRUCK`, `InvoiceItem.CREATEDBY_ID` (you already use this for tech role).

---

## Replenishment & stock levels

| Check | What to measure | Why it helps |
|-------|------------------|--------------|
| **Replenishment request to PO** | Of completed replenishment requests, how many have an associated PO (or PO created from replenishment)? | Validates that replenishment is driving purchasing. |
| **Requested vs received quantity** | For replenishment lines (or POs created from replenishment), compare requested qty to received qty; flag large under-receives. | Surfaces systematic short-ships or data entry issues. |
| **Stockouts / zero-on-hand after activity** | Count of SKU/location combinations that had a transfer-out or invoice usage in the period and then had 0 (or negative) quantity. | “True” stockouts after usage. |
| **Min/max vs actual** | If min/max or reorder points exist: count SKU/locations where current quantity is below min (or above max) and no open replenishment. | Indicates templates or reorder rules not aligned with usage. |

*Relevant tables:* `REPLENISHMENTREQUEST`, `REPLENISHMENTREQUESTITEM` (or similar), `PurchaseOrder`, `INVENTORYBALANCE`, `INVENTORYTRACKING`; template or SKU min/max if stored.

---

## Pricebook & setup (deeper)

| Check | What to measure | Why it helps |
|-------|------------------|--------------|
| **Materials with no unit of measure** | Count of active IsInventory materials with no UoM (or `HASUNITOFMEASURE = 0`). You already have “with unit of measure: 0” in setup summary. | Could be a **scorecard rule**: e.g. yellow if >10% of IsInventory materials lack UoM. |
| **Duplicate or near-duplicate materials** | Count of materials that share the same name or SKU (or normalized name). | Surfaces pricebook clutter and possible double-ordering. |
| **Inventory SKUs never used in period** | Count of IsInventory SKUs (material or equipment) with no invoice line, transfer, or adjustment in the last 90 days. | “Dead” inventory or over-setup. |
| **Template vs actual truck usage** | Compare template item set to materials actually transferred/used from that truck in the period. | Templates that don’t match what techs use. |
| **Warehouse vs truck balance** | Ratio of total quantity in warehouses vs on trucks (by value or quantity). | Helps assess whether stock is concentrated in the right place. |

*Relevant tables:* `Material`, `Equipment`, `INVENTORYSKU`, `INVENTORYTEMPLATE`, `INVENTORYTEMPLATEITEM`, `INVENTORYBALANCE`, `TRUCK`, `WAREHOUSE`.

---

## Counts & accuracy

| Check | What to measure | Why it helps |
|-------|------------------|--------------|
| **Variance at last count** | For locations/SKUs that had a recent inventory count: (count quantity − system quantity at count time); count or % with variance above a threshold. | Direct measure of record accuracy. |
| **Count frequency** | For each warehouse (and optionally truck): days since last completed count; flag no count in 90+ days. | Complements “past due counts” with “never counted.” |
| **Adjustments after count** | After a count is completed, how many adjustments (by type) were created? Large adjustment volume can indicate count quality or process issues. | You already have “direct adjustments”; this ties adjustments to counts. |

*Relevant tables:* `INVENTORYCOUNT`, `INVENTORYCOUNTITEM` (or equivalent), `INVENTORYADJUSTMENT`, `INVENTORYBALANCE`.

---

## Returns & credits

| Check | What to measure | Why it helps |
|-------|------------------|--------------|
| **Time to credit received** | For returns that reached “CreditReceived”: median (or p95) days from return created to status = CreditReceived. | Complements “pending >90d” with velocity of resolution. |
| **Returns with no matching receive** | Returns that are “received” but have no corresponding inventory receive or credit in the same period. | Data or process gap. |

*Relevant tables:* `InventoryReturn` (you already use); receive/credit tables if separate.

---

## Operations & process health

| Check | What to measure | Why it helps |
|-------|------------------|--------------|
| **Requisition to transfer (or to job)** | Requisitions completed (fulfilled) in period vs created; or time from requisition created to first transfer. | Item requisitions adoption and speed. |
| **Consignment** | If consignment is on: consignment balance, consignment returns, and aging. | Only relevant when feature is enabled. |
| **Serialized equipment** | If serialized tracking is on: count of serialized equipment with no current location or with negative movement. | Data quality for serialized flow. |
| **Granular WAC** | If Granular WAC is on: count of locations/SKUs with missing or zero cost; or large WAC variance vs standard cost. | Costing discipline. |

*Relevant tables:* `REQUISITION`, consignment-specific tables, `Equipment`, WAC/cost tables.

---

## Summary: quick wins vs larger lifts

- **Quick to add (same query shape as today):**
  - % of material lines that are IsInventory.
  - Materials (or IsInventory materials) with no UoM as a scorecard rule.
  - Trucks with templates but no transfer activity in 30 days.
  - Count frequency (days since last completed count per warehouse).

- **Medium (new subqueries or one extra row in combined SQL):**
  - PO receive rate or “received POs with a bill.”
  - Replenishment requests with an associated PO.
  - Invoice lines at $0 cost (IsInventory).
  - Inventory SKUs with no movement in 90 days.

- **Larger (new tables or complex logic):**
  - Variance at last count.
  - Estimate vs invoice material alignment.
  - Template vs actual truck usage.

If you tell me which area you want to extend first (e.g. “receiving” or “invoicing depth”), I can sketch the exact SQL and where to plug it into `00_combined_audit.sql` and `audit_report.py`.
