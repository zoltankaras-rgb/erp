// =================================================================
// === LOGIKA ŠPECIFICKÁ PRE MODUL EXPEDÍCIA (EXPEDICIA.JS) ===
// =================================================================

// --- Pomocné utility a fallbacky (aby nič nepadalo, ak common.js nie je načítaný) ---
function getCookie(name){
  return document.cookie.split('; ').reduce((a,c)=>{const [k,v]=c.split('=');return k===name?decodeURIComponent(v):a;},'');
}
const escapeHtml = (window.escapeHtml) ? window.escapeHtml : (s) => {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"'`=\/]/g, ch => ({
    '&':'&nbsp;'.replace('nbsp;','amp;'), '<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','/':'&#x2F;','`':'&#x60;','=':'&#x3D;'
  }[ch]));
};
const safeToFixed = (window.safeToFixed) ? window.safeToFixed : (n, d=3) => {
  const x = Number(n); return Number.isFinite(x) ? x.toFixed(d) : '';
};
if (typeof window.showStatus !== 'function') {
  window.showStatus = (msg, isError=false) => {
    const el = document.getElementById('status-bar') || document.getElementById('login-status');
    if (el){ el.textContent = msg || ''; el.style.color = isError ? '#b91c1c' : '#065f46'; }
  };
}
if (typeof window.clearStatus !== 'function') {
  window.clearStatus = () => { const el = document.getElementById('status-bar'); if (el) el.textContent=''; };
}
if (typeof window.apiRequest !== 'function') {
  window.apiRequest = async (url, options={})=>{
    const xsrf = getCookie('XSRF-TOKEN');
    const headers = Object.assign({'Content-Type':'application/json'}, options.headers||{});
    if (xsrf && !headers['X-CSRF-Token']) headers['X-CSRF-Token'] = xsrf;
    const init = {
      method: options.method || 'GET',
      credentials: 'include',
      headers,
    };
    if (options.body !== undefined) init.body = (headers['Content-Type']==='application/json') ? JSON.stringify(options.body) : options.body;
    const res = await fetch(url, init);
    if (!res.ok) {
      let text = '';
      try { text = await res.text(); } catch(_){}
      const err = new Error(text || res.statusText); err.status = res.status; throw err;
    }
    const ct = res.headers.get('content-type') || '';
    return ct.includes('application/json') ? res.json() : res.text();
  };
}
function forceEnterModule() {
  const lw  = document.getElementById('login-wrapper');
  const app = document.getElementById('expedicia-app');
  if (lw)  { lw.setAttribute('hidden',''); lw.style.display = 'none'; }
  if (app) { app.style.display = 'block'; }
  // istota: ukáž hlavné menu a natiahni dáta
  if (typeof showExpeditionView === 'function') showExpeditionView('view-expedition-menu');
  if (typeof loadAndShowExpeditionMenu === 'function') loadAndShowExpeditionMenu();
}

// --- Globálna premenná pre skener (ak bude dostupný) ---
let html5QrCode = null;

// --- Prepínanie view v rámci modulu expedície ---
function showExpeditionView(viewId) {
  document.querySelectorAll('#expedition-module-container > .view').forEach(v => v.style.display = 'none');
  const view = document.getElementById(viewId);
  if (view) view.style.display = 'block';
  else console.error(`Chyba: Pohľad s ID '${viewId}' nebol nájdený!`);
  clearStatus();
}

// --- Úvodný dashboard expedície ---
async function loadAndShowExpeditionMenu() {
  try {
    const data = await apiRequest('/api/expedicia/getExpeditionData');
    populatePendingSlicing(data.pendingTasks);
    showExpeditionView('view-expedition-menu');
  } catch (e) {
    // 401/403 rieši auth vrstva nižšie – tu neobnovujeme stránku
    console.error("Nepodarilo sa načítať dáta pre menu expedície.", e);
  }
}

function populatePendingSlicing(tasks) {
  const container = document.getElementById('pending-slicing-container');
  const wrapper = document.getElementById('slicing-card') || container;
  if (!tasks || tasks.length === 0) { wrapper.style.display = 'none'; return; }
  wrapper.style.display = 'block';

  let tableHtml = `<table><thead><tr><th>Zdroj</th><th>Cieľ</th><th>Plán (ks)</th><th>Akcia</th></tr></thead><tbody>`;
  tasks.forEach(task => {
    tableHtml += `<tr>
      <td>${escapeHtml(task.bulkProductName)}</td>
      <td>${escapeHtml(task.targetProductName)}</td>
      <td>${escapeHtml(task.plannedPieces)}</td>
      <td><button class="btn btn-primary" style="margin:0; width:auto;" onclick="finalizeSlicing('${task.logId}')">Ukončiť</button></td>
    </tr>`;
  });
  container.innerHTML = tableHtml + '</tbody></table>';
}

// --- Prepojenie s výrobou: dátumy a dávky ---
async function loadProductionDates() {
  try {
    const dates = await apiRequest('/api/expedicia/getProductionDates');
    showExpeditionView('view-expedition-date-selection');
    const container = document.getElementById('expedition-date-container');
    container.innerHTML = dates.length === 0 ? '<p>Žiadne výroby na prevzatie.</p>' : '';
    dates.forEach(date => {
      const btn = document.createElement('button');
      btn.className = 'btn btn-primary';
      btn.textContent = new Date(date + 'T00:00:00').toLocaleDateString('sk-SK');
      btn.onclick = () => loadProductionsByDate(date);
      container.appendChild(btn);
    });
  } catch(e) { /* spracované vyššie */ }
}

