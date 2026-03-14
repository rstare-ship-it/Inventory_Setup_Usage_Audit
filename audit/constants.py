"""
All threshold constants, area lists, and result-key definitions for the inventory audit.
Edit thresholds here; no changes needed elsewhere.
"""
from __future__ import annotations

# Result set keys (combined query returns 10 rows)
RESULT_KEYS = [
    "tenant_info",
    "pricebook",
    "purchase_orders_summary",
    "invoice_materials",
    "replenishment_summary",
    "returns_summary",
    "assessment_data",
    "inventory_settings",
    "setup_data",
    "usage_checks",
]

# PO status codes (ServiceTitan app model)
# 0=Pending, 1=Exported, 2=Sent, 3=PartiallyReceived, 4=Received, 5=Canceled, 6=PendingApproval
PENDING_STATUS_WAITING_TO_SEND = 0
PENDING_STATUSES = (0, 6, 2, 3)
COMPLETED_STATUSES = (4, 1)

# --- Purchasing thresholds ---
TOTAL_PENDING_ABSOLUTE_RED = 50
PENDING_POS_ALLOWED_PER_TRUCK = 0.5   # allowed = half of truck count

# Pending as % of allowed (lower is better)
PENDING_PCT_OF_ALLOWED_GOOD_MAX = 25
PENDING_PCT_OF_ALLOWED_OKAY_MAX = 40
PENDING_PCT_OF_ALLOWED_REVIEW_MAX = 60

# Pending over 90 days as % of allowed (lower is better)
PENDING_OVER_90_PCT_GOOD_MAX = 5
PENDING_OVER_90_PCT_OKAY_MAX = 10
PENDING_OVER_90_PCT_REVIEW_MAX = 30

# PO multi-line % (higher is better): <40% red, 40-50% review, 50-60% yellow, >60% green
PO_MULTI_LINE_RED_MAX_PCT = 40
PO_MULTI_LINE_REVIEW_MAX_PCT = 50
PO_MULTI_LINE_YELLOW_MIN_PCT = 50
PO_MULTI_LINE_YELLOW_MAX_PCT = 60

# PO receive rate % (higher is better): ≥80% Good, 65-80% Okay, 50-65% Needs review, <50% Needs attention
PO_RECEIVE_RATE_GOOD_MIN_PCT = 80
PO_RECEIVE_RATE_OKAY_MIN_PCT = 65
PO_RECEIVE_RATE_REVIEW_MIN_PCT = 50

PO_PLACEHOLDER_MAJORITY = 0.5   # red if > 50% of PO lines are placeholder/generic

# --- Invoicing thresholds ---
# % of invoices > $0 that have ≥1 IsInventory material line (higher is better)
INVOICE_GT_ZERO_WITH_MATERIAL_GOOD_MIN_PCT = 85
INVOICE_GT_ZERO_WITH_MATERIAL_OKAY_MIN_PCT = 75
INVOICE_GT_ZERO_WITH_MATERIAL_REVIEW_MIN_PCT = 50

# Technician-added % (higher is better)
INVOICE_TECH_ADDED_GOOD_MIN_PCT = 60
INVOICE_TECH_ADDED_OKAY_MIN_PCT = 50
INVOICE_TECH_ADDED_REVIEW_MIN_PCT = 30

# % of material lines that are IsInventory (higher is better)
INVOICE_MATERIAL_LINES_ISINVENTORY_GOOD_MIN_PCT = 85
INVOICE_MATERIAL_LINES_ISINVENTORY_OKAY_MIN_PCT = 75
INVOICE_MATERIAL_LINES_ISINVENTORY_REVIEW_MIN_PCT = 50

# Zero-cost IsInventory lines (lower is better)
INVOICE_ZERO_COST_GOOD_MAX_PCT = 3
INVOICE_ZERO_COST_OKAY_MAX_PCT = 5
INVOICE_ZERO_COST_REVIEW_MAX_PCT = 15

# --- Replenishment thresholds ---
REPLENISHMENT_RATE_GOOD_MIN_PCT = 80
REPLENISHMENT_RATE_OKAY_MIN_PCT = 70
REPLENISHMENT_RATE_REVIEW_MIN_PCT = 50

# --- Returns thresholds ---
RETURN_CREDIT_RECEIVED_STATUS = 2
RETURN_PENDING_PCT_GOOD_MAX = 5
RETURN_PENDING_PCT_OKAY_MAX = 10
RETURN_PENDING_PCT_REVIEW_MAX = 20

# --- Setup thresholds ---
TRUCK_TEMPLATE_PCT_MIN = 80        # at least 80% of trucks must have a template
WAREHOUSE_WITH_TEMPLATE_MIN = 1    # at least 1 warehouse with a template
TEMPLATE_MIN_ACTIVE_ITEMS = 20     # each template should have ≥20 active items

# --- Usage / operations thresholds ---
USAGE_REPLENISHMENT_OLD_30D_MAX = 20
USAGE_TRANSFERS_OLD_14D_MAX = 20
USAGE_REQUISITIONS_OLD_90D_MAX = 20
USAGE_PAST_DUE_COUNTS_MAX = 5
USAGE_DIRECT_ADJUSTMENTS_MAX = 20

# Transfers: expect half of trucks × 1 transfer per week over lookback
TRANSFER_EXPECTED_TRUCK_FRACTION = 0.5

# Extended: IsInventory materials with no invoice usage in 90 days (higher % unused = worse)
MATERIALS_UNUSED_90D_YELLOW_MAX_PCT = 50
MATERIALS_UNUSED_90D_RED_MIN_PCT = 75

# Warehouses with no completed count in last 90 days (0 = all must have one)
WAREHOUSES_NO_COUNT_90D_MAX = 0

