/* Inventory scorecard lookup — loads aggregate JSON and shows full tenant scorecard */
(function () {
  'use strict';
  var path = window.location.pathname;
  var base = path.endsWith('/') ? path : (path.lastIndexOf('/') >= 0 && path.substring(path.lastIndexOf('/') + 1).indexOf('.') >= 0 ? path.substring(0, path.lastIndexOf('/') + 1) : path + '/');
  var aggregateUrl = base + 'data/audit_aggregate.json';
  var cache = null;

  var AREA_ORDER = ['Pricebook & setup', 'Purchasing', 'Invoicing', 'Technician usage', 'Replenishment', 'Returns', 'Transfers', 'Counts and adjustments', 'Other'];
  var STATUS_TO_LABEL = { 'Green': 'Good', 'Yellow': 'On track', 'Review': 'Review', 'Red': 'Critical' };
  var FG_LABELS = { 'item_requisitions': 'Item requisitions', 'requisition_closeout': 'Requisition closeout', 'install_requisitions': 'Enable Requisition Workflow for Service Job', 'transfers_to_jobs': 'Transfers to jobs', 'consignment': 'Consignment', 'purchase_approval_workflow': 'Purchase approval workflow', 'granular_wac': 'Granular WAC', 'stock_optimizer': 'Stock Optimizer' };
  var INV_SETTING_LABELS = { 'BeginningDate': 'Inventory tracking start date', 'AllowCopyingPoItemsToInvoice': 'Automatically add PO Items to Invoice', 'AllowNegativeQuantityOnHand': 'Allow negative quantity on hand', 'AllowNegativeQuantityOnInvoice': 'Allow negative quantity on invoice', 'AutoApplyTagsToJobsBasedOnPoStatus': 'AutoApplyTagsToJobsBasedOnPoStatus', 'AutoApplyTagsToJobsBasedOnTransferStatus': 'AutoApplyTagsToJobsBasedOnTransferStatus', 'AutoAssignTruckToJobTransfers': 'AutoAssignTruckToJobTransfers', 'DontAutomaticallyCreateBills': "Don't automatically create bills", 'InventoryValuationMethod': 'Inventory valuation method', 'IsBinTrackingEnabled': 'Bin tracking enabled', 'IsConsignmentInventoryTrackingEnabled': 'Consignment inventory tracking enabled', 'IsInventoryMobileAppEnabled': 'Inventory mobile app enabled', 'OnlyReplenishMax': 'Only replenish max', 'PoItemCostCopyOption': 'PO item cost copy option', 'PurchaseOrderApprovalField': 'Purchase order approval field', 'RequisitionDateNeededByType': 'Requisition date needed by', 'IsSerializedTrackingEnabled': 'Serialized tracking enabled' };
  var VALUATION_NAMES = { 0: 'Standard costing', 1: 'Weighted average', 2: 'Weighted average (granular)' };
  var PO_APPROVAL_NAMES = { 0: 'Purchase order total', 1: 'Purchase order subtotal' };
  var PO_COPY_NAMES = { 0: 'Add items at $0', 1: 'Add items at receipt cost' };

  function esc(s) {
    return (s === null || s === undefined) ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function slugify(s) {
    return (s || '').toLowerCase().trim().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').slice(0, 80);
  }
  function findTenant(data, query) {
    var q = (query || '').trim();
    if (!q) return null;
    var byId = data.tenants_by_id || {};
    var bySlug = data.tenants_by_slug || {};
    if (/^\d+$/.test(q)) return byId[q] || null;
    return byId[bySlug[slugify(q)]] || null;
  }
  function statusSuffix(s) {
    if (!s) return 'green';
    var v = (s + '').toLowerCase();
    if (v === 'good' || v === 'green') return 'green';
    if (v === 'on track' || v === 'yellow') return 'yellow';
    if (v === 'review') return 'review';
    if (v === 'critical' || v === 'red' || v === 'needs attention') return 'red';
    return 'green';
  }

  function formatSettings(results) {
    var lines = [];
    var cfg = results.readiness_config || {};
    lines.push('<p><strong>Purchasing module:</strong> ' + (cfg.purchasing_module_on ? 'On' : (cfg.purchasing_module_on === false ? 'Off' : '—')) + '</p>');
    lines.push('<p><strong>Inventory module:</strong> ' + (cfg.inventory_module_on ? 'On' : (cfg.inventory_module_on === false ? 'Off' : '—')) + '</p>');
    var fg = results.feature_gates || {};
    Object.keys(FG_LABELS).forEach(function (k) {
      if (fg[k] !== undefined) lines.push('<p><strong>' + esc(FG_LABELS[k]) + ':</strong> ' + (fg[k] ? 'On' : 'Off') + '</p>');
    });
    var start = results.inventory_tracking_start_date;
    if (start) lines.push('<p><strong>Inventory tracking start date:</strong> ' + esc(String(start).substring(0, 10)) + '</p>');
    var inv = results.inventory_settings;
    if (inv && typeof inv === 'object') {
      ['AllowCopyingPoItemsToInvoice', 'AllowNegativeQuantityOnHand', 'AllowNegativeQuantityOnInvoice', 'DontAutomaticallyCreateBills', 'AutoApplyTagsToJobsBasedOnPoStatus', 'AutoApplyTagsToJobsBasedOnTransferStatus', 'AutoAssignTruckToJobTransfers', 'IsInventoryMobileAppEnabled', 'IsSerializedTrackingEnabled', 'OnlyReplenishMax', 'IsBinTrackingEnabled', 'IsConsignmentInventoryTrackingEnabled', 'InventoryValuationMethod', 'PoItemCostCopyOption', 'PurchaseOrderApprovalField'].forEach(function (k) {
        if (inv[k] === undefined) return;
        var label = INV_SETTING_LABELS[k] || k;
        var val = inv[k];
        if (typeof val === 'boolean') val = val ? 'Yes' : 'No';
        else if (k === 'InventoryValuationMethod') val = VALUATION_NAMES[val] != null ? VALUATION_NAMES[val] : val;
        else if (k === 'PurchaseOrderApprovalField') val = PO_APPROVAL_NAMES[val] != null ? PO_APPROVAL_NAMES[val] : val;
        else if (k === 'PoItemCostCopyOption') val = PO_COPY_NAMES[val] != null ? PO_COPY_NAMES[val] : val;
        lines.push('<p><strong>' + esc(label) + ':</strong> ' + esc(val) + '</p>');
      });
    }
    return lines.join('\n');
  }

  function formatSetup(results) {
    var lines = [];
    var isinv = results.isinventory_counts || {};
    var uom = results.materials_with_unit_of_measure;
    var ser = results.equipment_serialized_count;
    lines.push('<p><strong>Materials:</strong> total ' + (isinv.active_materials_count != null ? isinv.active_materials_count : '—') + '; with IsInventory: ' + (isinv.materials_isinventory_count != null ? isinv.materials_isinventory_count : '—') + '; with unit of measure: ' + (uom != null ? uom : '—') + '.</p>');
    lines.push('<p><strong>Equipment:</strong> total ' + (isinv.active_equipment_count != null ? isinv.active_equipment_count : '—') + '; with IsInventory: ' + (isinv.equipment_isinventory_count != null ? isinv.equipment_isinventory_count : '—') + '; serialized: ' + (ser != null ? ser : '—') + '.</p>');
    var setup = results.setup_data || {};
    var truckTotal = setup.truck_total != null ? setup.truck_total : 0;
    var truckTpl = setup.truck_with_template != null ? setup.truck_with_template : 0;
    var whTotal = setup.warehouse_total != null ? setup.warehouse_total : 0;
    var whTpl = setup.warehouse_with_template != null ? setup.warehouse_with_template : 0;
    var under = setup.templates_under_20_active_items != null ? setup.templates_under_20_active_items : 0;
    var truckOk = truckTotal === 0 || (truckTpl / truckTotal >= 0.8);
    var whOk = whTotal === 0 || whTpl >= 1;
    lines.push('<p><strong>Trucks:</strong> ' + truckTotal + ' total, ' + truckTpl + ' with inventory template (min 80% expected) — ' + (truckOk ? 'OK.' : 'Needs attention.') + '</p>');
    lines.push('<p><strong>Warehouses:</strong> ' + whTotal + ' total, ' + whTpl + ' with template — ' + (whOk ? 'OK.' : 'Needs attention.') + '</p>');
    lines.push('<p><strong>Templates with &lt; 20 active items:</strong> ' + under + ' — ' + (under === 0 ? 'OK.' : 'Needs attention.') + '</p>');
    return lines.join('\n');
  }

  function runLookup() {
    var input = document.getElementById('tenant-input');
    var errEl = document.getElementById('lookup-error');
    var container = document.getElementById('scorecard-container');
    if (!input || !errEl || !container) {
      if (errEl) errEl.textContent = 'Page setup error.';
      return;
    }
    errEl.textContent = '';
    errEl.style.color = '';
    container.hidden = true;
    var query = input.value.trim();
    if (!query) {
      errEl.textContent = 'Enter a tenant name or ID.';
      errEl.style.color = '#c00';
      return;
    }
    errEl.textContent = 'Loading…';
    errEl.style.color = '#666';

    function showError(msg) {
      errEl.textContent = msg;
      errEl.style.color = '#c00';
      container.hidden = true;
    }
    function render(tenant) {
      var areas = tenant.area_statuses || {};
      var plan = tenant.action_plan || [];
      var findingsByArea = tenant.findings_by_area || {};
      var results = tenant.results || {};
      var lookback = tenant.lookback_days || 90;
      var name = tenant.tenant_name || ('Tenant ' + tenant.tenant_id);
      var hasRed = Object.keys(areas).some(function (a) { var s = (areas[a] || '').toLowerCase(); return s === 'red' || s === 'critical'; });
      var ok = !hasRed;

      var html = '<div class="page">';
      html += '<header class="header"><h1>Inventory Setup &amp; Usage Scorecard</h1>';
      html += '<p class="meta"><span>' + esc(name) + '</span><span>Last ' + lookback + ' days</span><span>Tenant ID: ' + tenant.tenant_id + '</span></p></header>';

      html += '<div class="card scorecard"><h2 class="card-title">Scorecard by area</h2><div class="scorecard-grid">';
      AREA_ORDER.forEach(function (area) {
        var status = areas[area];
        if (status === 'N/A') return;
        var suf = statusSuffix(status);
        var label = STATUS_TO_LABEL[status] || status;
        html += '<div class="scorecard-item status-' + suf + '"><span class="area-name">' + esc(area) + '</span><span class="badge badge-' + suf + '">' + esc(label) + '</span></div>';
      });
      html += '</div><p class="overall ' + (ok ? 'ok' : 'not-ok') + '">' + (ok ? 'No critical issues.' : 'Address red areas to improve setup and usage.') + '</p></div>';

      html += '<section class="card block"><h2 class="card-title">Settings</h2>' + formatSettings(results) + '</section>';
      html += '<section class="card block"><h2 class="card-title">Setup summary</h2>' + formatSetup(results) + '</section>';

      html += '<section class="card block"><h2 class="card-title">Findings by area</h2>';
      AREA_ORDER.forEach(function (area) {
        var status = areas[area];
        if (status === 'N/A') return;
        var suf = statusSuffix(status);
        var label = STATUS_TO_LABEL[status] || status;
        var findings = findingsByArea[area] || { green: [], yellow: [], review: [], red: [] };
        var list = (findings.green || []).map(function (t) { return '<li class="finding-ok">' + esc(t) + '</li>'; }).join('') +
          (findings.yellow || []).map(function (t) { return '<li class="finding-warn">' + esc(t) + '</li>'; }).join('') +
          (findings.review || []).map(function (t) { return '<li class="finding-review">' + esc(t) + '</li>'; }).join('') +
          (findings.red || []).map(function (t) { return '<li class="finding-err">' + esc(t) + '</li>'; }).join('');
        if (!list) return;
        html += '<section class="findings-area border-' + suf + '"><h3 class="area-head">' + esc(area) + ' <span class="badge badge-' + suf + '">' + esc(label) + '</span></h3><ul class="findings-list">' + list + '</ul></section>';
      });
      html += '</section>';

      html += '<section class="card block action-plan"><h2 class="card-title">Recommended actions</h2>';
      if (plan.length) {
        html += '<ol class="action-plan-list">';
        plan.forEach(function (item) {
          var text = typeof item === 'string' ? item : (item && item.action) || String(item);
          html += '<li>' + esc(text) + '</li>';
        });
        html += '</ol>';
      } else {
        html += '<p>No specific actions recommended; keep up current practices.</p>';
      }
      html += '</section></div>';

      container.innerHTML = html;
      container.hidden = false;
      errEl.textContent = '';
    }
    function run(data) {
      var tenant = findTenant(data, query);
      if (!tenant) {
        showError('No tenant found for "' + query + '". Try another name or ID.');
        return;
      }
      try { render(tenant); } catch (e) { showError('Error: ' + (e.message || e)); }
    }

    if (cache) {
      run(cache);
      return;
    }
    fetch(aggregateUrl)
      .then(function (r) {
        if (!r.ok) throw new Error('Data returned ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data || (!data.tenants_by_id && !data.tenants)) throw new Error('Invalid data format.');
        cache = data;
        run(data);
      })
      .catch(function (err) {
        showError(err.message || 'Could not load data.');
      });
  }

  window.runLookup = runLookup;
  var inputEl = document.getElementById('tenant-input');
  if (inputEl) inputEl.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); runLookup(); } });
})();