async function loadProductionsByDate(date) {
  try {
    showExpeditionView('view-expedition-batch-list');
    document.getElementById('expedition-batch-list-title').textContent =
      `Výroba zo dňa: ${new Date(date + 'T00:00:00').toLocaleDateString('sk-SK')}`;

    const productions = await apiRequest('/api/expedicia/getProductionsByDate', { method: 'POST', body: {date} });
    const container = document.getElementById('expedition-batch-table');
    const actionButtons = document.getElementById('expedition-action-buttons');

    let tableHtml = '<table><thead><tr><th>Produkt</th><th>Stav</th><th>Plán</th><th>Realita</th><th>Akcie</th><th>Poznámka</th></tr></thead><tbody>';
    let hasPending = false, hasReadyForPrint = false;

    productions.forEach(p => {
      const isCompleted = p.status === 'Ukončené';
      const isReadyForPrint = p.status === 'Prijaté, čaká na tlač';
      if (!isCompleted && !isReadyForPrint) hasPending = true;
      if (isReadyForPrint) hasReadyForPrint = true;

      const planned = p.mj === 'ks'
        ? `${p.expectedPieces ?? '?'} ks`
        : `${safeToFixed(p.plannedQty)} kg`;

      let reality = (isCompleted || isReadyForPrint)
        ? (p.mj === 'ks' ? `${p.realPieces} ks` : `${safeToFixed(p.realQty)} kg`)
        : `<input type="number" id="actual_${p.batchId}" step="${p.mj === 'ks' ? 1 : 0.01}" style="width: 80px;">`;

      let actionsHtml = '';
      if (isCompleted || isReadyForPrint) {
        actionsHtml = `
          <div style="display: flex; gap: 5px; justify-content: center;">
            <button class="btn btn-info" style="margin:0;width:auto;flex:1; padding: 5px;" onclick="printAccompanyingLetter('${p.batchId}')" title="Tlačiť sprievodku"><i class="fas fa-print"></i></button>
            <button class="btn btn-secondary" style="margin:0;width:auto;flex:1; padding: 5px;" onclick="showTraceability('${p.batchId}')" title="Detail šarže"><i class="fas fa-search"></i></button>
          </div>`;
      } else {
        actionsHtml = `<select id="status_${p.batchId}">
            <option value="OK">OK</option>
            <option value="NEPRIJATÉ">NEPRIJATÉ</option>
            <option value="Iné">Iné</option>
          </select>`;
          actionsHtml = `
  <div style="display:flex; gap:6px; justify-content:center; align-items:center;">
    <select id="status_${p.batchId}">
      <option value="OK">OK</option>
      <option value="NEPRIJATÉ">NEPRIJATÉ</option>
      <option value="Iné">Iné</option>
    </select>
    <button class="btn btn-danger" style="margin:0;width:auto;flex:0"
      onclick="returnToProductionPrompt('${p.batchId}')">Vrátiť</button>
  </div>`;

      }

      const rowClass = isReadyForPrint ? 'batch-row-ok' : '';
      tableHtml += `<tr class="${rowClass}" data-batch-id="${p.batchId}" data-unit="${p.mj}" data-product-name="${escapeHtml(p.productName)}" data-planned-qty="${p.plannedQty}" data-production-date="${p.datum_vyroby}">
        <td>${escapeHtml(p.productName)}</td>
        <td>${escapeHtml(p.status)}</td>
        <td>${planned}</td>
        <td>${reality}</td>
        <td>${actionsHtml}</td>
        <td>${(isCompleted || isReadyForPrint) ? (p.poznamka_expedicie || '') : `<input type="text" id="note_${p.batchId}">`}</td>
      </tr>`;
    });

    container.innerHTML = tableHtml + '</tbody></table>';
    actionButtons.innerHTML = '';
    if (hasPending) actionButtons.innerHTML += `<button class="btn btn-success" onclick="completeProductions('${date}')">Potvrdiť prevzatie</button>`;
    if (hasReadyForPrint) actionButtons.innerHTML += `<button class="btn btn-danger" onclick="finalizeDay('${date}')">Finalizovať deň (uzávierka)</button>`;
  } catch(e) { /* spracované vyššie */ }
}
function returnToProductionPrompt(batchId){
  const qty = prompt("Zadajte množstvo (kg), ktoré vraciate do výroby:");
  if (qty === null) return;
  const q = parseFloat(qty);
  if (isNaN(q) || q <= 0) { showStatus("Neplatné množstvo.", true); return; }
  const reason = prompt("Dôvod vrátenia (napr. doudenie, prebal...):") || '';
  returnToProduction(batchId, q, reason);
}
async function returnToProduction(batchId, qty, reason){
  try {
    const res = await apiRequest('/api/expedicia/returnToProduction', {
      method:'POST', body:{ batchId, qty_kg: qty, reason }
    });
    showStatus(res.message || 'Vrátené do výroby.', false);
    // obvykle to nechceš v zozname – načítaj znova
    const title = document.getElementById('expedition-batch-list-title')?.textContent || '';
    const m = title.match(/(\d{1,2}\.\d{1,2}\.\d{4})/); // len orientačne
    // radšej si ulož aktuálny 'date' do globálu, alebo nechaj tak:
  } catch(e) {
    showStatus("Chyba pri vrátení do výroby: " + (e.message||""), true);
  }
}

