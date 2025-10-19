// static/js/vyroba/vyroba.js
(function () {
  'use strict';

  // ----------------------------
  // Utilitky
  // ----------------------------
  const $  = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const cssEscape = (window.CSS && window.CSS.escape) ? window.CSS.escape :
    (str) => String(str).replace(/[^a-zA-Z0-9_\-]/g, '_');

  function todayISO() {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
  }
  function nowForDoc() {
    const d = new Date();
    const pad = (x, n=2) => String(x).padStart(n, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }
  function makeDocNumber(prefix='ODP') {
    const d = new Date();
    const seq = Math.floor(Math.random()*900 + 100);
    return `${prefix}-${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}-${d.getHours()}${String(d.getMinutes()).padStart(2,'0')}${String(d.getSeconds()).padStart(2,'0')}-${seq}`;
  }
  function setStatus(msg, type = '') {
    const s = $('#status-bar');
    if (!s) return;
    s.className = 'status' + (type ? ' ' + type : '');
    s.textContent = msg || '';
  }
  function csrfToken() {
    const m = document.querySelector('meta[name="csrf-token"]');
    if (m) return m.getAttribute('content');
    const c = document.cookie.match(/(?:^|;)\s*csrf_token=([^;]+)/);
    return c ? decodeURIComponent(c[1]) : null;
  }
  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  async function http(url, opt = {}) {
    const headers = {
      'Accept': 'application/json',
      ...(opt.body ? { 'Content-Type': 'application/json' } : {}),
      ...(opt.headers || {})
    };
    const t = csrfToken();
    if (t) { headers['X-CSRFToken'] = t; headers['X-CSRF-Token'] = t; }

    const o = { method: 'GET', credentials: 'same-origin', ...opt, headers };
    if (o.body && typeof o.body !== 'string') o.body = JSON.stringify(o.body);

    const res = await fetch(url, o);
    const isJson = (res.headers.get('content-type') || '').includes('application/json');
    const data = isJson ? await res.json() : await res.text();
    if (!res.ok || (data && typeof data === 'object' && data.error)) {
      const errMsg = (data && data.error) || `HTTP ${res.status}`;
      console.error('HTTP error on', url, '→', errMsg, data);
      throw new Error(errMsg);
    }
    return data;
  }

  async function hit(urls, opt) {
    const arr = Array.isArray(urls) ? urls : [urls];
    let lastErr;
    for (const u of arr) {
      try { return await http(u, opt); }
      catch (e) {
        lastErr = e;
        if (!String(e.message).includes('404')) throw e; // fallback len pri 404
      }
    }
    throw lastErr || new Error('Endpointy zlyhali.');
  }

  // ----------------------------
  // API vrstva (endpoints podľa app.py)
  // ----------------------------
  const VyrobaApi = {
    // Produkty s receptami
    getRecipes()           { return hit(['/api/vyroba/recipes', '/api/vyroba/getMenuData']); },

    // Dashboard
    getPlanned()           { return hit(['/api/vyroba/planned', '/api/vyroba/getMenuData']); },
    getRunning()           { return hit(['/api/vyroba/running', '/api/vyroba/getMenuData']); },
    getRunningDetail(id)   { return http('/api/vyroba/running/detail', { method: 'POST', body: { batch_id: +id } }); },

    // Plánovanie / štart
    calcIngredients(vyrobok_id, plannedWeight) {
      return hit('/api/vyroba/calculateIngredients', { method: 'POST', body: { vyrobok_id, plannedWeight:+plannedWeight } });
    },
    startProduction(payload) {
      return hit(['/api/vyroba/start', '/api/vyroba/startProduction'], { method: 'POST', body: payload });
    },
    finishProduction(payload) { return hit('/api/vyroba/finish', { method: 'POST', body: payload }); },

    // Sklad
    getWarehouse()         { return hit(['/api/sklad/getWarehouse', '/api/vyroba/getWarehouseState']); },
    getWriteoffItems()     { return hit('/api/sklad/items'); },
  writeoff(itemName, quantity, note, workerName) {
  const token = csrfToken();  // pre istotu pošleme aj v tele
  return hit(['/api/sklad/writeoff', '/api/vyroba/manualWriteOff'], {
    method: 'POST',
    body: {
      itemName,
      quantity: +quantity,
      note: note || '',
      workerName: workerName || '',
      csrf_token: token || ''
    }
  });
},


    // Inventúra (výrobný sklad – pod-sklady)
    getInventoryGroups(groupName) {
      const q = groupName ? `?group=${encodeURIComponent(groupName)}` : '';
      return http(`/api/vyroba/inventory/groups${q}`);
    },
    submitInventoryCategory(groupName, items, workerName) {
      return http('/api/vyroba/inventory/submitCategory', { method: 'POST', body: { group_name:groupName, items, worker_name:workerName||'' } });
    },
    completeInventoryAll(workerName, items) {
  return http('/api/vyroba/inventory/complete', {
    method: 'POST',
    body: { worker_name: workerName || '', items }
  });
},

    // legacy fallback (ak máš ešte tlačidlo Uložiť inventúru mimo pod-skladov)
    submitInventoryLegacy(items, note) {
      return hit(['/api/vyroba/inventory/complete', '/api/inventura/update', '/api/vyroba/submitInventory'], {
        method: 'POST', body: { items, note: note || '' }
      });
    },
  };

  // ----------------------------
  // Renderery
  // ----------------------------
  function renderTaskGroups(containerSelector, data, kind) {
    const el = $(containerSelector);
    if (!el) return;

    const isEmpty = !data || (Array.isArray(data) && data.length === 0) ||
                    (typeof data === 'object' && Object.keys(data).length === 0);

    if (isEmpty) { el.innerHTML = '<p class="muted">Žiadne položky.</p>'; return; }

    const groups = (data && data.data) ? data.data : data;

    el.innerHTML = Object.entries(groups).map(([cat, items]) => `
      <div class="task-group">
        <div class="muted" style="font-weight:600;margin-bottom:6px">${esc(cat)}</div>
        ${(items || []).map(it => `
          <div class="task-card ${kind}" ${kind === 'running' ? `data-batch-id="${esc(it.batchId || it.logId || it.id || '')}"` : ''}>
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
              <div>
                <div style="font-weight:700">${esc(it.productName || it.name || '—')}</div>
                ${it.displayQty ? `<div class="muted" style="font-size:12px">${esc(it.displayQty)}</div>` : ''}
              </div>
              ${kind === 'planned'
                ? `<button class="btn btn-primary" data-action="plan-product" data-id="${esc(it.productId || it.id || '')}" data-name="${esc(it.productName || it.name || '')}">Plánovať</button>`
                : ''}
            </div>
          </div>
        `).join('')}
      </div>
    `).join('');

    // plánované → výber výrobku
    $$('#planned-tasks-container [data-action="plan-product"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const pid = +btn.getAttribute('data-id') || null;
        const name = btn.getAttribute('data-name') || '';
        openBatchPlanning(name, pid);
      });
    });

    // prebiehajúce → rozklik detail
    if (kind === 'running') {
      el.querySelectorAll('.task-card.running').forEach(card => {
        const batchId = +(card.getAttribute('data-batch-id') || 0);
        if (!batchId) return;
        card.style.cursor = 'pointer';
        card.addEventListener('click', async () => {
          try { showRunningDetail(await VyrobaApi.getRunningDetail(batchId)); }
          catch (e) { setStatus(e.message || String(e), 'error'); }
        });
      });
    }
  }

  function renderCategories(containerSelector, data) {
    const el = $(containerSelector);
    if (!el) return;

    let cats = {};
    if (Array.isArray(data?.data)) cats = { 'Produkty': data.data };
    else if (data?.data && typeof data.data === 'object') cats = data.data;
    else if (typeof data === 'object') cats = data;

    if (!cats || Object.keys(cats).length === 0) {
      el.innerHTML = '<p class="muted">Žiadne recepty.</p>'; return;
    }

    el.innerHTML = Object.entries(cats).map(([cat, arr]) => `
      <div class="card">
        <div style="font-weight:700;margin-bottom:6px">${esc(cat)}</div>
        <div class="row" style="flex-wrap:wrap;gap:6px">
          ${(arr || []).map(p => `
            <button class="btn" data-action="choose-product" data-id="${esc(p.id)}" data-name="${esc(p.name || p.nazov || '')}">
              ${esc(p.name || p.nazov || '')}
            </button>
          `).join('')}
        </div>
      </div>
    `).join('');

    $$('#category-container [data-action="choose-product"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const pid = +btn.getAttribute('data-id');
        const name = btn.getAttribute('data-name') || '';
        openBatchPlanning(name, pid);
      });
    });
  }

  async function loadCategories() {
    try {
      setStatus('Načítavam výrobky s receptom…');
      const data = await VyrobaApi.getRecipes();
      const cats = (data && data.data) ? data.data
                 : (data && data.recipes) ? data.recipes
                 : (typeof data === 'object' ? data : {});
      const hasAny = Object.keys(cats || {}).some(k => Array.isArray(cats[k]) && cats[k].length);
      if (!hasAny) {
        const el = document.getElementById('category-container');
        if (el) el.innerHTML = `
          <div class="card">
            <div class="muted">Nenašli sa žiadne výrobky s priradeným receptom.</div>
            <div class="muted" style="font-size:12px;margin-top:6px">
              V Kancelárii pridaj recept (ERP → Recepty) alebo priraď existujúci recept k výrobku.
            </div>
          </div>`;
        setStatus('Nie sú dostupné žiadne recepty.', 'error');
        return;
      }
      renderCategories('#category-container', cats);
      setStatus('Vyber výrobok a pokračuj.');
    } catch (e) {
      console.error('loadCategories failed:', e);
      setStatus(e.message || 'Nepodarilo sa načítať produkty s receptom.', 'error');
      const el = document.getElementById('category-container');
      if (el) el.innerHTML = '<p class="muted">Nepodarilo sa načítať produkty.</p>';
    }
  }

  // --- plánovacie view: picker výrobku (ak prídeš z menu)
  async function ensurePlanningProductPicker() {
    const host = document.getElementById('view-batch-planning');
    if (!host) return;

    if (!document.getElementById('planning-product-picker')) {
      const row = document.createElement('div');
      row.id = 'planning-product-picker';
      row.className = 'row';
      row.style.cssText = 'gap:12px; align-items:flex-end; margin-bottom:8px';
      row.innerHTML = `
        <label style="flex:1">Výrobok s receptom
          <select id="planning-product-select" style="width:100%"><option value="">— vyber —</option></select>
        </label>
        <button class="btn" id="planning-product-apply">Vybrať</button>
      `;
      const anchor = document.getElementById('ingredients-check-area') || host.firstChild;
      host.insertBefore(row, anchor);

      document.getElementById('planning-product-apply').addEventListener('click', () => {
        const sel = document.getElementById('planning-product-select');
        const id = +(sel?.value || 0);
        const name = sel?.selectedOptions?.[0]?.text || '';
        if (!id) { setStatus('Vyber výrobok, prosím.', 'error'); return; }
        openBatchPlanning(name, id);
      });
    }

    const sel = document.getElementById('planning-product-select');
    if (sel && sel.options.length <= 1) {
      try {
        const data = await VyrobaApi.getRecipes();
        const cats = (data && data.data) ? data.data : data || {};
        const items = Object.values(cats).flatMap(a => Array.isArray(a) ? a : []);
        sel.innerHTML = '<option value="">— vyber —</option>' + items.map(p =>
          `<option value="${esc(p.id)}">${esc(p.name || p.nazov || '')}</option>`
        ).join('');
      } catch (e) {
        setStatus(e.message || 'Nepodarilo sa načítať výrobky s receptom.', 'error');
      }
    }
  }
