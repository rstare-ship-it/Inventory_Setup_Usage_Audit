-- Inventory Setup/Usage Audit: one query returning 9 rows (tenant_info, POs, invoice, replenishment, returns, assessment, inventory_settings, setup_data, usage_checks).
-- For tenants already on the inventory module. Export to Excel or CSV; run audit_report.py --from-excel.
-- Columns: source, v1..v16 (shorter rows have NULL in trailing columns). inventory_settings row: v1 = NamedValue VALUE (JSON).
--
-- *** REPLACE 0 BELOW WITH YOUR TENANT ID ***
-- Look up: SELECT _TENANT_ID FROM tenant_data.MASTER_DB.TENANTRECORD WHERE LOWER(_TENANT_NAME) = 'yourtenant' LIMIT 1;
WITH
tenant_param AS (SELECT 0 AS tenant_id),
tenant_info AS (
    SELECT tp.tenant_id AS v1, TRIM(COALESCE(tr._TENANT_NAME, '')) AS v2
    FROM tenant_param tp
    LEFT JOIN tenant_data.MASTER_DB.TENANTRECORD tr ON tr._TENANT_ID = tp.tenant_id
    LIMIT 1
),
-- 1) Purchase orders summary (16 values): same as readiness check
pos_in_period AS (
    SELECT po.ID, po.STATUS, po.CREATEDON, po.MODIFIEDON, po._TENANT_ID
    FROM tenant_data.DBO.PurchaseOrder po
    CROSS JOIN tenant_param tp
    WHERE po.ACTIVE = 1
      AND (
        (po.MODIFIEDON >= DATEADD(day, -90, CURRENT_DATE()) AND po.MODIFIEDON < DATEADD(day, 1, CURRENT_DATE()))
        OR (po.CREATEDON >= DATEADD(day, -90, CURRENT_DATE()) AND po.CREATEDON < DATEADD(day, 1, CURRENT_DATE()))
      )
      AND po._TENANT_ID = tp.tenant_id
),
po_line_counts AS (
    SELECT i.PURCHASEORDER_ID, COUNT(*) AS line_count
    FROM tenant_data.DBO.PurchaseOrderItem i
    JOIN pos_in_period p ON p.ID = i.PURCHASEORDER_ID AND p._TENANT_ID = i._TENANT_ID
    CROSS JOIN tenant_param tp
    WHERE (i.ACTIVE = TRUE OR i.ACTIVE IS NULL)
      AND i._TENANT_ID = tp.tenant_id
    GROUP BY i.PURCHASEORDER_ID
),
lookback_agg AS (
    SELECT
        COUNT(*) AS po_created_in_period,
        MIN(p.CREATEDON) AS earliest_po,
        MAX(p.MODIFIEDON) AS latest_po,
        COALESCE(SUM(CASE WHEN p.STATUS = 0 THEN 1 ELSE 0 END), 0) AS status_0,
        COALESCE(SUM(CASE WHEN p.STATUS = 1 THEN 1 ELSE 0 END), 0) AS status_1,
        COALESCE(SUM(CASE WHEN p.STATUS = 2 THEN 1 ELSE 0 END), 0) AS status_2,
        COALESCE(SUM(CASE WHEN p.STATUS = 3 THEN 1 ELSE 0 END), 0) AS status_3,
        COALESCE(SUM(CASE WHEN p.STATUS = 4 THEN 1 ELSE 0 END), 0) AS status_4,
        COALESCE(SUM(CASE WHEN p.STATUS = 5 THEN 1 ELSE 0 END), 0) AS status_5,
        COALESCE(SUM(CASE WHEN p.STATUS = 6 THEN 1 ELSE 0 END), 0) AS status_6
    FROM pos_in_period p
),
line_quality AS (
    SELECT
        COUNT(*) AS po_count,
        SUM(CASE WHEN plc.line_count = 1 THEN 1 ELSE 0 END) AS pos_with_one_line_only,
        COALESCE(SUM(plc.line_count), 0) AS total_line_items
    FROM po_line_counts plc
),
placeholder_count AS (
    SELECT COUNT(*) AS line_items_placeholder_like
    FROM tenant_data.DBO.PurchaseOrderItem i
    JOIN pos_in_period p ON p.ID = i.PURCHASEORDER_ID AND p._TENANT_ID = i._TENANT_ID
    CROSS JOIN tenant_param tp
    WHERE (i.ACTIVE = TRUE OR i.ACTIVE IS NULL)
      AND i._TENANT_ID = tp.tenant_id
      AND (
          LOWER(COALESCE(i.DESCRIPTION, '')) LIKE '%placeholder%'
          OR LOWER(COALESCE(i.DESCRIPTION, '')) LIKE '%generic%'
          OR LOWER(COALESCE(i.DESCRIPTION, '')) LIKE '%material%'
      )
),
po_row AS (
    SELECT
        (SELECT COUNT(*) FROM tenant_data.DBO.PurchaseOrder po
         CROSS JOIN tenant_param tp_po
         WHERE po.ACTIVE = 1 AND po.STATUS = 0 AND po._TENANT_ID = tp_po.tenant_id) AS v1,
        la.po_created_in_period AS v2,
        la.earliest_po AS v3,
        la.latest_po AS v4,
        la.status_0 AS v5, la.status_1 AS v6, la.status_2 AS v7, la.status_3 AS v8,
        la.status_4 AS v9, la.status_5 AS v10, la.status_6 AS v11,
        lq.po_count AS v12,
        lq.pos_with_one_line_only AS v13,
        lq.total_line_items AS v14,
        pc.line_items_placeholder_like AS v15,
        (SELECT COUNT(*) FROM tenant_data.DBO.PurchaseOrder po
         CROSS JOIN tenant_param tp_old
         WHERE po.ACTIVE = 1 AND po.STATUS = 0 AND po._TENANT_ID = tp_old.tenant_id
           AND po.CREATEDON < DATEADD(day, -90, CURRENT_DATE())) AS v16
    FROM lookback_agg la
    CROSS JOIN line_quality lq
    CROSS JOIN placeholder_count pc
),
-- 2) Invoice material lines (4 values) + invoices with $>0 and with IsInventory material (2 values) + extended (4): IsInventory line count, zero-cost, from transfer, distinct materials used
inv_ext AS (
    SELECT
        COUNT(DISTINCT ii.ID) AS v7,
        COUNT(DISTINCT CASE WHEN (ii.COST IS NULL OR ii.COST = 0) THEN ii.ID END) AS v8,
        COUNT(DISTINCT CASE WHEN ii.USEDMATERIAL_ID IS NOT NULL THEN ii.ID END) AS v9,
        COUNT(DISTINCT ii.SKUREFERENCE_SKUID) AS v10
    FROM tenant_data.DBO.InvoiceItem ii
    JOIN tenant_data.DBO.Invoice i ON i.ID = ii.INVOICE_ID AND i._TENANT_ID = ii._TENANT_ID
    JOIN tenant_data.DBO.Material m ON m.ID = ii.SKUREFERENCE_SKUID AND m._TENANT_ID = ii._TENANT_ID
        AND (m.ARCHIVED = FALSE OR m.ARCHIVED IS NULL) AND (m.ACTIVE = TRUE OR m.ACTIVE IS NULL)
        AND m.ISINVENTORY = 1
    CROSS JOIN tenant_param tp
    WHERE ii.ACTIVE = 1
      AND ii.SKUREFERENCE_SKUTYPE = 1
      AND ii._TENANT_ID = tp.tenant_id
      AND i.INVOICEDON >= DATEADD(day, -90, CURRENT_DATE())
      AND i.INVOICEDON < DATEADD(day, 1, CURRENT_DATE())
),
inv AS (
    SELECT
        inv4.v1, inv4.v2, inv4.v3, inv4.v4,
        igz.invoices_total_gt_zero AS v5,
        igz.invoices_gt_zero_with_material AS v6,
        COALESCE(ie.v7, 0) AS v7,
        COALESCE(ie.v8, 0) AS v8,
        COALESCE(ie.v9, 0) AS v9,
        COALESCE(ie.v10, 0) AS v10
    FROM (
        SELECT
            COUNT(DISTINCT ii.ID) AS v1,
            COUNT(DISTINCT ii.INVOICE_ID) AS v2,
            COUNT(DISTINCT CASE
                WHEN ii.CREATEDBY_ID IS NOT NULL
                     AND ur.BUILTINROLE IS NOT NULL
                     AND (ur.BUILTINROLE = 1 OR BITAND(ur.BUILTINROLE, 512) = 512)
                THEN ii.ID
            END) AS v3,
            COUNT(DISTINCT CASE
                WHEN (LOWER(COALESCE(ii.DESCRIPTION, '') || ' ' || COALESCE(ii.SKUNAME, '')) LIKE '%placeholder%'
                     OR LOWER(COALESCE(ii.DESCRIPTION, '') || ' ' || COALESCE(ii.SKUNAME, '')) LIKE '%generic%'
                     OR LOWER(COALESCE(ii.DESCRIPTION, '') || ' ' || COALESCE(ii.SKUNAME, '')) LIKE '%material%')
                THEN ii.ID
            END) AS v4
        FROM tenant_data.DBO.InvoiceItem ii
        JOIN tenant_data.DBO.Invoice i ON i.ID = ii.INVOICE_ID AND i._TENANT_ID = ii._TENANT_ID
        LEFT JOIN tenant_data.DBO.USER u ON u.ID = ii.CREATEDBY_ID AND u._TENANT_ID = ii._TENANT_ID
        LEFT JOIN tenant_data.DBO.UserRole ur ON ur.ID = u.USERROLE_ID AND ur._TENANT_ID = u._TENANT_ID
        CROSS JOIN tenant_param tp
        WHERE ii.ACTIVE = 1
          AND ii.SKUREFERENCE_SKUTYPE = 1
          AND ii._TENANT_ID = tp.tenant_id
          AND i.INVOICEDON >= DATEADD(day, -90, CURRENT_DATE())
          AND i.INVOICEDON < DATEADD(day, 1, CURRENT_DATE())
    ) inv4
    CROSS JOIN (
        SELECT
            COUNT(*) AS invoices_total_gt_zero,
            COUNT(CASE WHEN mat.INVOICE_ID IS NOT NULL THEN 1 END) AS invoices_gt_zero_with_material
        FROM tenant_data.DBO.Invoice i
        CROSS JOIN tenant_param tp
        LEFT JOIN (
            SELECT DISTINCT ii.INVOICE_ID, ii._TENANT_ID
            FROM tenant_data.DBO.InvoiceItem ii
            JOIN tenant_data.DBO.Material m ON m.ID = ii.SKUREFERENCE_SKUID AND m._TENANT_ID = ii._TENANT_ID
                AND (m.ARCHIVED = FALSE OR m.ARCHIVED IS NULL) AND (m.ACTIVE = TRUE OR m.ACTIVE IS NULL)
                AND m.ISINVENTORY = 1
            WHERE ii.ACTIVE = 1 AND ii.SKUREFERENCE_SKUTYPE = 1
        ) mat ON mat.INVOICE_ID = i.ID AND mat._TENANT_ID = i._TENANT_ID
        WHERE i._TENANT_ID = tp.tenant_id
          AND i.INVOICEDON >= DATEADD(day, -90, CURRENT_DATE())
          AND i.INVOICEDON < DATEADD(day, 1, CURRENT_DATE())
          AND COALESCE(i.TOTAL, 0) > 0
    ) igz
    LEFT JOIN inv_ext ie ON 1 = 1
),
-- 3) Replenishment: open, completed in lookback, used materials can be replenished
repl_row AS (
    SELECT
        (SELECT COUNT(*) FROM tenant_data.DBO.REPLENISHMENTREQUEST rr
         CROSS JOIN tenant_param tp_r
         WHERE rr._TENANT_ID = tp_r.tenant_id
           AND (rr._IS_DELETED = FALSE OR rr._IS_DELETED IS NULL)
           AND (rr.ACTIVE = 1 OR rr.ACTIVE IS NULL)
           AND rr.STATUS IN (0, 1)) AS v1,
        (SELECT COUNT(*) FROM tenant_data.DBO.REPLENISHMENTREQUEST rr
         CROSS JOIN tenant_param tp_r2
         WHERE rr._TENANT_ID = tp_r2.tenant_id
           AND (rr._IS_DELETED = FALSE OR rr._IS_DELETED IS NULL)
           AND rr.STATUS = 2
           AND rr.MODIFIEDON >= DATEADD(day, -90, CURRENT_DATE())
           AND rr.MODIFIEDON < DATEADD(day, 1, CURRENT_DATE())) AS v2,
        (SELECT COUNT(*) FROM tenant_data.DBO.USEDMATERIAL um
         CROSS JOIN tenant_param tp_um
         WHERE um._TENANT_ID = tp_um.tenant_id
           AND (um._IS_DELETED = FALSE OR um._IS_DELETED IS NULL)
           AND (um.ACTIVE = TRUE OR um.ACTIVE IS NULL)
           AND um.STATUS = 0) AS v3
    FROM (SELECT 1) AS one
),
-- 4) Assessment: feature gates, active/isinventory/uom counts, tracking start. v8..v14 = extra FGs + materials with UoM.
assess AS (
    SELECT
        fg."EnablePurchasingModule" AS v1,
        fg."EnableInventoryModule" AS v2,
        (SELECT COUNT(*) FROM tenant_data.DBO.Material m
         CROSS JOIN tenant_param tp_a
         WHERE m._TENANT_ID = tp_a.tenant_id
           AND (m.ARCHIVED = FALSE OR m.ARCHIVED IS NULL) AND (m.ACTIVE = TRUE OR m.ACTIVE IS NULL)) AS v3,
        (SELECT COUNT(*) FROM tenant_data.DBO.Equipment e
         CROSS JOIN tenant_param tp_a2
         WHERE e._TENANT_ID = tp_a2.tenant_id
           AND (e.ARCHIVED = FALSE OR e.ARCHIVED IS NULL) AND (e.ACTIVE = TRUE OR e.ACTIVE IS NULL)) AS v4,
        (SELECT COUNT(*) FROM tenant_data.DBO.Material m
         CROSS JOIN tenant_param tp_a3
         WHERE m._TENANT_ID = tp_a3.tenant_id
           AND (m.ARCHIVED = FALSE OR m.ARCHIVED IS NULL) AND (m.ACTIVE = TRUE OR m.ACTIVE IS NULL) AND m.ISINVENTORY = 1) AS v5,
        (SELECT COUNT(*) FROM tenant_data.DBO.Equipment e
         CROSS JOIN tenant_param tp_a4
         WHERE e._TENANT_ID = tp_a4.tenant_id
           AND (e.ARCHIVED = FALSE OR e.ARCHIVED IS NULL) AND (e.ACTIVE = TRUE OR e.ACTIVE IS NULL) AND e.ISINVENTORY = 1) AS v6,
        (SELECT TRIM(TO_VARCHAR(PARSE_JSON(nv.VALUE):BeginningDate))
         FROM tenant_data.DBO.NamedValue nv
         CROSS JOIN tenant_param tp_a5
         WHERE nv._TENANT_ID = tp_a5.tenant_id
           AND nv.NAME = 'Inventory.Configuration' AND nv.VALUE IS NOT NULL
         ORDER BY nv._RECORD_UPDATED_TS_UTC DESC NULLS LAST
         LIMIT 1) AS v7,
        fg."ItemRequisitions" AS v8,
        fg."RequisitionCloseout" AS v9,
        fg."EnableRequisitionWorkflowForServiceJob" AS v10,
        fg."TransfersToJobs" AS v11,
        fg."ConsignmentInventory" AS v12,
        fg."DisablePurchasingApprovalWorkflow" AS v13,
        fg."EnableGranularWAC" AS v14,
        (SELECT COUNT(*) FROM tenant_data.DBO.INVENTORYSKU sku
         CROSS JOIN tenant_param tp_uom
         WHERE sku._TENANT_ID = tp_uom.tenant_id
           AND (sku.ACTIVE = TRUE OR sku.ACTIVE IS NULL)
           AND sku.SKUREFERENCE_SKUTYPE = 1
           AND sku.ISINVENTORY = 1
           AND sku.HASUNITOFMEASURE = 1) AS v15,
        (SELECT COUNT(*) FROM tenant_data.DBO.Equipment e
         CROSS JOIN tenant_param tp_ser
         WHERE e._TENANT_ID = tp_ser.tenant_id
           AND (e.ARCHIVED = FALSE OR e.ARCHIVED IS NULL) AND (e.ACTIVE = TRUE OR e.ACTIVE IS NULL)
           AND e.ISINVENTORY = 1
           AND e.SERIALIZEDON IS NOT NULL) AS v16
    FROM tenant_data.FEATURE_GATE.FEATURE_GATE_FLAT fg
    CROSS JOIN tenant_param tp_fg
    WHERE fg._TENANT_ID = tp_fg.tenant_id
    LIMIT 1
),
-- 5) Inventory settings from NamedValue (Inventory.Configuration) — full JSON in v1 for readable display
inv_settings AS (
    SELECT nv.VALUE AS v1
    FROM tenant_data.DBO.NamedValue nv
    CROSS JOIN tenant_param tp_nv
    WHERE nv._TENANT_ID = tp_nv.tenant_id
      AND nv.NAME = 'Inventory.Configuration'
      AND nv.VALUE IS NOT NULL
    ORDER BY nv._RECORD_UPDATED_TS_UTC DESC NULLS LAST
    LIMIT 1
),
-- 6) Returns summary (same as readiness): v1=total_pending, v2=in_period, v3=earliest, v4=latest, v5..v8=status_0..3, v9=pending_over_90_days
ret_in_period AS (
    SELECT ir.STATUS, ir.CREATEDON, ir.MODIFIEDON
    FROM tenant_data.DBO.InventoryReturn ir
    CROSS JOIN tenant_param tp
    WHERE ir.ACTIVE = 1
      AND (
        (ir.MODIFIEDON >= DATEADD(day, -90, CURRENT_DATE()) AND ir.MODIFIEDON < DATEADD(day, 1, CURRENT_DATE()))
        OR (ir.CREATEDON >= DATEADD(day, -90, CURRENT_DATE()) AND ir.CREATEDON < DATEADD(day, 1, CURRENT_DATE()))
      )
      AND ir._TENANT_ID = tp.tenant_id
),
ret_row AS (
    SELECT
        (SELECT COUNT(*) FROM tenant_data.DBO.InventoryReturn ir
         CROSS JOIN tenant_param tp_ret
         WHERE ir.ACTIVE = 1 AND ir.STATUS = 0 AND ir._TENANT_ID = tp_ret.tenant_id) AS v1,
        (SELECT COUNT(*) FROM ret_in_period) AS v2,
        (SELECT MIN(CREATEDON) FROM ret_in_period) AS v3,
        (SELECT MAX(MODIFIEDON) FROM ret_in_period) AS v4,
        (SELECT COALESCE(SUM(CASE WHEN STATUS = 0 THEN 1 ELSE 0 END), 0) FROM ret_in_period) AS v5,
        (SELECT COALESCE(SUM(CASE WHEN STATUS = 1 THEN 1 ELSE 0 END), 0) FROM ret_in_period) AS v6,
        (SELECT COALESCE(SUM(CASE WHEN STATUS = 2 THEN 1 ELSE 0 END), 0) FROM ret_in_period) AS v7,
        (SELECT COALESCE(SUM(CASE WHEN STATUS = 3 THEN 1 ELSE 0 END), 0) FROM ret_in_period) AS v8,
        (SELECT COUNT(*) FROM tenant_data.DBO.InventoryReturn ir
         CROSS JOIN tenant_param tp_old
         WHERE ir.ACTIVE = 1 AND ir.STATUS = 0 AND ir._TENANT_ID = tp_old.tenant_id
           AND ir.CREATEDON < DATEADD(day, -90, CURRENT_DATE())) AS v9
    FROM (SELECT 1) AS one
),
-- 7) Setup: trucks/warehouses with templates; templates with < 20 active items
setup_data AS (
    SELECT
        (SELECT COUNT(*) FROM tenant_data.DBO.TRUCK t
         CROSS JOIN tenant_param tp_s
         WHERE t._TENANT_ID = tp_s.tenant_id
           AND (t.ACTIVE = TRUE OR t.ACTIVE IS NULL)) AS v1,
        (SELECT COUNT(*) FROM tenant_data.DBO.TRUCK t
         CROSS JOIN tenant_param tp_s2
         WHERE t._TENANT_ID = tp_s2.tenant_id
           AND (t.ACTIVE = TRUE OR t.ACTIVE IS NULL)
           AND t.TEMPLATE_ID IS NOT NULL) AS v2,
        (SELECT COUNT(*) FROM tenant_data.DBO.WAREHOUSE w
         CROSS JOIN tenant_param tp_s3
         WHERE w._TENANT_ID = tp_s3.tenant_id
           AND (w.ACTIVE = TRUE OR w.ACTIVE IS NULL)) AS v3,
        (SELECT COUNT(*) FROM tenant_data.DBO.WAREHOUSE w
         CROSS JOIN tenant_param tp_s4
         WHERE w._TENANT_ID = tp_s4.tenant_id
           AND (w.ACTIVE = TRUE OR w.ACTIVE IS NULL)
           AND w.TEMPLATE_ID IS NOT NULL) AS v4,
        (SELECT COUNT(*) FROM (
            SELECT it.ID, it._TENANT_ID
            FROM tenant_data.DBO.INVENTORYTEMPLATE it
            JOIN tenant_data.DBO.INVENTORYTEMPLATEITEM iti
              ON iti.TEMPLATE_ID = it.ID AND iti._TENANT_ID = it._TENANT_ID
              AND (iti.ACTIVE = TRUE OR iti.ACTIVE IS NULL)
            CROSS JOIN tenant_param tp_s5
            WHERE it._TENANT_ID = tp_s5.tenant_id
              AND (it.ACTIVE = TRUE OR it.ACTIVE IS NULL)
            GROUP BY it.ID, it._TENANT_ID
            HAVING COUNT(*) < 20
        )) AS v5
    FROM (SELECT 1) AS one
),
-- 8) Usage checks: replenishment >30d, transfers >14d, requisitions >90d, past due counts, negative balances, direct adjustments (type 0)
usage_checks AS (
    SELECT
        (SELECT COUNT(*) FROM tenant_data.DBO.REPLENISHMENTREQUEST rr
         CROSS JOIN tenant_param tp_uc
         WHERE rr._TENANT_ID = tp_uc.tenant_id
           AND (rr._IS_DELETED = FALSE OR rr._IS_DELETED IS NULL)
           AND (rr.ACTIVE = 1 OR rr.ACTIVE IS NULL)
           AND rr.STATUS IN (0, 1)
           AND rr.CREATEDON < DATEADD(day, -30, CURRENT_DATE())) AS v1,
        (SELECT COUNT(*) FROM tenant_data.DBO.INVENTORYTRANSFER it
         CROSS JOIN tenant_param tp_uc2
         WHERE it._TENANT_ID = tp_uc2.tenant_id
           AND (it.ACTIVE = TRUE OR it.ACTIVE IS NULL)
           AND it.EXECUTIONSTATUS = 0
           AND it.CREATEDON < DATEADD(day, -14, CURRENT_DATE())) AS v2,
        (SELECT COUNT(*) FROM tenant_data.DBO.REQUISITION rq
         CROSS JOIN tenant_param tp_uc3
         WHERE rq._TENANT_ID = tp_uc3.tenant_id
           AND (rq.ACTIVE = TRUE OR rq.ACTIVE IS NULL)
           AND rq.STATUS IN (-1, 0)
           AND rq.CREATEDON < DATEADD(day, -90, CURRENT_DATE())) AS v3,
        (SELECT COUNT(*) FROM tenant_data.DBO.INVENTORYCOUNT ic
         CROSS JOIN tenant_param tp_uc4
         WHERE ic._TENANT_ID = tp_uc4.tenant_id
           AND (ic.ACTIVE = TRUE OR ic.ACTIVE IS NULL)
           AND ic.DUEDATE < CURRENT_DATE()
           AND ic.STATUS IN (0, 1, 2)) AS v4,
        -- Current balance = Balance.QuantityAvailable - SUM(Tracking.QuantityAvailable for TRANS_DATE > today); matches Items Overview stock-levels logic (TrackingService.GetBalancesAsync).
        (SELECT COUNT(*) FROM (
            SELECT ib.BIN_ID, ib.SKUREFERENCE_SKUID, ib.DISPOSITION, ib._TENANT_ID,
                (ib.QUANTITYAVAILABLE - COALESCE((
                    SELECT SUM(t.QUANTITYAVAILABLE)
                    FROM tenant_data.DBO.INVENTORYTRACKING t
                    WHERE t.BIN_ID = ib.BIN_ID AND t.SKUREFERENCE_SKUID = ib.SKUREFERENCE_SKUID
                      AND t.DISPOSITION = ib.DISPOSITION AND t._TENANT_ID = ib._TENANT_ID
                      AND (t.ACTIVE = TRUE OR t.ACTIVE IS NULL)
                      AND t.TRANS_DATE > CURRENT_DATE()
                ), 0)) AS current_qty_available
            FROM tenant_data.DBO.INVENTORYBALANCE ib
            CROSS JOIN tenant_param tp_uc5
            WHERE ib._TENANT_ID = tp_uc5.tenant_id
              AND (ib.ACTIVE = TRUE OR ib.ACTIVE IS NULL)
        ) cur
        WHERE cur.current_qty_available < 0) AS v5,
        (SELECT COUNT(*) FROM tenant_data.DBO.INVENTORYADJUSTMENT ia
         CROSS JOIN tenant_param tp_uc6
         WHERE ia._TENANT_ID = tp_uc6.tenant_id
           AND (ia.ACTIVE = TRUE OR ia.ACTIVE IS NULL)
           AND ia.TYPE = 0
           AND ia.CREATEDON >= DATEADD(day, -90, CURRENT_DATE())
           AND ia.CREATEDON < DATEADD(day, 1, CURRENT_DATE())) AS v6,
        (SELECT COUNT(*) FROM tenant_data.DBO.WAREHOUSE w
         CROSS JOIN tenant_param tp_uc7
         WHERE w._TENANT_ID = tp_uc7.tenant_id
           AND (w.ACTIVE = TRUE OR w.ACTIVE IS NULL)
           AND NOT EXISTS (
               SELECT 1 FROM tenant_data.DBO.INVENTORYCOUNT ic
               WHERE ic.LOCATION_ID = w.ID AND ic._TENANT_ID = w._TENANT_ID
                 AND (ic.ACTIVE = TRUE OR ic.ACTIVE IS NULL)
                 AND ic.DATECOMPLETED >= DATEADD(day, -90, CURRENT_DATE())
                 AND ic.DATECOMPLETED < DATEADD(day, 1, CURRENT_DATE()))) AS v7,
        (SELECT COUNT(*) FROM tenant_data.DBO.INVENTORYTRANSFER it
         CROSS JOIN tenant_param tp_uc8
         WHERE it._TENANT_ID = tp_uc8.tenant_id
           AND (it.ACTIVE = TRUE OR it.ACTIVE IS NULL)
           AND it.EXECUTIONSTATUS = 1
           AND it.MODIFIEDON >= DATEADD(day, -90, CURRENT_DATE())
           AND it.MODIFIEDON < DATEADD(day, 1, CURRENT_DATE())) AS v8
    FROM (SELECT 1) AS one
)
SELECT 'tenant_info' AS source,
    TO_VARCHAR(ti.v1), TO_VARCHAR(ti.v2),
    CAST(NULL AS VARCHAR) AS v3, CAST(NULL AS VARCHAR) AS v4, CAST(NULL AS VARCHAR) AS v5, CAST(NULL AS VARCHAR) AS v6,
    CAST(NULL AS VARCHAR) AS v7, CAST(NULL AS VARCHAR) AS v8, CAST(NULL AS VARCHAR) AS v9, CAST(NULL AS VARCHAR) AS v10,
    CAST(NULL AS VARCHAR) AS v11, CAST(NULL AS VARCHAR) AS v12, CAST(NULL AS VARCHAR) AS v13, CAST(NULL AS VARCHAR) AS v14, CAST(NULL AS VARCHAR) AS v15, CAST(NULL AS VARCHAR) AS v16