// --- Detail šarže / sprievodný list / uzávierky ---
function showTraceability(batchId) { window.open(`/traceability/${batchId}`, '_blank'); }
async function completeProductions(date) {
  const workerName = document.getElementById('expedition-worker-name')?.value || '';
  if (!workerName) { showStatus("Zadajte meno preberajúceho pracovníka.", true); return; }

  // pozbieraj len riadky so stavom OK a zadanou realitou
  const rows = Array.from(document.querySelectorAll('#expedition-batch-table tbody tr'));
  const itemsToAccept = rows.map(row => {
    const batchId = row.dataset.batchId;
    const unit    = row.dataset.unit || '';
    const productName = row.dataset.productName || '';
    return {
      batchId,
      workerName,
      unit,
      productName,
      actualValue: document.getElementById(`actual_${batchId}`)?.value,
      note:        document.getElementById(`note_${batchId}`)?.value || '',
      status:      document.getElementById(`status_${batchId}`)?.value || 'OK'
    };
  }).filter(x => x.status === 'OK' && x.actualValue);

  if (itemsToAccept.length === 0) {
    showStatus("Nič na prevzatie. Zadajte reálne hodnoty pri položkách so stavom OK.", true);
    return;
  }

  try {
    // 1) prijmi dávky – backend vráti páry {accept_id, batch_id}
    const res = await apiRequest('/api/expedicia/acceptProductions', {
      method: 'POST',
      body: { items: itemsToAccept }
    });

    showStatus(res?.message || 'Prevzatie uložené.', false);

    // 2) okamžite otvor príjemku a sprievodný list (pre každú prijatú dávku)
    const accepted = Array.isArray(res?.accepted) ? res.accepted : [];
    accepted.forEach(pair => {
      try {
        // príjemka – GET (otvorí sa nový tab a rovno sa tlačí)
        apiRequest('/api/expedicia/printAcceptance?accept_id='+encodeURIComponent(pair.accept_id))
        .then(html=>{ try{ openPrintModal(html); }catch(_){ /* no-op */ } })
        .catch(()=>{});
      } catch (_) {}

      try {
        // sprievodný list – POST -> HTML -> nový tab
        const xsrf = getCookie('XSRF-TOKEN');
        fetch('/api/expedicia/getAccompanyingLetter', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': xsrf || '' },
          credentials: 'include',
          body: JSON.stringify({ batchId: pair.batch_id, workerName })
        })
        .then(r => r.text())
        .then(html => { try{ openPrintModal(html); }catch(_){ /* no-op */ } })
        .catch(() => {});
      } catch (_) {}
    });

    // 3) znova načítaj zoznam – prijaté už backend nevráti (viď patch B)
    if (date) loadProductionsByDate(date);

  } catch (e) {
    showStatus("Chyba pri prevzatí: " + (e?.message || ''), true);
  }
}

async function printAcceptance(accept_id){
  try {
    const xsrf = getCookie('XSRF-TOKEN') || getCookie('csrf_token') || '';
    const r = await fetch('/api/expedicia/printAcceptance', {
      method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json','X-CSRF-Token': xsrf },
      body: JSON.stringify({ accept_id })
    });
    if (!r.ok) throw new Error(await r.text());
    const html = await r.text();
    const w = window.open('', '_blank'); w.document.write(html); w.document.close();
  } catch(e) {
    showStatus("Chyba tlače príjemky: " + (e.message||""), true);
  }
}


async function finalizeDay(dateStr) {
  try {
    const result = await apiRequest('/api/expedicia/finalizeDay', { method: 'POST', body: { date_string: dateStr } });
    showStatus(result.message, false);
  } catch (err) {
    showStatus("Chyba pri uzávierke dňa.", true);
  }
}
async function showAccompanyingLetter(batchId, workerName){
  const r = await fetch('/api/expedicia/getAccompanyingLetter', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ batchId, workerName })
  });
  const html = await r.text();
  openPrintModal(html); // žiadne window.open
}

async function printAccompanyingLetter(batchId) {
  const workerName = document.getElementById('expedition-worker-name').value;
  if (!workerName) { showStatus("Zadajte meno preberajúceho pracovníka.", true); return; }
  try {
    const xsrf = getCookie('XSRF-TOKEN');
    const response = await fetch('/api/expedicia/getAccompanyingLetter', {
      method: 'POST',
      headers: {'Content-Type':'application/json','X-CSRF-Token': xsrf || ''},
      credentials: 'include',
      body: JSON.stringify({ batchId, workerName })
    });
    if (!response.ok) throw new Error(`Chyba servera: ${response.statusText}`);
    const htmlContent = await response.text();
    openPrintModal(htmlContent);
  } catch (e) {
    showStatus(`Chyba pri tlači: ${e.message}`, true);
  }
}