function renderWriteoffItems(items) {
  const sel = $('#writeoff-item-select');
  if (!sel) return;
  sel.innerHTML = '<option value="">— vyber —</option>' + (items || []).map(x =>
    `<option value="${esc(x.id)}" data-name="${esc(x.name || x.nazov || '')}">
       ${esc(x.name || x.nazov || '')}
     </option>`
  ).join('');
}


  // ----------------------------
  // Ingrediencie – prepočet
  // ----------------------------
  function renderIngredientsTable(res) {
    const wrap = document.getElementById('ingredients-table');
    if (!wrap) return;

    const rows = (res.ingredients || []).map((r) => {
      const lack = (Number(r.in_stock_kg) + 1e-9) < Number(r.required_kg);
      const required = Number(r.required_kg || 0);
      return `
        <tr class="${lack ? 'loss' : ''}" data-from-id="${esc(r.product_id)}" data-required="${required}">
          <td>
            <div style="font-weight:600">${esc(r.name)}</div>
            <div class="muted" style="margin-top:2px">
              <label style="display:block">Použiť pôvodnú surovinu (kg):
                <input type="number" class="orig-qty" step="0.001" min="0" value="${required.toFixed(3)}" style="max-width:140px">
              </label>
            </div>
            <div class="muted" style="margin-top:4px">
              Náhrada (len pre túto dávku):
              <select class="override-select" style="max-width:260px">
                <option value="">— bez náhrady —</option>
              </select>
              <input type="number" class="override-qty" step="0.001" min="0" value="0.000" style="max-width:120px" title="Koľko kg náhrady použiješ">
            </div>
          </td>
          <td class="num">${Number(r.required_kg).toFixed(3)}</td>
          <td class="num">${Number(r.in_stock_kg).toFixed(3)}</td>
          <td class="num">${Number(r.unit_cost || 0).toFixed(4)}</td>
          <td class="num">${Number(r.total_cost || 0).toFixed(2)}</td>
        </tr>`;
    }).join('');

    wrap.innerHTML = `
      <div class="table-wrap">
        <table class="table" id="ingredients-fixed-table">
          <colgroup>
            <col class="col-name"><col class="col-qty"><col class="col-price"><col class="col-price"><col class="col-value">
          </colgroup>
          <thead>
            <tr>
              <th>Surovina / Náhrada</th>
              <th class="num">Potrebné (kg)</th>
              <th class="num">Sklad (kg)</th>
              <th class="num">Cena/kg</th>
              <th class="num">Spolu €</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>

      <div class="row" style="margin-top:10px;gap:12px;align-items:center">
        <label>Meno pracovníka (ak sa menia množstvá / použije sa náhrada)
          <input id="override-worker" type="text" placeholder="Meno a priezvisko">
        </label>
        <span class="muted">Ak zmeníš množstvá alebo použiješ náhradu, meno je povinné.</span>
      </div>
    `;

    // naplň možnosti náhrad
    (async () => {
      try {
        const items = await VyrobaApi.getWriteoffItems();
        const options = (items || []).map(x => {
          const idVal = x.id || x.product_id || x.produkt_id || '';
          return `<option value="${esc(idVal)}">${esc(x.name || x.nazov || '')}</option>`;
        }).join('');
        document.querySelectorAll('.override-select').forEach(sel => sel.insertAdjacentHTML('beforeend', options));
      } catch(_) {}
    })();
  }

  // ----------------------------
  // Sklad – deduplikovaný výpis
  // ----------------------------
  function renderWarehouse(items) {
    const tbody = document.querySelector('#warehouse-table tbody');
    const table = document.querySelector('#warehouse-table');
    const counter = document.getElementById('warehouse-count');
    if (!tbody || !table) return;

    if (!table.querySelector('colgroup')) {
      table.insertAdjacentHTML('afterbegin', `
        <colgroup>
          <col class="col-name"><col class="col-qty"><col class="col-price"><col class="col-value">
        </colgroup>
      `);
    }

    // normalizácia + dedup
    let arrRaw = [];
    if (Array.isArray(items)) arrRaw = items;
    else if (Array.isArray(items?.all)) arrRaw = items.all;
    else if (Array.isArray(items?.items)) arrRaw = items.items;
    else if (Array.isArray(items?.data)) arrRaw = items.data;
    else if (Array.isArray(items?.warehouse)) arrRaw = items.warehouse;
    else if (items && typeof items === 'object') {
      const keys = Object.keys(items).filter(k => k !== 'all');
      arrRaw = keys.flatMap(k => Array.isArray(items[k]) ? items[k] : []);
    }
    const seen = new Map();
    for (const x of arrRaw) {
      const key = String(x.product_id ?? x.produkt_id ?? x.id ?? x.ean ?? x.produkt ?? x.name ?? Math.random());
      if (!seen.has(key)) seen.set(key, x);
    }
    const arr = Array.from(seen.values());

    const filter = (document.getElementById('warehouse-filter')?.value || '').trim().toLowerCase();
    const rows = arr.map(x => ({
      name: x.name || x.nazov || x.produkt || x.product || '',
      qty:  Number(x.qty ?? x.mnozstvo ?? x.quantity ?? 0),
      avg:  Number(x.avg_price ?? x.priemerna_cena ?? x.unit_cost ?? 0),
    })).filter(r => !filter || r.name.toLowerCase().includes(filter));

    tbody.innerHTML = rows.map(r => `
      <tr>
        <td>${esc(r.name)}</td>
        <td class="num">${r.qty.toFixed(3)}</td>
        <td class="num">${r.avg.toFixed(4)}</td>
        <td class="num">${(r.qty * r.avg).toFixed(2)}</td>
      </tr>
    `).join('') || `<tr><td colspan="4">Žiadne dáta.</td></tr>`;
    if (counter) counter.textContent = `${rows.length} položiek`;
  }

  // ----------------------------
  // Detail prebiehajúcej dávky
  // ----------------------------
  function showRunningDetail(detail) {
    let box = document.getElementById('running-detail-box');
    if (!box) {
      const host = document.getElementById('view-dashboard') || document.body;
      box = document.createElement('div');
      box.id = 'running-detail-box';
      box.className = 'card';
      box.style.marginTop = '12px';
      host.insertBefore(box, host.firstChild);
    }

    const stdRows = (detail.standard_ingredients || []).map(r =>
      `<tr><td>${esc(r.name)}</td><td class="num">${Number(r.required_kg).toFixed(3)}</td></tr>`
    ).join('') || '<tr><td colspan="2">—</td></tr>';

    const usedRows = (detail.used_ingredients || []).map(r =>
      `<tr><td>${esc(r.name)}</td><td class="num">${Number(r.used_kg).toFixed(3)}</td></tr>`
    ).join('') || '<tr><td colspan="2">—</td></tr>';

    const note = detail.override_note ? `<div class="muted" style="margin-top:8px">${esc(detail.override_note)}</div>` : '';

    box.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
        <div>
          <div style="font-weight:700">Dávka #${detail.batch_id} — ${esc(detail.product)}</div>
          <div class="muted">Plán: ${Number(detail.planned_kg||0).toFixed(1)} kg</div>
        </div>
        <button class="btn" id="close-running-detail">Zavrieť</button>
      </div>
      <div class="grid2" style="margin-top:12px">
        <div>
          <h4>Štandardný recept</h4>
          <table class="table">
            <colgroup><col class="col-name"><col class="col-qty"></colgroup>
            <thead><tr><th>Surovina</th><th class="num">Potrebné (kg)</th></tr></thead>
            <tbody>${stdRows}</tbody>
          </table>
        </div>
        <div>
          <h4>Skutočne použité</h4>
          <table class="table">
            <colgroup><col class="col-name"><col class="col-qty"></colgroup>
            <thead><tr><th>Surovina</th><th class="num">Spotreba (kg)</th></tr></thead>
            <tbody>${usedRows}</tbody>
          </table>
        </div>
      </div>
      ${note}
    `;
    $('#close-running-detail')?.addEventListener('click', () => box.remove());
  }

  // ----------------------------
  // Plánovanie / štart výroby
  // ----------------------------
  let currentProduct = { id: null, name: null };

  async function recalcIngredients() {
    const pid = currentProduct.id;
    const w = +($('#planned-weight')?.value || 0);
    if (!pid || w <= 0) {
      $('#ingredients-check-area') && ($('#ingredients-check-area').style.display = 'none');
      $('#start-production-btn') && ($('#start-production-btn').disabled = true);
      return;
    }
    setStatus('Kontrolujem suroviny…');
    try {
      const res = await VyrobaApi.calcIngredients(pid, w);
      renderIngredientsTable(res);
      $('#ingredients-check-area').style.display = 'block';
      $('#start-production-btn').disabled = false;
      const missing = Array.isArray(res.missing) && res.missing.length > 0;
      setStatus(missing ? 'Upozornenie: chýbajú suroviny – spustením pôjde sklad do mínusu.' : 'Všetko pripravené na štart výroby.', missing ? 'error' : '');
    } catch (e) {
      console.error('calculateIngredients failed:', e);
      $('#ingredients-check-area') && ($('#ingredients-check-area').style.display = 'none');
      $('#start-production-btn') && ($('#start-production-btn').disabled = true);
      setStatus(e.message || String(e), 'error');
    }
  }

  function openBatchPlanning(name, id = null) {
    currentProduct = { id, name: name || 'Výrobok' };
    $('#batch-planning-title') && ($('#batch-planning-title').textContent = `Plánovanie — ${name || 'výrobok'}`);
    switchView('view-batch-planning');
    ensurePlanningProductPicker();

    const w = $('#planned-weight');
    const d = $('#production-date');
    if (w && !w.value) w.value = 100;
    if (d && !d.value) d.value = todayISO();

    if (!id) {
      $('#ingredients-check-area') && ($('#ingredients-check-area').style.display = 'none');
      $('#start-production-btn') && ($('#start-production-btn').disabled = true);
      setStatus('Vyber výrobok z rozbaľovačky hore a zadaj množstvo (kg).', 'error');
      return;
    }

    $('#planned-weight') && ($('#planned-weight').oninput = recalcIngredients);
    recalcIngredients();
  }

  async function startProductionFlow() {
  const w = +(document.getElementById('planned-weight')?.value || 0);
  const d = document.getElementById('production-date')?.value || null;

  if (!currentProduct.id) {
    setStatus('Vyber najprv výrobok (Spustiť výrobu → klik na produkt alebo vyber v Dávka).', 'error');
    const cat = document.getElementById('category-container');
    if (cat) cat.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  if (w <= 0) {
    setStatus('Zadaj plánované množstvo (kg) > 0.', 'error');
    return;
  }

  // Zber úprav: POZOR – pridáme len to, čo sa skutočne zmenilo
  const overrides = [];
  (document.querySelectorAll('#ingredients-fixed-table tbody tr') || []).forEach(tr => {
    const fromId   = +tr.getAttribute('data-from-id');
    const required = +tr.getAttribute('data-required') || 0;
    const origInp  = tr.querySelector('.orig-qty');
    const sel      = tr.querySelector('.override-select');
    const altInp   = tr.querySelector('.override-qty');

    const useOrig = origInp ? +origInp.value : required;
    const toId    = sel && sel.value ? +sel.value : 0;
    const toQty   = altInp ? +altInp.value : 0;

    const changed = (Math.abs(useOrig - required) > 1e-9) || (toId > 0 && toQty > 0);
    if (changed) {
      overrides.push({
        from_id: fromId,
        use_original_qty_kg: isFinite(useOrig) ? useOrig : required,
        to_id: toId > 0 ? toId : null,
        to_qty_kg: toId > 0 ? (isFinite(toQty) ? toQty : 0) : 0
      });
    }
  });

  // Autor zmeny: povinný IBA ak existuje aspoň 1 override
  let payload = {
    vyrobok_id: currentProduct.id,
    productName: currentProduct.name,
    plannedWeight: w,
    productionDate: d
  };
  if (overrides.length > 0) {
    const overrideAuthor = (document.getElementById('override-worker')?.value || '').trim();
    if (!overrideAuthor) {
      setStatus('Zadaj meno pracovníka, ktorý upravil množstvá/náhrady.', 'error');
      return;
    }
    payload.overrides = overrides;
    payload.override_author = overrideAuthor;
  }
  // Ak nič nemeníš, overrides vôbec neposielaj → backend nebude vyžadovať autora.

  setStatus('Spúšťam výrobu…');
  try {
    let res = await VyrobaApi.startProduction(payload);
    if (res && res.requires_confirmation) {
      const lines = (res.missing || []).map(m =>
        `• ${m.name}: chýba ${Number(m.shortage_kg || m.shortage || 0).toFixed(3)} kg (sklad ${Number(m.in_stock_kg || m.in_stock || 0).toFixed(3)} / potreba ${Number(m.required_kg || m.required || 0).toFixed(3)})`
      ).join('\n');
      const ok = confirm(`UPOZORNENIE: Chýbajú suroviny a sklad pôjde do mínusu.\n\n${lines}\n\nChceš napriek tomu spustiť výrobu?`);
      if (!ok) return;
      res = await VyrobaApi.startProduction({ ...payload, forceStart: true });
    }

    setStatus(res.message || (res.went_negative ? 'Výroba spustená (časť surovín šla do mínusu).' : 'Výroba spustená.'));
    await Promise.all([ loadDashboard(), loadWarehouse(true) ]);
    document.querySelector('.nav .nav-item[data-view="view-dashboard"]')?.click();
  } catch (e) {
    console.error('startProduction failed:', e);
    const msg = (e && e.message) ? e.message : String(e);
    setStatus(
      (msg.includes('Failed to fetch') || msg.includes('Network')) ? 'Server zrušil spojenie počas spracovania. Pozri log servera.' : msg,
      'error'
    );
  }
}


  // ----------------------------
  // Dashboard, Weekly, Sklad
  // ----------------------------
  async function loadDashboard() {
    const [planned, running] = await Promise.all([
      VyrobaApi.getPlanned().catch(() => ({})),
      VyrobaApi.getRunning().catch(() => ({}))
    ]);
    renderTaskGroups('#planned-tasks-container', planned, 'planned');
    renderTaskGroups('#running-tasks-container', running, 'running');
  }
  async function loadWeeklyNeeds() {
    try {
      const data = await http('/api/vyroba/weeklyNeeds'); // server môže vracať prázdne items
      const box = document.getElementById('weekly-needs-box'); if (!box) return;
      const rows = (data.items || data || []).map(it => {
        const ok = Number(it.stock_kg || 0) >= Number(it.needed_kg || 0);
        const mark = ok ? '🟢' : '🔴';
        return `<tr class="${ok ? '' : 'loss'}">
          <td>${mark} ${esc(it.name)}</td>
          <td class="num">${Number(it.needed_kg||0).toFixed(1)}</td>
          <td class="num">${Number(it.stock_kg||0).toFixed(1)}</td>
        </tr>`;
      }).join('') || `<tr><td colspan="3">Žiadne dáta</td></tr>`;
      box.innerHTML = `
        <table class="table">
          <colgroup><col class="col-name"><col class="col-qty"><col class="col-qty"></colgroup>
          <thead><tr><th>Surovina</th><th class="num">Potrebné (kg)</th><th class="num">Sklad (kg)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>`;
    } catch(_) {}
  }
  async function loadWeeklyPlan() {
    try {
      const data = await http('/api/vyroba/weeklyPlan');
      const box = document.getElementById('weekly-plan-box'); if (!box) return;
      const items = (data.items || data || []).map(it =>
        `<li>${esc(it.date || '')}: ${esc(it.product || it.name || '')} – ${Number(it.qty || 0).toFixed(1)} kg</li>`
      ).join('') || '<li>Žiadne dáta</li>';
      box.innerHTML = `<ul class="muted">${items}</ul>`;
    } catch(_) {}
  }

  let _warehouseCache = null;
  async function loadWarehouse(force = false) {
    try {
      if (!_warehouseCache || force) {
        _warehouseCache = await VyrobaApi.getWarehouse();
      }
      renderWarehouse(_warehouseCache);
    } catch (e) {
      setStatus(e.message || String(e), 'error');
    }
  }
  async function preloadWriteoffItems() {
    try {
      renderWriteoffItems(await VyrobaApi.getWriteoffItems());
    } catch(_) {}
  }

  // ----------------------------
  // Inventúra – pod-sklady výrobného skladu
  // ----------------------------
  function ensureInventoryUi() {
    const view = document.getElementById('view-inventory');
    if (!view) return;

    if (!document.getElementById('inv-toolbar')) {
      const row = document.createElement('div');
      row.id = 'inv-toolbar';
      row.className = 'row';
      row.style.cssText = 'justify-content:space-between; align-items:center; margin-bottom:8px';
      row.innerHTML = `
        <div class="muted">Inventúra – výrobný sklad (pod-sklady)</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap">
          <button class="btn inv-tab" data-group="Mäso">Mäso</button>
          <button class="btn inv-tab" data-group="Koreniny">Koreniny</button>
          <button class="btn inv-tab" data-group="Obaly">Obaly</button>
          <button class="btn inv-tab" data-group="Pomocný materiál">Pomocný materiál</button>
          <button class="btn inv-tab" data-group="Ostatné">Ostatné</button>
          <input id="inv-worker" type="text" placeholder="Meno pracovníka" style="max-width:220px;margin-left:8px">
        </div>
      `;
      view.insertBefore(row, view.firstChild);

      row.querySelectorAll('.inv-tab').forEach(btn => {
        btn.addEventListener('click', () => {
          row.querySelectorAll('.inv-tab').forEach(x => x.classList.remove('active'));
          btn.classList.add('active');
          loadInventoryGroup(btn.getAttribute('data-group'));
        });
      });
    }

    if (!document.getElementById('inv-groups-wrap')) {
      const wrap = document.createElement('div');
      wrap.id = 'inv-groups-wrap';
      view.appendChild(wrap);
    }
  }

  function loadInventoryGroup(groupName) {
    return VyrobaApi.getInventoryGroups(groupName)
      .then((data) => {
        const groups = data.groups || {};
        renderInventoryGroup(groupName, groups[groupName] || []);
      })
      .catch((e) => setStatus(e.message || String(e), 'error'));
  }
function renderInventoryGroup(groupName, items) {
  const host = document.getElementById('inv-groups-wrap');
  if (!host) return;

  // poskladaj riadky tabuľky bezpečne (žiadne zalomené backticky)
  const rows = (items || []).map(it => {
    return (
      '<tr data-name="' + esc(it.name) + '" data-group="' + esc(groupName) + '">' +
        '<td>' + esc(it.name) + '</td>' +
        '<td class="num">' + Number(it.systemQty || 0).toFixed(3) + '</td>' +
        '<td class="num"><input type="number" step="0.001" min="0" class="inv-real-input" style="max-width:120px"></td>' +
      '</tr>'
    );
  }).join('') || '<tr><td colspan="3">Žiadne položky</td></tr>';

  // poskladaj celý card HTML bez vnorených backtickov
  var html =
    '<div class="card" style="margin-bottom:10px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;">' +
        '<h3 style="margin:0">' + esc(groupName) + '</h3>' +
        '<button class="btn" id="inv-save-group">Uložiť ' + esc(groupName) + '</button>' +
      '</div>' +
      '<div class="table-wrap" style="margin-top:8px">' +
        '<table class="table">' +
          '<colgroup><col class="col-name"><col class="col-qty"><col class="col-qty"></colgroup>' +
          '<thead><tr><th>Položka</th><th class="num">Systém (kg)</th><th class="num">Reálne (kg)</th></tr></thead>' +
          '<tbody>' + rows + '</tbody>' +
        '</table>' +
      '</div>' +
    '</div>';

  host.innerHTML = html;

  // handler uloženia skupiny
  var btn = document.getElementById('inv-save-group');
  if (btn) {
    btn.addEventListener('click', async function () {
      const worker = (document.getElementById('inv-worker')?.value || '').trim();
      const trs = host.querySelectorAll('tr[data-group="' + cssEscape(groupName) + '"]');
      const itemsToSave = Array.from(trs).map(function (tr) {
        const name = tr.getAttribute('data-name');
        const real = +tr.querySelector('.inv-real-input')?.value || 0;
        return real > 0 ? { name: name, realQty: real } : null;
      }).filter(Boolean);

      if (itemsToSave.length === 0) {
        setStatus('Žiadne hodnoty pre ' + groupName + '.', 'error');
        return;
      }
      try {
        const res = await VyrobaApi.submitInventoryCategory(groupName, itemsToSave, worker);
        setStatus(res.message || ('Uložené: ' + groupName + '.' ));
        await loadWarehouse(true);
      } catch (e) {
        setStatus(e.message || String(e), 'error');
      }
    });
  }
}


  // ----------------------------
  // Navigácia (sidebar)
  // ----------------------------
  function switchView(viewId) {
    $$('.view').forEach(v => {
      if (v.id === viewId) { v.classList.add('active'); v.style.display = ''; }
      else { v.classList.remove('active'); if (!v.classList.contains('active')) v.style.display = 'none'; }
    });
    $$('.nav .nav-item').forEach(a => a.classList.toggle('active', a.getAttribute('data-view') === viewId));
  }

  function wireSidebar() {
    $$('.nav .nav-item').forEach(a => {
      a.addEventListener('click', async (e) => {
        e.preventDefault();
        const id = a.getAttribute('data-view');
        if (!id) return;

        switchView(id);

        if (id === 'view-warehouse') {
          loadWarehouse(false);
          $('#warehouse-filter') && $('#warehouse-filter').addEventListener('input', () => loadWarehouse(false), { once: true });
        }

        if (id === 'view-start-production-category') {
          try {
            await loadCategories();
            const view = document.getElementById('view-start-production-category');
            if (view) view.scrollIntoView({ behavior: 'smooth', block: 'start' });
          } catch(_) {}
        }

        if (id === 'view-batch-planning') {
          ensurePlanningProductPicker();
          setStatus('Vyber výrobok z rozbaľovačky a zadaj množstvo (kg).');
        }

        if (id === 'view-inventory') {
          ensureInventoryUi();
          const first = document.querySelector('.inv-tab[data-group="Mäso"]') || document.querySelector('.inv-tab');
          if (first) first.click();
        }
      });
    });
  }

  // ----------------------------
  // Vydajka odpisu – generovanie a tlač
  // ----------------------------
  function printWriteoffSlip({ itemName, quantity, note, workerName }) {
    const docNo = makeDocNumber('ODP');
    const ts = nowForDoc();
    const html = `
      <!doctype html><html lang="sk"><head>
        <meta charset="utf-8">
        <title>Vydajka odpisu ${esc(docNo)}</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 24px; font-size: 13px; }
          h1 { font-size: 18px; margin: 0 0 8px; }
          .muted { color: #666; }
          table { border-collapse: collapse; width: 100%; margin-top: 12px; }
          th, td { border: 1px solid #ddd; padding: 6px 8px; }
          th { text-align: left; background: #f7f7f7; }
          .num { text-align: right; }
          .row { display:flex; justify-content:space-between; gap: 12px; margin-top: 8px; }
          .sig { margin-top: 32px; display:flex; gap: 60px; }
          .sig > div { width: 240px; border-top: 1px solid #999; text-align: center; padding-top: 6px; }
          @media print { .no-print { display:none !important; } }
          .small { font-size: 12px; }
        </style>
      </head><body>
        <div class="no-print" style="text-align:right">
          <button onclick="window.print()">Tlačiť</button>
          <button onclick="window.close()">Zavrieť</button>
        </div>
        <h1>Vydajka odpisu</h1>
        <div class="small muted">Číslo: ${esc(docNo)} &nbsp;|&nbsp; Dátum/čas: ${esc(ts)}</div>
        <table>
          <thead><tr><th>Položka</th><th class="num">Množstvo</th><th>Poznámka</th></tr></thead>
          <tbody>
            <tr>
              <td>${esc(itemName)}</td>
              <td class="num">${Number(quantity||0).toFixed(3)}</td>
              <td>${esc(note || '')}</td>
            </tr>
          </tbody>
        </table>
        <div class="row">
          <div>Zadal: <strong>${esc(workerName || '—')}</strong></div>
          <div>Oddelenie: Výroba</div>
        </div>
        <div class="sig">
          <div>Vystavil</div><div>Schválil</div><div>Prevzal</div>
        </div>
      </body></html>
    `;
    const w = window.open('', '_blank', 'noopener,noreferrer,width=900,height=700');
    if (!w) { alert('Povoľťe otváranie popup okien, aby sa dala vytlačiť vydajka.'); return; }
    w.document.open('text/html'); w.document.write(html); w.document.close();
    try { w.focus(); } catch (_) {}
    try { w.print(); } catch (_) {}
  }

  // ----------------------------
  // Public API
  // ----------------------------
  async function submitManualWriteoff() {
  const sel = $('#writeoff-item-select');
  const productId   = +(sel?.value || 0);                                         // value = ID
  const productName = sel?.selectedOptions?.[0]?.getAttribute('data-name') ||     // data-name = názov
                      sel?.selectedOptions?.[0]?.text || '';
  const qty    = +($('#writeoff-quantity')?.value || 0);
  const note   = $('#writeoff-note')?.value || '';
  const worker = ($('#writeoff-worker')?.value || '').trim();

  if ((!productId && !productName) || qty <= 0 || !worker) {
    setStatus('Vyber položku, zadaj množstvo > 0 a meno pracovníka.', 'error');
    return;
  }

  setStatus('Odpísavam…');

  try {
    const token = csrfToken(); // meta/cookie CSRF
    const payload = {
      // Pošleme OBOJE – vyhovieme starému (itemName, quantity, workerName) aj novému (product_id)
      product_id: productId || undefined,
      itemName: productName || undefined,
      quantity: qty,
      note: note || '',
      workerName: worker,
      csrf_token: token || ''
    };

    // pre debug (ak by ešte padalo na 400, uvidíš presne, čo posielame)
    // console.log('WRITE-OFF PAYLOAD', payload);

    const res = await hit(['/api/sklad/writeoff', '/api/vyroba/manualWriteOff'], {
      method: 'POST',
      body: payload
    });

    setStatus(res.message || 'Odpis hotový.');
    $('#writeoff-quantity') && ($('#writeoff-quantity').value = '');
    $('#writeoff-note') && ($('#writeoff-note').value = '');

    // Vydajka – použijeme pekný názov (productName); ak by bol prázdny, zobrazíme ID
    const printedName = productName || `#${productId}`;
    printWriteoffSlip({ itemName: printedName, quantity: qty, note, workerName: worker });

    await loadWarehouse(true);
  } catch (e) {
    const msg = (e && e.message) ? e.message : String(e);
    if (/403/.test(msg) || /CSRF/i.test(msg)) {
      setStatus('CSRF: token chýba/nesedí. Obnov stránku (Ctrl+F5) alebo sa prihlás znova.', 'error');
    } else {
      setStatus(msg, 'error');
    }
  }
}

async function submitInventory() {
  // 1) NOVÝ spôsob – inventúra cez pod-sklady (karty v #inv-groups-wrap)
  const wrap = document.getElementById('inv-groups-wrap');
  if (wrap) {
    const trs = Array.from(wrap.querySelectorAll('tr[data-name][data-group]'));
    const items = trs.map(tr => {
      const name = tr.getAttribute('data-name');
      const type = tr.getAttribute('data-group');              // názov pod-skladu (Mäso/Koreniny/…)
      const inp  = tr.querySelector('.inv-real-input');
      const real = inp ? parseFloat(inp.value || '0') : 0;
      return real > 0 ? { name, realQty: real, type } : null;  // filter nuly
    }).filter(Boolean);

    const worker = (document.getElementById('inv-worker')?.value || '').trim();

    if (!items.length) {
      setStatus('Zadaj aspoň jednu reálnu hodnotu v pod-skladoch (Mäso/Koreniny/Obaly/…).', 'error');
      return;
    }

    try {
      const res = await VyrobaApi.completeInventoryAll(worker, items);
      setStatus(res.message || 'Inventúra dokončená.');
      await loadWarehouse(true);
      return;
    } catch (e) {
      setStatus(e.message || String(e), 'error');
      return;
    }
  }

  // 2) LEGACY fallback – ak máš ešte staré tabuľky mimo pod-skladov
  const container = document.getElementById('inventory-tables-container') || document;
  const rows = Array.from(container.querySelectorAll('tr[data-product-id]'));
  const items = rows.map(r => {
    const pid  = +(r.getAttribute('data-product-id') || 0);
    const inp  = r.querySelector('input.inv-real') || r.querySelector('input[type="number"]');
    const real = inp ? parseFloat(inp.value || '0') : 0;
    return (pid > 0 && isFinite(real) && real > 0) ? { product_id: pid, real_qty: real } : null;
  }).filter(Boolean);

  if (!items.length) {
    setStatus('Inventúra: nenašli sa žiadne vyplnené položky. Použi prosím sekciu pod-skladov.', 'error');
    return;
  }

  try {
    const res = await VyrobaApi.submitInventoryLegacy(items, '');
    setStatus(res.message || 'Inventúra uložená.');
    await loadWarehouse(true);
  } catch (e) {
    setStatus(e.message || String(e), 'error');
  }
}

  // ----------------------------
  // Inicializácia
  // ----------------------------
  async function initialize() {
    try {
      wireSidebar();
      $('#start-production-btn') && $('#start-production-btn').addEventListener('click', startProductionFlow);
      $('#planned-weight') && ($('#planned-weight').addEventListener('input', recalcIngredients));
      $('#production-date') && ($('#production-date').setAttribute('value', todayISO()));
      $('#view-manual-writeoff .btn-danger') && $('#view-manual-writeoff .btn-danger').addEventListener('click', submitManualWriteoff);
      $('#warehouse-filter') && $('#warehouse-filter').addEventListener('input', () => renderWarehouse(_warehouseCache || []));
      switchView('view-dashboard');
      setStatus('Načítavam…');

      await Promise.all([
        loadDashboard(),
        loadCategories().catch(()=>{}),
        loadWarehouse(false),
        preloadWriteoffItems(),
        (async ()=>{ try { await loadWeeklyNeeds(); } catch(_) {} })(),
        (async ()=>{ try { await loadWeeklyPlan(); } catch(_) {} })()
      ]);

      setStatus('Pripravené.');
    } catch (e) {
      setStatus(e.message || String(e), 'error');
    }
  }

  // Expozícia
  window.vyroba = {
    initialize,
    submitManualWriteoff,
    submitInventory,
    openBatchPlanning
  };

})();