FROM tenant_info ti
UNION ALL
SELECT 'purchase_orders_summary' AS source,
    TO_VARCHAR(po.v1), TO_VARCHAR(po.v2), TO_VARCHAR(po.v3), TO_VARCHAR(po.v4), TO_VARCHAR(po.v5), TO_VARCHAR(po.v6), TO_VARCHAR(po.v7), TO_VARCHAR(po.v8), TO_VARCHAR(po.v9), TO_VARCHAR(po.v10), TO_VARCHAR(po.v11), TO_VARCHAR(po.v12), TO_VARCHAR(po.v13), TO_VARCHAR(po.v14), TO_VARCHAR(po.v15), TO_VARCHAR(po.v16)
FROM po_row po
UNION ALL
SELECT 'invoice_materials' AS source,
    TO_VARCHAR(inv.v1), TO_VARCHAR(inv.v2), TO_VARCHAR(inv.v3), TO_VARCHAR(inv.v4), TO_VARCHAR(inv.v5), TO_VARCHAR(inv.v6),
    TO_VARCHAR(inv.v7), TO_VARCHAR(inv.v8), TO_VARCHAR(inv.v9), TO_VARCHAR(inv.v10),
    CAST(NULL AS VARCHAR) AS v11, CAST(NULL AS VARCHAR) AS v12,
    CAST(NULL AS VARCHAR) AS v13, CAST(NULL AS VARCHAR) AS v14, CAST(NULL AS VARCHAR) AS v15, CAST(NULL AS VARCHAR) AS v16