async function finalizeSlicing(logId) {
  const actualPieces = prompt("Zadajte reálny počet kusov, ktorý bol nakrájaný:");
  if (actualPieces === null || actualPieces === "" || isNaN(parseInt(actualPieces))) {
    showStatus("Zadaný neplatný počet kusov.", true); return;
  }
  try {
    const result = await apiRequest('/api/expedicia/finalizeSlicing', { method:'POST', body:{ logId, actualPieces: parseInt(actualPieces) } });
    showStatus(result.message, false);
    loadAndShowExpeditionMenu();
  } catch(e) { /* spracované vyššie */ }
}

// --- Inventúra ---
async function loadAndShowProductInventory() {
  try {
    const data = await apiRequest('/api/expedicia/getProductsForInventory');
    showExpeditionView('view-expedition-inventory');
    const container = document.getElementById('product-inventory-tables-container');
    container.innerHTML = '';
    for (const category in data) {
      if (data[category].length > 0) {
        container.innerHTML += `<h4>${escapeHtml(category)}</h4><div class="table-container">${createProductInventoryTable(data[category])}</div>`;
      }
    }
  } catch (e) { /* spracované vyššie */ }
}

function createProductInventoryTable(items) {
  let table = `<table><thead><tr><th>Názov Produktu</th><th>Systém (ks/kg)</th><th>Reálny stav (ks/kg)</th></tr></thead><tbody>`;
  items.forEach(item => {
    table += `<tr>
      <td>${escapeHtml(item.nazov_vyrobku)} (${item.mj})</td>
      <td>${item.system_stock_display}</td>
      <td><input type="number" step="0.01" data-ean="${escapeHtml(item.ean)}" class="product-inventory-input"></td>
    </tr>`;
  });
  return table + '</tbody></table>';
}

async function submitProductInventory() {
  const workerName = document.getElementById('inventory-worker-name').value;
  if (!workerName) { showStatus("Zadajte meno pracovníka, ktorý vykonáva inventúru.", true); return; }
  const inventoryData = Array.from(document.querySelectorAll('.product-inventory-input'))
    .filter(input => input.value)
    .map(input => ({ ean: input.dataset.ean, realQty: input.value }));

  if (inventoryData.length === 0) { showStatus("Nezadali ste žiadne reálne stavy.", true); return; }

  try {
    const result = await apiRequest('/api/expedicia/submitProductInventory', { method:'POST', body:{ workerName, inventoryData } });
    showStatus(result.message, false);
    setTimeout(loadAndShowExpeditionMenu, 2000);
  } catch (e) { /* spracované vyššie */ }
}

// --- Manuálny príjem ---
async function loadAndShowManualReceive() {
  try {
    const products = await apiRequest('/api/expedicia/getAllFinalProducts');
    showExpeditionView('view-expedition-manual-receive');
    const select = document.getElementById('manual-receive-product-select');
    select.innerHTML = '<option value="">Vyberte produkt...</option>';
    products.forEach(p => {
      const o = document.createElement('option');
      o.value = p.ean; o.textContent = `${p.name} (${p.unit})`;
      select.add(o);
    });
    document.getElementById('manual-receive-date').valueAsDate = new Date();
  } catch(e) { /* spracované vyššie */ }
}

async function submitManualReceive() {
  const data = {
    workerName: document.getElementById('manual-receive-worker-name').value,
    receptionDate: document.getElementById('manual-receive-date').value,
    ean: document.getElementById('manual-receive-product-select').value,
    quantity: document.getElementById('manual-receive-quantity').value
  };
  if (!data.workerName || !data.ean || !data.quantity) { showStatus("Všetky polia sú povinné.", true); return; }
  try {
    const result = await apiRequest('/api/expedicia/manualReceiveProduct', { method:'POST', body:data });
    showStatus(result.message, false);
    setTimeout(loadAndShowExpeditionMenu, 2000);
  } catch(e) { /* spracované vyššie */ }
}

// --- Požiadavka krájanie ---
async function loadAndShowSlicingRequest() {
  try {
    const products = await apiRequest('/api/expedicia/getSlicableProducts');
    showExpeditionView('view-expedition-slicing-request');
    const select = document.getElementById('slicing-product-select');
    select.innerHTML = '<option value="">Vyberte produkt na krájanie...</option>';
    products.forEach(p => {
      const o = document.createElement('option');
      o.value = p.ean; o.textContent = p.name; select.add(o);
    });
  } catch(e) { /* spracované vyššie */ }
}

async function submitSlicingRequest() {
  const data = {
    ean: document.getElementById('slicing-product-select').value,
    pieces: document.getElementById('slicing-planned-pieces').value
  };
  if (!data.ean || !data.pieces) { showStatus("Vyberte produkt a zadajte počet kusov.", true); return; }
  try {
    const result = await apiRequest('/api/expedicia/startSlicingRequest', { method:'POST', body:data });
    showStatus(result.message, false);
    setTimeout(loadAndShowExpeditionMenu, 2000);
  } catch(e) { /* spracované vyššie */ }
}

