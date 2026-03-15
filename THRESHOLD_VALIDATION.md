# Pass/Fail Threshold Validation — Home Service Trades

This document validates the audit thresholds in `audit/constants.py` against what we'd expect to be acceptable for **home service trades** businesses (HVAC, plumbing, electrical, etc.) using purchasing or inventory in ServiceTitan.

---

## Online / industry data check

**Searches performed:** home service trades inventory KPIs, field service replenishment/PO metrics, technician invoice/material usage benchmarks, pending PO and cycle count benchmarks.

**What was found:**

- **General KPIs** (HVAC/plumbing): Technician utilization target **75%+**; contribution margin targets **~70%+**; first-time fix rate in field service **~77%** (inventory issues cited as a cause of failures). These support a "high bar" mindset but are not the same as our metrics.
- **Best practices:** Standardize processes, audit inventory, automate procurement/POs, cycle count for accuracy, address aging and bottlenecks. No published numeric thresholds for "max pending POs," "% invoices with material lines," "replenishment completion rate," or "max past due counts."
- **PO cycle time:** Top performers issue POs in under ~5 hours; aging and pending PO counts are monitored for bottlenecks—but no industry standard for a specific "red at 50 pending" cap.
- **Cycle counts:** Industry guidance aims for very high (near 100%) inventory record accuracy and recommends addressing past-due counts; no benchmark for "max 5 past due" as a pass/fail line.

**Conclusion:** There is **no published benchmark data** that directly specifies acceptable values for our exact thresholds. The validation below is based on **codebase alignment** (Inventory Readiness Check), **first-principles reasoning** for field service, and **loose alignment** with industry themes. If you have internal benchmarks or customer data, those should take precedence.

---

## Pricebook readiness

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **PRICEBOOK_RED_PCT** | 25% | Red when >25% of materials have $0 cost OR use Default/Imported Default Replenishment as primary vendor. Both are signals of incomplete setup that will cause cost and ordering issues. **Acceptable.** |

---

## Purchase orders

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **TOTAL_PENDING_ABSOLUTE_RED** | 50 | Red when total pending POs > 50. For 1–5 truck shops this is high; for 20+ trucks it can be normal. 50 is a reasonable "investigate" cap. **Acceptable.** |
| **PO_RECEIVE_RATE_GOOD_MIN_PCT** | 80% | Green when ≥80% of created POs are received/exported in the lookback period. Strong signal of active PO discipline. **Acceptable.** |
| **PO_RECEIVE_RATE_OKAY_MIN_PCT** | 65% | Yellow 65–79%. Functional but room to improve. **Acceptable.** |
| **PO_RECEIVE_RATE_REVIEW_MIN_PCT** | 50% | Needs Review 50–64%. Low completion rate, needs investigation. **Acceptable.** |
| **PO_MULTI_LINE_YELLOW_MIN_PCT** | 50% | Yellow when ≥50% of POs have more than one line. Single-line POs suggest ordering one item at a time instead of batching. **Acceptable.** |
| **PO_MULTI_LINE_RED_MAX_PCT** | 40% | Red when <40% multi-line. Strong signal of poor PO batching discipline. **Acceptable.** |
| **PO_PLACEHOLDER_MAJORITY** | 0.5 (50%) | Red when >50% of PO lines are placeholder/generic. Same idea as above. **Acceptable.** |

---

## Invoices (material usage)

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **INVOICE_GT_ZERO_WITH_MATERIAL_GOOD_MIN_PCT** | 85% | Green when ≥85% of $>0 invoices have ≥1 inventory material line. Strong signal that invoicing is tied to inventory. **Acceptable.** |
| **INVOICE_GT_ZERO_WITH_MATERIAL_OKAY_MIN_PCT** | 75% | Yellow 75–84%. Sensible middle band. **Acceptable.** |
| **INVOICE_GT_ZERO_WITH_MATERIAL_REVIEW_MIN_PCT** | 50% | Needs Review 50–74%. **Acceptable.** |
| **INVOICE_TECH_ADDED_GOOD_MIN_PCT** | 60% | Green when ≥60% of material lines are technician-added. Field service expects techs to add parts on invoices. **Acceptable.** |
| **INVOICE_TECH_ADDED_OKAY_MIN_PCT** | 50% | Yellow 50–59%. **Acceptable.** |
| **INVOICE_TECH_ADDED_REVIEW_MIN_PCT** | 30% | Needs Review 30–49%. **Acceptable.** |
| **INVOICE_ZERO_COST_GOOD_MAX_PCT** | 3% | Green when zero-cost IsInventory lines <3%. **Acceptable.** |
| **INVOICE_ZERO_COST_OKAY_MAX_PCT** | 5% | Yellow 3–4%. **Acceptable.** |
| **INVOICE_ZERO_COST_REVIEW_MAX_PCT** | 15% | Needs Review 5–14%. **Acceptable.** |