FROM inv
UNION ALL
SELECT 'replenishment_summary' AS source,
    TO_VARCHAR(repl.v1), TO_VARCHAR(repl.v2), TO_VARCHAR(repl.v3),
    CAST(NULL AS VARCHAR) AS v4, CAST(NULL AS VARCHAR) AS v5, CAST(NULL AS VARCHAR) AS v6,
    CAST(NULL AS VARCHAR) AS v7, CAST(NULL AS VARCHAR) AS v8, CAST(NULL AS VARCHAR) AS v9, CAST(NULL AS VARCHAR) AS v10,
    CAST(NULL AS VARCHAR) AS v11, CAST(NULL AS VARCHAR) AS v12, CAST(NULL AS VARCHAR) AS v13, CAST(NULL AS VARCHAR) AS v14, CAST(NULL AS VARCHAR) AS v15, CAST(NULL AS VARCHAR) AS v16
FROM repl_row repl
UNION ALL
SELECT 'returns_summary' AS source,
    TO_VARCHAR(ret.v1), TO_VARCHAR(ret.v2), TO_VARCHAR(ret.v3), TO_VARCHAR(ret.v4),
    TO_VARCHAR(ret.v5), TO_VARCHAR(ret.v6), TO_VARCHAR(ret.v7), TO_VARCHAR(ret.v8), TO_VARCHAR(ret.v9),
    CAST(NULL AS VARCHAR) AS v10, CAST(NULL AS VARCHAR) AS v11, CAST(NULL AS VARCHAR) AS v12, CAST(NULL AS VARCHAR) AS v13,
    CAST(NULL AS VARCHAR) AS v14, CAST(NULL AS VARCHAR) AS v15, CAST(NULL AS VARCHAR) AS v16