// --- Manuálny odpis škody ---
async function loadAndShowManualDamage() {
  try {
    const products = await apiRequest('/api/expedicia/getAllFinalProducts');
    showExpeditionView('view-expedition-manual-damage');
    const select = document.getElementById('damage-product-select');
    select.innerHTML = '<option value="">Vyberte produkt...</option>';
    products.forEach(p => {
      const o = document.createElement('option');
      o.value = p.ean; o.textContent = `${p.name} (${p.unit})`; select.add(o);
    });
    select.onchange = (e) => {
      const txt = e.target.options[e.target.selectedIndex]?.textContent || '';
      const m = txt.match(/\((.*)\)/);
      const unit = m ? m[1] : 'ks/kg';
      document.getElementById('damage-quantity-label').textContent = `Množstvo (${unit})`;
    };
  } catch(e) { /* spracované vyššie */ }
}

async function submitManualDamage() {
  const data = {
    workerName: document.getElementById('damage-worker-name').value,
    ean: document.getElementById('damage-product-select').value,
    quantity: document.getElementById('damage-quantity').value,
    note: document.getElementById('damage-note').value
  };
  if (!data.workerName || !data.ean || !data.quantity || !data.note) { showStatus("Všetky polia sú povinné.", true); return; }
  try {
    const result = await apiRequest('/api/expedicia/logManualDamage', { method:'POST', body:data });
    showStatus(result.message, false);
    setTimeout(loadAndShowExpeditionMenu, 2000);
  } catch(e) { /* spracované vyššie */ }
}

// --- Skenovanie (bez nutnosti vendor knižnice) ---
function startBarcodeScanner() {
  showExpeditionView('view-expedition-scanner');
  const scanResultEl = document.getElementById('scan-result');
  scanResultEl.textContent = '';

  if (typeof Html5Qrcode === 'undefined') {
    alert('Skenovanie nie je dostupné (knižnica nie je prítomná).');
    showExpeditionView('view-expedition-menu');
    return;
  }

  html5QrCode = new Html5Qrcode("scanner-container");
  const qrCodeSuccessCallback = (decodedText /*, decodedResult */) => {
    scanResultEl.textContent = `Naskenovaný kód: ${decodedText}`;
    stopBarcodeScanner();
    showTraceability(decodedText);
  };
  const config = { fps: 10, qrbox: { width: 250, height: 250 } };

  html5QrCode.start({ facingMode: "environment" }, config, qrCodeSuccessCallback)
    .catch(err => {
      showStatus(`Chyba pri spúšťaní kamery: ${err}`, true);
      showExpeditionView('view-expedition-menu');
    });
}

function stopBarcodeScanner() {
  if (html5QrCode && html5QrCode.isScanning) {
    html5QrCode.stop().catch(err => console.error("Nepodarilo sa zastaviť skener.", err));
  }
  showExpeditionView('view-expedition-menu');
}
// =================== AUTH / UI PREPÍNAČE ===================
function showLogin() {
  const lw  = document.getElementById('login-wrapper');
  const app = document.getElementById('expedicia-app');
  if (lw)  { lw.removeAttribute('hidden'); lw.style.display = ''; }
  if (app) { app.style.display = 'none'; }
  document.body.classList.remove('is-auth');
}
function showApp() {
  const lw  = document.getElementById('login-wrapper');
  const app = document.getElementById('expedicia-app');
  if (lw)  { lw.setAttribute('hidden',''); lw.style.display = 'none'; }
  if (app) { app.style.display = 'block'; }
  document.body.classList.add('is-auth');
}
/** Robustný vstup do modulu po úspešnom logine */
function forceEnterModule() {
  showApp();
  if (typeof showExpeditionView === 'function') showExpeditionView('view-expedition-menu');
  if (!window.__exp_menu_loaded && typeof loadAndShowExpeditionMenu === 'function') {
    window.__exp_menu_loaded = true;
    loadAndShowExpeditionMenu();
  }
  // Jednorazová poistka: ak by UI ostalo skryté, sprav reload /expedicia
  setTimeout(() => {
    const app = document.getElementById('expedicia-app');
    if (!app || getComputedStyle(app).display === 'none') {
      if (!window.__exp_reloaded_after_login) {
        window.__exp_reloaded_after_login = true;
        window.location.href = '/expedicia';
      }
    }
  }, 200);
}

// --- apiRequest – rozšírený CSRF zdroj (cookie XSRF-TOKEN / csrf_token / <meta>)
window.apiRequest = (typeof window.apiRequest === 'function') ? window.apiRequest : async (url, options = {}) => {
  const xsrf = getCookie('XSRF-TOKEN') || getCookie('csrf_token') ||
               document.querySelector('meta[name="csrf-token"]')?.content || '';
  const headers = Object.assign({'Content-Type':'application/json'}, options.headers || {});
  if (xsrf && !headers['X-CSRF-Token']) headers['X-CSRF-Token'] = xsrf;

  const init = {
    method: options.method || 'GET',
    credentials: 'include',
    headers,
  };
  if (options.body !== undefined) {
    init.body = (headers['Content-Type'] === 'application/json') ? JSON.stringify(options.body) : options.body;
  }
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = (await res.text().catch(()=>'')) || res.statusText;
    const err = new Error(text); err.status = res.status; throw err;
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
};

