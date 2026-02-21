# Pass/Fail Threshold Validation — Home Service Trades

This document validates the audit thresholds in `audit_report.py` against what we’d expect to be acceptable for **home service trades** businesses (HVAC, plumbing, electrical, etc.) already using the inventory module.

---

## Online / industry data check

**Searches performed:** home service trades inventory KPIs, field service replenishment/PO metrics, technician invoice/material usage benchmarks, pending PO and cycle count benchmarks.

**What was found:**

- **General KPIs** (HVAC/plumbing): Technician utilization target **75%+**; contribution margin targets **~70%+**; first-time fix rate in field service **~77%** (inventory issues cited as a cause of failures). These support a “high bar” mindset but are not the same as our metrics.
- **Best practices:** Standardize processes, audit inventory, automate procurement/POs, cycle count for accuracy, address aging and bottlenecks. No published numeric thresholds for “max pending POs,” “% invoices with material lines,” “replenishment completion rate,” or “max past due counts.”
- **PO cycle time:** Top performers issue POs in under ~5 hours; aging and pending PO counts are monitored for bottlenecks—but no industry standard for a specific “red at 50 pending” cap.
- **Cycle counts:** Industry guidance aims for very high (near 100%) inventory record accuracy and recommends addressing past-due counts; no benchmark for “max 5 past due” as a pass/fail line.

**Conclusion:** There is **no published benchmark data** that directly specifies acceptable values for our exact thresholds (e.g., 50 pending POs, 75%/50% invoice material bands, 70% replenishment rate, 20 aging requests, 5 past due counts). The validation below is therefore based on **codebase alignment** (Inventory Readiness Check), **first-principles reasoning** for field service, and **loose alignment** with industry themes (e.g., 75% green bar is in the same “high performer” range as utilization/first-time fix; strict past-due count cap supports “address compliance” guidance). If you have internal benchmarks or customer data, those should take precedence.

---

## Purchase orders

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **TOTAL_PENDING_ABSOLUTE_RED** | 50 | Red when total pending POs > 50. For 1–5 truck shops this is high; for 20+ trucks it can be normal. 50 is a reasonable “investigate” cap. **Acceptable.** |
| **PO_SINGLE_LINE_MAJORITY** | 0.5 (50%) | Red when >50% of POs have only one line. Suggests batching or weak PO discipline. 50% is a reasonable fail bar. **Acceptable.** |
| **PO_PLACEHOLDER_MAJORITY** | 0.5 (50%) | Red when >50% of PO lines are placeholder/generic. Same idea as above. **Acceptable.** |

---

## Invoices (material usage)

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **INVOICE_GT_ZERO_WITH_MATERIAL_GREEN_MIN_PCT** | 75% | Green when ≥75% of $>0 invoices have ≥1 inventory material line. Strong signal that invoicing is tied to inventory. **Acceptable.** |
| **INVOICE_GT_ZERO_WITH_MATERIAL_YELLOW_MIN_PCT** | 50% | Yellow 50–75%. Sensible middle band. **Acceptable.** |
| **INVOICE_TECH_ADDED_GREEN_MIN_PCT** | 50% | Green when ≥50% of material lines are technician-added. Field service expects techs to add parts on invoices. **Acceptable.** |
| **INVOICE_TECH_ADDED_YELLOW_MIN_PCT** | 30% | Yellow 30–49%. **Acceptable.** |
| **INVOICE_PLACEHOLDER_GREEN_MAX_PCT** | 10% | Green when placeholder-like lines <10%. **Acceptable.** |
| **INVOICE_PLACEHOLDER_RED_MIN_PCT** | 70% | Red when >70% placeholder. **Acceptable.** |

---

## Replenishment

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **REPLENISHMENT_RATE_GREEN_MIN_PCT** | 70% | Rate = 100×(1 − open/completed). Green when ≥70% (open ≤ ~30% of completed). Shows replenishment is being closed out. **Acceptable.** |
| **REPLENISHMENT_RATE_YELLOW_MIN_PCT** | 50% | Yellow 50–70%. **Acceptable.** |

---

## Returns

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **RETURN_PENDING_PCT_MAX** | 10% | Yellow when pending returns >10% of returns in the period. Encourages timely resolution. **Acceptable.** |

---

## Setup (trucks / warehouses / templates)

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **TRUCK_TEMPLATE_PCT_MIN** | 80% | At least 80% of active trucks with an inventory template. Allows for a few trucks not yet onboarded. **Acceptable.** |
| **WAREHOUSE_WITH_TEMPLATE_MIN** | 1 | At least one active warehouse with a template. Minimum viable setup. **Acceptable.** |
| **TEMPLATE_MIN_ACTIVE_ITEMS** | 20 | Each template ≥20 active items. Home service trucks/warehouses typically carry a meaningful set of parts; 20 is a reasonable floor. **Acceptable.** |

---

## Usage (aging and adjustments)

| Threshold | Value | Rationale |
|-----------|--------|------------|
| **USAGE_REPLENISHMENT_OLD_30D_MAX** | 20 | Red when >20 replenishment requests older than 30 days. Reasonable cap for “address aging.” **Acceptable.** |
| **USAGE_TRANSFERS_OLD_14D_MAX** | 20 | Red when >20 pending transfers older than 14 days. **Acceptable.** |
| **USAGE_REQUISITIONS_OLD_90D_MAX** | 20 | Red when ≥20 requisitions older than 90 days. **Acceptable.** |
| **USAGE_PAST_DUE_COUNTS_MAX** | 5 | Red when >5 past due inventory counts. Strict but good for driving cycle-count discipline. **Acceptable.** |
| **USAGE_DIRECT_ADJUSTMENTS_MAX** | 20 | Red when >20 direct (type 0) adjustments in last 90 days. High volume can indicate workarounds or poor receiving. **Acceptable.** |

---

## Summary

- **All current pass/fail values are within what we’d expect to be acceptable** for home service trades businesses using inventory, based on codebase alignment and first-principles reasoning.
- **Online search:** No industry benchmarks were found that define these exact numbers; general KPIs (e.g., 75% utilization, ~77% first-time fix) support a “high bar” mindset but don’t map 1:1 to our metrics. See “Online / industry data check” above.
- They align with the Inventory Readiness Check (same or similar thresholds where applicable) and are tuned for field service (invoices, tech-added materials, trucks, replenishment, aging).
- **Optional tweaks** you could consider (not required):
  - **TEMPLATE_MIN_ACTIVE_ITEMS**: Some very small operations might legitimately have 15–20 items; 20 is still a reasonable minimum.
  - **TOTAL_PENDING_ABSOLUTE_RED**: If you see many large, healthy tenants hitting red, you could raise to 75–100; 50 is conservative and safe for “investigate.”

---

## README vs code

`README.md` mentions `REPLENISHMENT_OPEN_YELLOW` (default 300); that threshold lives in the **Inventory Readiness Check** app, not in this Setup/Usage Audit. This audit uses **replenishment rate** (open vs completed) instead. No change needed; just a clarification.