FROM ret_row ret
UNION ALL
SELECT 'assessment_data' AS source,
    TO_VARCHAR(a.v1), TO_VARCHAR(a.v2), TO_VARCHAR(a.v3), TO_VARCHAR(a.v4), TO_VARCHAR(a.v5), TO_VARCHAR(a.v6), TO_VARCHAR(a.v7),
    TO_VARCHAR(a.v8), TO_VARCHAR(a.v9), TO_VARCHAR(a.v10), TO_VARCHAR(a.v11), TO_VARCHAR(a.v12), TO_VARCHAR(a.v13), TO_VARCHAR(a.v14), TO_VARCHAR(a.v15), TO_VARCHAR(a.v16)
FROM assess a
UNION ALL
SELECT 'inventory_settings' AS source,
    TO_VARCHAR(s.v1),
    CAST(NULL AS VARCHAR) AS v2, CAST(NULL AS VARCHAR) AS v3, CAST(NULL AS VARCHAR) AS v4, CAST(NULL AS VARCHAR) AS v5,
    CAST(NULL AS VARCHAR) AS v6, CAST(NULL AS VARCHAR) AS v7, CAST(NULL AS VARCHAR) AS v8, CAST(NULL AS VARCHAR) AS v9,
    CAST(NULL AS VARCHAR) AS v10, CAST(NULL AS VARCHAR) AS v11, CAST(NULL AS VARCHAR) AS v12, CAST(NULL AS VARCHAR) AS v13,
    CAST(NULL AS VARCHAR) AS v14, CAST(NULL AS VARCHAR) AS v15, CAST(NULL AS VARCHAR) AS v16