// --- Login/Logout volania (len tu) ---
async function tryLogin(username, password) {
  const xsrf = getCookie('XSRF-TOKEN') || getCookie('csrf_token') ||
               document.querySelector('meta[name="csrf-token"]')?.content || '';
  const headers = {'Content-Type':'application/json'};
  if (xsrf) headers['X-CSRF-Token'] = xsrf;

  // preferované API
  try {
    const r = await fetch('/api/internal/login', {
      method:'POST', credentials:'include', headers,
      body: JSON.stringify({ username, password })
    });
    if (r.ok) return true;
  } catch(_){}
  // alternatívne API (ak existuje)
  try {
    const r = await fetch('/api/auth/login', {
      method:'POST', credentials:'include', headers,
      body: JSON.stringify({ username, password })
    });
    if (r.ok) return true;
  } catch(_){}
  // fallback /login (form)
  try {
    const hForm = {'Content-Type':'application/x-www-form-urlencoded'};
    if (xsrf) hForm['X-CSRF-Token'] = xsrf;
    const r = await fetch('/login', {
      method:'POST', credentials:'include', headers:hForm,
      body: new URLSearchParams({ username, password })
    });
    if (r.ok || r.status === 302) return true;
  } catch(_){}
  return false;
}

async function logoutStayHere() {
  const xsrf = getCookie('XSRF-TOKEN') || getCookie('csrf_token') ||
               document.querySelector('meta[name="csrf-token"]')?.content || '';
  const h = xsrf ? { 'X-CSRF-Token': xsrf } : {};
  try { await fetch('/api/internal/logout', { method:'POST', credentials:'include', headers:h }); } catch(_){}
  try { await fetch('/api/auth/logout',   { method:'POST', credentials:'include', headers:h }); } catch(_){}
  showLogin();
  try { history.replaceState(null, '', '/expedicia'); } catch(_){}
}

// --- checkAuthAndInit – najprv check_session, potom prepni UI ---
async function checkAuthAndInit() {
  try {
    const r = await fetch('/api/internal/check_session', { credentials:'include' });
    if (r.ok) {
      const s = await r.json();
      if (s && s.authenticated) { forceEnterModule(); return; }
    }
  } catch(_){}
  showLogin();
}

// =================== DOMContentLoaded – JEDEN handler ===================
document.addEventListener('DOMContentLoaded', async () => {
  window.__exp_menu_loaded = false;

  // 1) Auth check najprv
  await checkAuthAndInit();

  // 2) Login – aliasy + CAPTURE submit
  const form = document.getElementById('login-form');
  if (form) {
    const uVis = document.getElementById('login-username') || document.getElementById('username');
    const pVis = document.getElementById('login-password') || document.getElementById('password');

    // skryté aliasy (#username/#password) pre iný kód (ak chýbajú)
    let uHidden = document.getElementById('username');
    let pHidden = document.getElementById('password');
    if (!uHidden) { uHidden = document.createElement('input'); uHidden.type='hidden'; uHidden.id='username'; uHidden.name='username'; form.appendChild(uHidden); }
    if (!pHidden) { pHidden = document.createElement('input'); pHidden.type='hidden'; pHidden.id='password'; pHidden.name='password'; form.appendChild(pHidden); }

    const sync = () => { if (uVis) uHidden.value = uVis.value; if (pVis) pHidden.value = pVis.value; };
    uVis && uVis.addEventListener('input', sync);
    pVis && pVis.addEventListener('input', sync);
    sync();

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      e.stopImmediatePropagation(); // zruší iné submit-handlery (napr. v common.js)

      const u = (uVis?.value || uHidden.value || '').trim();
      const p = (pVis?.value || pHidden.value || '');
      const status = document.getElementById('login-status');
      if (!u || !p) { if (status) status.textContent = 'Zadajte meno a heslo.'; return; }

      const btn = form.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      try {
        const ok = await tryLogin(u, p);
        if (ok) {
          if (status) status.textContent = 'Prihlásenie OK…';
          forceEnterModule(); // prepni + načítaj menu (raz)
        } else {
          if (status) status.textContent = 'Prihlásenie zlyhalo.';
        }
      } finally {
        if (btn) btn.disabled = false;
      }
    }, true); // CAPTURE = true
  }

  // 3) Logout – zostaň na /expedicia, zobraz login
  document.getElementById('btn-logout')?.addEventListener('click', logoutStayHere);

  // 4) Side bar navigácia
  document.querySelectorAll('.nav-item').forEach(a => {
    a.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(x => x.classList.remove('active'));
      a.classList.add('active');
      if (typeof showExpeditionView === 'function') showExpeditionView(a.dataset.view);
    });
  });

  // 5) Tlačidlá v menu
  const $ = (s)=>document.querySelector(s);
  $('#btn-load-dates')?.addEventListener('click', loadProductionDates);
  $('#btn-open-scanner')?.addEventListener('click', startBarcodeScanner);
  $('#btn-open-inventory')?.addEventListener('click', loadAndShowProductInventory);
  $('#btn-open-manual-receive')?.addEventListener('click', loadAndShowManualReceive);
  $('#btn-open-slicing')?.addEventListener('click', loadAndShowSlicingRequest);
  $('#btn-open-damage')?.addEventListener('click', loadAndShowManualDamage);
  $('#btn-submit-inventory')?.addEventListener('click', submitProductInventory);
  $('#btn-submit-manual-receive')?.addEventListener('click', submitManualReceive);
  $('#btn-submit-slicing')?.addEventListener('click', submitSlicingRequest);
  $('#btn-submit-damage')?.addEventListener('click', submitManualDamage);
});