# --- Pricebook readiness (purchasing audit) ---
PRICEBOOK_RED_PCT = 0.25           # red if > 25% have $0 cost or Default Replenishment as primary

# --- Go-live readiness ---
GO_LIVE_ITEMS_INVENTORY_MIN_PCT = 50   # at least half of materials marked IsInventory

# --- Audit areas ---
# Full inventory audit (display order)
AUDIT_AREAS = [
    "Pricebook & setup",
    "Purchasing",
    "Invoicing",
    "Replenishment",
    "Returns",
    "Transfers",
    "Counts and adjustments",
    "Other",
]

# Purchasing-only audit (not yet live with inventory)
AUDIT_AREAS_PURCHASING = [
    "Pricebook",
    "Purchasing",
    "Invoicing",
    "Replenishment",
    "Returns",
]

# Areas that must be red-free before inventory implementation is considered ready
READINESS_AREAS = ["Pricebook", "Purchasing", "Invoicing"]

# Settings we show in the scorecard (camelCase and PascalCase variants)
SETTINGS_WE_CARE_ABOUT = [
    "beginningDate", "BeginningDate",
    "allowCopyingPoItemsToInvoice", "AllowCopyingPoItemsToInvoice",
    "allowNegativeQuantityOnHand", "AllowNegativeQuantityOnHand",
    "allowNegativeQuantityOnInvoice", "AllowNegativeQuantityOnInvoice",
    "autoApplyTagsToJobsBasedOnPoStatus", "AutoApplyTagsToJobsBasedOnPoStatus",
    "autoApplyTagsToJobsBasedOnTransferStatus", "AutoApplyTagsToJobsBasedOnTransferStatus",
    "autoAssignTruckToJobTransfers", "AutoAssignTruckToJobTransfers",
    "dontAutomaticallyCreateBills", "DontAutomaticallyCreateBills",
    "inventoryValuationMethod", "InventoryValuationMethod",
    "isBinTrackingEnabled", "IsBinTrackingEnabled",
    "isConsignmentInventoryTrackingEnabled", "IsConsignmentInventoryTrackingEnabled",
    "isInventoryMobileAppEnabled", "IsInventoryMobileAppEnabled",
    "isSerializedTrackingEnabled", "IsSerializedTrackingEnabled",
    "onlyReplenishMax", "OnlyReplenishMax",
    "poItemCostCopyOption", "PoItemCostCopyOption",
    "purchaseOrderApprovalField", "PurchaseOrderApprovalField",
]

INVENTORY_SETTING_LABELS: dict[str, str] = {
    "beginningDate": "Inventory tracking start date",
    "BeginningDate": "Inventory tracking start date",
    "isBeginningDateStarted": "Tracking start date has passed",
    "IsBeginningDateStarted": "Tracking start date has passed",
    "allowNegativeQuantityOnHand": "Allow negative quantity on hand",
    "AllowNegativeQuantityOnHand": "Allow negative quantity on hand",
    "onlyReplenishMax": "Only replenish max",
    "OnlyReplenishMax": "Only replenish max",
    "isSerializedTrackingEnabled": "Serialized tracking enabled",
    "IsSerializedTrackingEnabled": "Serialized tracking enabled",
    "isBinTrackingEnabled": "Bin tracking enabled",
    "IsBinTrackingEnabled": "Bin tracking enabled",
    "inventoryValuationMethod": "Inventory valuation method",
    "InventoryValuationMethod": "Inventory valuation method",
    "allowNegativeQuantityOnInvoice": "Allow negative quantity on invoice",
    "AllowNegativeQuantityOnInvoice": "Allow negative quantity on invoice",
    "dontAutomaticallyCreateBills": "Don't automatically create bills",
    "DontAutomaticallyCreateBills": "Don't automatically create bills",
    "allowCopyingPoItemsToInvoice": "Automatically add PO Items to Invoice",
    "AllowCopyingPoItemsToInvoice": "Automatically add PO Items to Invoice",
    "poItemCostCopyOption": "PO item cost copy option",
    "PoItemCostCopyOption": "PO item cost copy option",
    "autoApplyTagsToJobsBasedOnPoStatus": "Auto apply PO Tags to Jobs",
    "isInventoryMobileAppEnabled": "Inventory mobile app enabled",
    "IsInventoryMobileAppEnabled": "Inventory mobile app enabled",
    "isConsignmentInventoryTrackingEnabled": "Consignment inventory tracking enabled",
    "IsConsignmentInventoryTrackingEnabled": "Consignment inventory tracking enabled",
    "autoAssignTruckToJobTransfers": "Assign Truck for Transfer (TTJ)",
    "purchaseOrderApprovalField": "Purchase order approval field",
    "PurchaseOrderApprovalField": "Purchase order approval field",
    "autoApplyTagsToJobsBasedOnTransferStatus": "Auto apply Transfer Tags to Jobs",
    "enableUnitOfMeasure": "Enable unit of measure",
    "EnableUnitOfMeasure": "Enable unit of measure",
}

INVENTORY_VALUATION_NAMES: dict[int, str] = {
    0: "Standard costing",
    1: "Weighted average",
    2: "Weighted average (granular)",
}
TRACKING_DISPOSITION_NAMES: dict[int, str] = {0: "Singular", 1: "Dual"}
PO_APPROVAL_FIELD_NAMES: dict[int, str] = {
    0: "Purchase order total",
    1: "Purchase order subtotal",
}
REQUISITION_DATE_NEEDED_NAMES: dict[int, str] = {
    0: "30 days",
    1: "1 week",
    2: "2 weeks",
    3: "90 days",
}
PO_ITEM_COST_COPY_NAMES: dict[int, str] = {
    0: "Add items at $0",
    1: "Add items at receipt cost",
}