FROM inv_settings s
UNION ALL
SELECT 'setup_data' AS source,
    TO_VARCHAR(sd.v1), TO_VARCHAR(sd.v2), TO_VARCHAR(sd.v3), TO_VARCHAR(sd.v4), TO_VARCHAR(sd.v5),
    CAST(NULL AS VARCHAR) AS v6, CAST(NULL AS VARCHAR) AS v7, CAST(NULL AS VARCHAR) AS v8, CAST(NULL AS VARCHAR) AS v9,
    CAST(NULL AS VARCHAR) AS v10, CAST(NULL AS VARCHAR) AS v11, CAST(NULL AS VARCHAR) AS v12, CAST(NULL AS VARCHAR) AS v13,
    CAST(NULL AS VARCHAR) AS v14, CAST(NULL AS VARCHAR) AS v15, CAST(NULL AS VARCHAR) AS v16
FROM setup_data sd
UNION ALL
SELECT 'usage_checks' AS source,
    TO_VARCHAR(uc.v1), TO_VARCHAR(uc.v2), TO_VARCHAR(uc.v3), TO_VARCHAR(uc.v4), TO_VARCHAR(uc.v5), TO_VARCHAR(uc.v6), TO_VARCHAR(uc.v7), TO_VARCHAR(uc.v8),
    CAST(NULL AS VARCHAR) AS v9, CAST(NULL AS VARCHAR) AS v10,
    CAST(NULL AS VARCHAR) AS v11, CAST(NULL AS VARCHAR) AS v12, CAST(NULL AS VARCHAR) AS v13, CAST(NULL AS VARCHAR) AS v14, CAST(NULL AS VARCHAR) AS v15, CAST(NULL AS VARCHAR) AS v16
FROM usage_checks uc;