// === HARD FIX LOGIN PRE /expedicia – obíď common.js, pošli správne dáta ===
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('login-form');
  if (!form) return;

  // 1) Urob aliasy polí: podpor obidva názvy (#username/#password a #login-username/#login-password)
  const uVis = document.getElementById('username') || document.getElementById('login-username');
  const pVis = document.getElementById('password') || document.getElementById('login-password');

  // Ak common.js očakáva #username/#password a ty máš len login-*,
  // vytvoríme skryté aliasy a budeme ich priebežne synchronizovať.
  let uHidden = document.getElementById('username');
  let pHidden = document.getElementById('password');

  if (!uHidden) {
    uHidden = document.createElement('input');
    uHidden.type = 'hidden'; uHidden.id = 'username'; uHidden.name = 'username';
    form.appendChild(uHidden);
  }
  if (!pHidden) {
    pHidden = document.createElement('input');
    pHidden.type = 'hidden'; pHidden.id = 'password'; pHidden.name = 'password';
    form.appendChild(pHidden);
  }

  const sync = () => {
    if (uVis) uHidden.value = uVis.value;
    if (pVis) pHidden.value = pVis.value;
  };
  // priebežná synchronizácia, aby akýkoľvek iný kód videl správne hodnoty
  ['input','change'].forEach(evt => {
    uVis && uVis.addEventListener(evt, sync);
    pVis && pVis.addEventListener(evt, sync);
  });
  sync();

  // 2) Zachyť submit v CAPTURE fáze a úplne potlač ďalších poslucháčov (napr. common.js)
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    e.stopImmediatePropagation(); // zastaví ďalšie handler-y (vrátane common.js)

    const username = (uHidden.value || '').trim();
    const password = pHidden.value || '';
    const statusEl = document.getElementById('login-status');

    if (!username || !password) {
      if (statusEl) statusEl.textContent = 'Zadajte meno a heslo.';
      return;
    }

    try {
      const headers = {'Content-Type':'application/json'};
      const csrf = document.querySelector('meta[name="csrf-token"]')?.content; 
      if (csrf) headers['X-CSRF-Token'] = csrf;

      const rsp = await fetch('/api/internal/login', {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify({ username, password })
      });

      if (rsp.ok) {
        if (statusEl) statusEl.textContent = 'Prihlásenie OK…';
        // zobraz aplikáciu a načítaj dashboard
        if (typeof showApp === 'function') showApp();
        if (typeof loadAndShowExpeditionMenu === 'function') loadAndShowExpeditionMenu();
      } else {
        const txt = await rsp.text();
        if (statusEl) statusEl.textContent = txt || 'Prihlásenie zlyhalo.';
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = 'Chyba pripojenia.';
      console.error(err);
    }
  }, true); // <-- CAPTURE = true (naozaj dôležité)
});
async function onScan(){
  const el = document.getElementById('scanBox');
  const code = (el?.value || '').trim();
  if(!code) return;

  const r = await fetch('/api/expedicia/scanPayload', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({code})
  });
  const data = await r.json();

  if(data.error){
    alert(data.error);
  }else{
    // TODO: otvor modal s detailami výroby
    console.log('SCAN DATA', data);
  }
  el.value = '';
}

document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('scanBox');
  if(el){
    el.addEventListener('keydown', (e) => { if(e.key === 'Enter') onScan(); });
  }
});
/* =======================
   Expedícia: modal + skener
   ======================= */
