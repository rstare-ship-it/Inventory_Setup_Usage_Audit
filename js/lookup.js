/* Inventory scorecard lookup — loads aggregate JSON and shows tenant scorecard */
(function () {
  'use strict';
  var path = window.location.pathname;
  var base = path.endsWith('/') ? path : (path.lastIndexOf('/') >= 0 && path.substring(path.lastIndexOf('/') + 1).indexOf('.') >= 0 ? path.substring(0, path.lastIndexOf('/') + 1) : path + '/');
  var aggregateUrl = base + 'data/audit_aggregate.json';
  var cache = null;

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
  function statusClass(s) {
    if (!s) return '';
    var v = (s + '').toLowerCase();
    if (v === 'good' || v === 'green') return 'green';
    if (v === 'on track' || v === 'yellow') return 'yellow';
    if (v === 'review') return 'review';
    if (v === 'critical' || v === 'red' || v === 'needs attention') return 'red';
    return '';
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
      var isLive = tenant.is_live ? 'Live' : 'Purchasing only';
      var html = '<h2>' + (tenant.tenant_name || 'Tenant') + ' <span style="font-size:0.6em;color:#666;">(ID ' + tenant.tenant_id + ' · ' + isLive + ' · ' + (tenant.lookback_days || 90) + 'd lookback)</span></h2>';
      html += '<h3>Scorecard</h3><div class="area-rows">';
      Object.keys(areas).forEach(function (area) {
        var status = areas[area];
        if (status === 'N/A') return;
        html += '<div class="area-row"><span class="area-status ' + statusClass(status) + '">' + status + '</span> ' + area + '</div>';
      });
      html += '</div>';
      if (plan.length) {
        html += '<h3>Action plan</h3><ul class="action-plan">';
        plan.forEach(function (item) {
          var text = typeof item === 'string' ? item : (item && item.action) || String(item);
          html += '<li>' + text.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</li>';
        });
        html += '</ul>';
      }
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
  var input = document.getElementById('tenant-input');
  if (input) input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); runLookup(); } });
})();