---

## Replenishment

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **REPLENISHMENT_RATE_GOOD_MIN_PCT** | 80% | Green when ≥80% replenishment completion rate (1 − open/completed). Shows replenishment is actively being closed out. **Acceptable.** |
| **REPLENISHMENT_RATE_OKAY_MIN_PCT** | 70% | Yellow 70–79%. **Acceptable.** |
| **REPLENISHMENT_RATE_REVIEW_MIN_PCT** | 50% | Needs Review 50–69%. **Acceptable.** |

---

## Returns

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **RETURN_PENDING_PCT_GOOD_MAX** | 5% | Green when pending returns ≤5% of returns in the period. **Acceptable.** |
| **RETURN_PENDING_PCT_OKAY_MAX** | 10% | Yellow 6–10%. Encourages timely resolution. **Acceptable.** |
| **RETURN_PENDING_PCT_REVIEW_MAX** | 20% | Needs Review 11–20%. **Acceptable.** |

---

## Setup (trucks / warehouses / templates)

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **TRUCK_TEMPLATE_PCT_MIN** | 80% | At least 80% of active trucks must have an inventory template. Allows for a few trucks not yet onboarded. **Acceptable.** |
| **WAREHOUSE_WITH_TEMPLATE_MIN** | 1 | At least one active warehouse with a template. Minimum viable setup. **Acceptable.** |
| **TEMPLATE_MIN_ACTIVE_ITEMS** | 20 | Each template ≥20 active items. Home service trucks/warehouses typically carry a meaningful set of parts; 20 is a reasonable floor. **Acceptable.** |

---

## Usage (aging and adjustments)

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **USAGE_REPLENISHMENT_OLD_30D_MAX** | 20 | Red when >20 replenishment requests older than 30 days. Reasonable cap for "address aging." **Acceptable.** |
| **USAGE_TRANSFERS_OLD_14D_MAX** | 20 | Red when >20 pending transfers older than 14 days. **Acceptable.** |
| **USAGE_REQUISITIONS_OLD_90D_MAX** | 20 | Red when ≥20 requisitions older than 90 days. **Acceptable.** |
| **USAGE_PAST_DUE_COUNTS_MAX** | 5 | Red when >5 past due inventory counts. Strict but good for driving cycle-count discipline. **Acceptable.** |
| **USAGE_DIRECT_ADJUSTMENTS_MAX** | 20 | Red when >20 direct (type 0) adjustments in last 90 days. High volume can indicate workarounds or poor receiving. **Acceptable.** |

---

## Readiness (purchasing-only)

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **GO_LIVE_ITEMS_INVENTORY_MIN_PCT** | 50% | Go-live readiness requires ≥50% of materials marked IsInventory. Below this signals incomplete tagging. **Acceptable.** |

Pre-work qualifiers used by both readiness checks pull from existing thresholds: `PRICEBOOK_RED_PCT` (25%), `PO_RECEIVE_RATE_OKAY_MIN_PCT` (65%), `PO_MULTI_LINE_YELLOW_MIN_PCT` (50%), `INVOICE_TECH_ADDED_REVIEW_MIN_PCT` (30%).

---

## Summary

- **All current pass/fail values are within what we'd expect to be acceptable** for home service trades businesses, based on codebase alignment and first-principles reasoning.
- **Online search:** No industry benchmarks were found that define these exact numbers; general KPIs (e.g., 75% utilization, ~77% first-time fix) support a "high bar" mindset but don't map 1:1 to our metrics.
- They align with the Inventory Readiness Check (same or similar thresholds where applicable) and are tuned for field service (invoices, tech-added materials, trucks, replenishment, aging).
- **Optional tweaks** you could consider (not required):
  - **TEMPLATE_MIN_ACTIVE_ITEMS**: Some very small operations might legitimately have 15–20 items; 20 is still a reasonable minimum.
  - **TOTAL_PENDING_ABSOLUTE_RED**: If you see many large, healthy tenants hitting red, you could raise to 75–100; 50 is conservative and safe for "investigate."