(function(){
  // Ak už existujú globálne modálne funkcie, nahrádzať ich nebudeme
  if (typeof window.openPrintModal !== 'function') {
    window.openPrintModal = function(html){
      var m = document.getElementById('printModal');
      var fr = document.getElementById('printFrame');
      if (!m || !fr) return;
      fr.srcdoc = html;
      m.classList.remove('hidden');
    };
  }
  if (typeof window.closePrintModal !== 'function') {
    window.closePrintModal = function(){
      var m = document.getElementById('printModal');
      var fr = document.getElementById('printFrame');
      if (!m || !fr) return;
      m.classList.add('hidden');
      fr.srcdoc = '';
    };
  }
  if (typeof window.printIframe !== 'function') {
    window.printIframe = function(){
      var fr = document.getElementById('printFrame');
      if (fr && fr.contentWindow) {
        fr.contentWindow.focus();
        fr.contentWindow.print();
      }
    };
  }

  var state = { lastBatchId: null };

  function escapeHtml(s){
    return String(s)
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function openScannerView(){
    try {
      var views = document.querySelectorAll('section.view');
      for (var i=0;i<views.length;i++) views[i].style.display = 'none';
      var sec = document.getElementById('view-expedition-scanner');
      if (sec) sec.style.display = '';
      setTimeout(function(){ var el = document.getElementById('scanBox'); if (el) el.focus(); }, 50);
    } catch(e){}
  }

  async function onScan(){
    var el = document.getElementById('scanBox');
    var raw = (el && el.value ? el.value : '').trim();
    if (!raw) return;

    var code = raw.replace(/[\r\n\t]/g, '');

    try{
      var r = await fetch('/api/expedicia/scanPayload', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({code: code})
      });
      var data = await r.json();

      if (!r.ok || (data && data.error)) {
        renderScanResult({ error: (data && data.error) ? data.error : ('HTTP ' + r.status) });
        state.lastBatchId = null;
        var btn1 = document.getElementById('btn-print-letter'); if (btn1) btn1.disabled = true;
        return;
      }

      renderScanResult(data);

      if (code.indexOf('BATCH:') === 0) {
        var idStr = code.split(':',1)[1] || code.substring(6);
        var id = parseInt(idStr, 10);
        state.lastBatchId = isFinite(id) ? id : null;
      } else if (data && data.header && data.header.id) {
        state.lastBatchId = data.header.id;
      } else {
        state.lastBatchId = null;
      }
      var btn2 = document.getElementById('btn-print-letter'); if (btn2) btn2.disabled = !state.lastBatchId;
    } catch(err){
      renderScanResult({ error: String(err) });
      state.lastBatchId = null;
      var btn3 = document.getElementById('btn-print-letter'); if (btn3) btn3.disabled = true;
    } finally {
      if (el) el.value = '';
    }
  }

  function renderScanResult(payload){
    var box = document.getElementById('scan-result');
    if (!box) return;

    if (payload && payload.error){
      box.innerHTML = '<div class="card" style="border-left:4px solid #d33;padding:.75rem 1rem;">'
        + '<strong>Chyba skenu:</strong> ' + escapeHtml(payload.error) + '</div>';
      return;
    }

    var h = (payload && payload.header) ? payload.header : {};
    var ingr = (payload && payload.ingredients) ? payload.ingredients : [];
    var product = escapeHtml(h.product_name || '');
    var ean = escapeHtml(h.ean || '');
    var stav = escapeHtml(h.stav || '');
    var dv = ((h.datum_vyroby || '') + '').substring(0, 19).replace('T',' ');
    var plan = Number(h.planovane_mnozstvo || 0);
    var real = Number(h.skutocne_vyrobene || 0);

    var eanSpan = ean ? ('&nbsp;<small class="muted">(EAN: ' + ean + ')</small>') : '';

    var rows = (ingr || []).map(function(it){
      var nd = (it.na_davku != null ? Number(it.na_davku) : 0).toFixed(3);
      var nr = (it.na_real  != null ? Number(it.na_real)  : 0).toFixed(3);
      return '<tr>'
        + '<td>' + escapeHtml(it.surovina || '') + '</td>'
        + '<td class="right">' + nd + '</td>'
        + '<td class="right">' + nr + '</td>'
        + '</tr>';
    }).join('');

    box.innerHTML =
      '<div class="card">'
        + '<h3 style="margin:.2rem 0 0.6rem;">' + product + (ean ? ' ' + eanSpan : '') + '</h3>'
        + '<div class="row" style="flex-wrap:wrap; gap:1.2rem;">'
          + '<div><strong>Dátum výroby:</strong> ' + escapeHtml(dv) + '</div>'
          + '<div><strong>Plán:</strong> ' + plan.toFixed(3) + '</div>'
          + '<div><strong>Skutočne:</strong> ' + real.toFixed(3) + '</div>'
          + '<div><strong>Stav:</strong> ' + stav + '</div>'
        + '</div>'
      + '</div>'
      + '<div class="card">'
        + '<h4>Recept / Zloženie</h4>'
        + '<div class="table-wrap">'
          + '<table class="table">'
            + '<thead>'
              + '<tr>'
                + '<th>Surovina</th>'
                + '<th class="right">Na dávku</th>'
                + '<th class="right">Na reálnu výrobu</th>'
              + '</tr>'
            + '</thead>'
            + '<tbody>'
              + (rows || '<tr><td colspan="3" class="muted">Bez položiek receptu.</td></tr>')
            + '</tbody>'
          + '</table>'
        + '</div>'
      + '</div>';
  }

  async function printLetterFromScan(){
    if (!state.lastBatchId) return;
    var wnEl = document.getElementById('expedition-worker-name');
    var worker = (wnEl && wnEl.value ? wnEl.value : 'skener').trim();
    var r = await fetch('/api/expedicia/getAccompanyingLetter', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ batchId: state.lastBatchId, workerName: worker })
    });
    var html = await r.text();
    window.openPrintModal(html);
  }

  function clearScan(){
    var box = document.getElementById('scan-result');
    if (box) box.innerHTML = '';
    state.lastBatchId = null;
    var btn = document.getElementById('btn-print-letter');
    if (btn) btn.disabled = true;
    var sb = document.getElementById('scanBox');
    if (sb) sb.focus();
  }

  // Bind eventy po načítaní
  document.addEventListener('DOMContentLoaded', function(){
    var sb = document.getElementById('scanBox');
    if (sb) sb.addEventListener('keydown', function(e){ if (e.key === 'Enter') onScan(); });

    var bpl = document.getElementById('btn-print-letter');
    if (bpl) bpl.addEventListener('click', printLetterFromScan);

    var bcs = document.getElementById('btn-clear-scan');
    if (bcs) bcs.addEventListener('click', clearScan);

    var bos = document.getElementById('btn-open-scanner');
    if (bos) bos.addEventListener('click', openScannerView);

    var links = document.querySelectorAll('.nav a.nav-item[data-view="view-expedition-scanner"]');
    for (var i=0;i<links.length;i++){
      links[i].addEventListener('click', function(){
        setTimeout(function(){
          var el = document.getElementById('scanBox');
          if (el) el.focus();
        }, 120);
      });
    }
  });
})();
