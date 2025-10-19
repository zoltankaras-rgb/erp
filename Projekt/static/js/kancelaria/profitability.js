// static/js/kancelaria/profitability.js
// Modul ZISKOVOSŤ – moderné, prehľadné karty (ako fleet): 1 aktívna sekcia naraz

/* --- Profitability: safe DOM helpers --- */
function qs(root, sel) { return (root || document).querySelector(sel); }
function qsa(root, sel) { return Array.from((root || document).querySelectorAll(sel)); }
function on(el, evt, fn) {
  if (!el) { console.warn('[profitability] chýba prvok pre', evt); return; }
  el.addEventListener(evt, fn);
}

/* ---------- helpers ---------- */
const esc = s => (s==null?'':String(s)).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const fx  = (n,d=2)=>{ const x=Number(n); return Number.isFinite(x)?x.toFixed(d):''; };
function toast(msg, err=false){ try{ window.showStatus?.(msg, !!err); }catch{ err?alert(msg):console.log(msg); } }

/* ==== DASHBOARD helpers ==== */
function pct(prev, curr){
  if (prev == null || prev === 0) return null;
  return ((curr - prev) / Math.abs(prev)) * 100.0;
}
/** KPI s rozumnou farbou: pre costs je pokles zelene, nárast červene */
function dashKPI(label, value, prevValue, opts={}){
  const isCost = !!opts.isCost;
  const pRaw = pct(prevValue, value);
  const arrow = pRaw==null ? '' : (pRaw >= 0 ? '▲' : '▼');
  const beneficial = pRaw==null ? null : (isCost ? (pRaw < 0) : (pRaw >= 0));
  const cls = beneficial==null ? '' : (beneficial ? 'pos' : 'neg');
  const delta = pRaw==null ? '' : `<span class="delta ${cls}">${arrow} ${fx(pRaw,1)}%</span>`;
  return `<div class="kpi"><div class="lbl">${label}</div><div class="val">€ ${fx(value)}</div>${delta}</div>`;
}

/* ---------- state ---------- */
let profState = {
  year:  new Date().getFullYear(),
  month: new Date().getMonth()+1,
  activeTab: 'dash', // 'departments' | 'production' | 'sales' | 'calcs'
  data: null,
  dashboard: null,
  currentSalesChannel: null,
  currentCalcId: null
};
window.profState = profState;

/* ---------- init ---------- */
async function initializeProfitabilityModule(){
  const root = document.getElementById('section-profitability');
  if (!root) return;

  // rámec UI
  root.innerHTML = `
    <div class="card">
      <div class="row wrap" style="gap:12px; align-items:flex-end; justify-content:center">
        <label>Rok
          <select id="prof-year"></select>
        </label>
        <label>Mesiac
          <select id="prof-month"></select>
        </label>
      </div>
      <div class="row wrap prof-tabs" style="gap:10px; justify-content:center; margin-top:12px">
        <button data-tab="dash" class="btn active">Prehľad</button>
        <button data-tab="departments" class="btn">Oddelenia</button>
        <button data-tab="production"  class="btn">Výroba</button>
        <button data-tab="sales"       class="btn">Predajné kanály</button>
        <button data-tab="calcs"       class="btn">Kalkulácie</button>
      </div>
    </div>
    <div id="prof-body"></div>
  `;

  // rok/mesiac
  const ySel = document.getElementById('prof-year');
  const mSel = document.getElementById('prof-month');
  const yNow = new Date().getFullYear();
  for (let y=yNow; y>=yNow-5; y--) ySel.add(new Option(y, y));
  ["Január","Február","Marec","Apríl","Máj","Jún","Júl","August","September","Október","November","December"]
    .forEach((n,i)=> mSel.add(new Option(n, i+1)));
  ySel.value = profState.year;
  mSel.value = profState.month;
  ySel.onchange = async ()=>{
    profState.year = Number(ySel.value);
    await loadData();
    await loadDashboard();
    renderActive();
  };
  mSel.onchange = async ()=>{
    profState.month = Number(mSel.value);
    await loadData();
    await loadDashboard();
    renderActive();
  };

  // tabs
  document.querySelectorAll('.prof-tabs .btn').forEach(b=>{
    b.onclick = ()=>{
      document.querySelectorAll('.prof-tabs .btn').forEach(x=>x.classList.remove('active'));
      b.classList.add('active');
      profState.activeTab = b.dataset.tab;
      renderActive();
    };
  });

  await loadData();
  await loadDashboard();
  renderActive(); // render vloží markup konkrétnej karty a v ňom sa volá wiring
}
window.initializeProfitabilityModule = initializeProfitabilityModule;

/* ---------- data ---------- */
async function loadData(){
  const payload = { year: profState.year, month: profState.month };
  const res = await apiRequest('/api/kancelaria/profitability/getData', { method:'POST', body: payload });
  if (res?.error) { toast(res.error, true); profState.data = null; return; }
  profState.data = res || {};
}
async function loadDashboard(){
  try{
    const payload = { year: profState.year, month: profState.month, months_back: 12 };
    const res = await apiRequest('/api/kancelaria/profitability/getDashboard', { method:'POST', body: payload });
    profState.dashboard = res || { series: [] };
  } catch(e){
    console.warn('[profitability] dashboard endpoint nedostupný', e);
    profState.dashboard = { series: [] };
  }
}

/* ---------- routing ---------- */
function renderActive(){
  const host = document.getElementById('prof-body');
  if (!host) return;
  host.innerHTML = '';
  const title = (t)=>`<div class="section-header"><h2>Ziskovosť – ${t} (${String(profState.month).padStart(2,'0')}/${profState.year})</h2></div>`;

  if (profState.activeTab === 'dash'){
    host.innerHTML = title('Prehľad') + renderDashboardCard();
    return;
  }
  if (profState.activeTab === 'departments'){
    host.innerHTML = title('Oddelenia') + renderDepartmentsCard();
    wireDepartmentsCard();
  }
  else if (profState.activeTab === 'production'){
    host.innerHTML = title('Výroba') + renderProductionCard();
    wireProductionCard();
  }
  else if (profState.activeTab === 'sales'){
    host.innerHTML = title('Predajné kanály') + `<div id="prof-sales-box"></div>`;
    renderSalesChannels();
  }
  else if (profState.activeTab === 'calcs'){
    host.innerHTML = title('Kalkulácie') + renderCalcsCard();
    wireCalcsCard();
  }
}

/* ===================== PREHĽAD / DASHBOARD ===================== */
function renderDashboardCard(){
  const s = (profState.dashboard?.series || []).slice().sort((a,b)=> (a.year*100+a.month)-(b.year*100+b.month));
  const last = s[s.length-1] || null;
  const prev = s[s.length-2] || null;

  const style = `
    <style>
      .kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
      .kpi .lbl{opacity:.7;font-size:12px}
      .kpi .val{font-size:22px;font-weight:600}
      .delta.pos{color:#0a8;margin-left:6px}
      .delta.neg{color:#c33;margin-left:6px}
      .table .num{text-align:right}
    </style>`;

  const kpis = !last ? '<div class="card"><p>Žiadne dáta.</p></div>' : `
    <div class="card">
      <div class="kpi-grid">
        ${dashKPI('Tržby (Expedícia)', last.revenue_eur, prev?.revenue_eur)}
        ${dashKPI('COGS (Expedícia)', last.cogs_eur, prev?.cogs_eur, {isCost:true})}
        ${dashKPI('Zisk Expedície', last.expedition_profit_eur, prev?.expedition_profit_eur)}
        ${dashKPI('Zisk spolu (NET)', last.net_profit_eur, prev?.net_profit_eur)}
      </div>
      <div class="kpi-grid" style="margin-top:12px">
        ${dashKPI('Zisk Rozrábky', last.butchering_profit_eur, prev?.butchering_profit_eur)}
        ${dashKPI('Zisk Výroby', last.production_profit_eur, prev?.production_profit_eur)}
        ${dashKPI('Všeobecné náklady', last.general_costs_eur, prev?.general_costs_eur, {isCost:true})}
        <div></div>
      </div>
    </div>`;

  const rows = s.map(row => `
    <tr>
      <td>${String(row.month).padStart(2,'0')}/${row.year}</td>
      <td class="num">€ ${fx(row.revenue_eur)}</td>
      <td class="num">€ ${fx(row.cogs_eur)}</td>
      <td class="num">€ ${fx(row.expedition_profit_eur)}</td>
      <td class="num">€ ${fx(row.butchering_profit_eur)}</td>
      <td class="num">€ ${fx(row.production_profit_eur)}</td>
      <td class="num">€ ${fx(row.general_costs_eur)}</td>
      <td class="num"><strong>€ ${fx(row.net_profit_eur)}</strong></td>
    </tr>`).join('');

  const table = `
    <div class="card mt">
      <div class="table-wrap">
        <table class="table">
          <thead><tr>
            <th>Mesiac</th>
            <th class="num">Tržby</th>
            <th class="num">COGS</th>
            <th class="num">Zisk Expedície</th>
            <th class="num">Zisk Rozrábky</th>
            <th class="num">Zisk Výroby</th>
            <th class="num">Všeobecné náklady</th>
            <th class="num">Zisk spolu</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;

  return style + kpis + table;
}

/* ===================== ODD/DEPARTMENTS ===================== */
function renderDepartmentsCard(){
  const d = profState.data?.department_data || {};
  const f = (k)=> Number(d[k] || 0);

  return `
    <div class="card">
      <div class="grid-2">
        <label>Expedícia – Počiatočný stav (€) <input type="number" step="0.01" id="dep-exp_stock_prev" value="${f('exp_stock_prev')}"></label>
        <label>Expedícia – Dovoz z rozrábky (€) <input type="number" step="0.01" id="dep-exp_from_butchering" value="${f('exp_from_butchering')}"></label>
        <label>Expedícia – Dovoz z výroby (€) <input type="number" step="0.01" id="dep-exp_from_prod" value="${f('exp_from_prod')}"></label>
        <label>Expedícia – Externý nákup (€) <input type="number" step="0.01" id="dep-exp_external" value="${f('exp_external')}"></label>
        <label>Expedícia – Vrátenky (€) <input type="number" step="0.01" id="dep-exp_returns" value="${f('exp_returns')}"></label>
        <label>Expedícia – Koncový stav (€) <input type="number" step="0.01" id="dep-exp_stock_current" value="${f('exp_stock_current')}"></label>
        <label>Expedícia – Tržby (€) <input type="number" step="0.01" id="dep-exp_revenue" value="${f('exp_revenue')}"></label>

        <label>Rozrábka – hodnota mäsa (€) <input type="number" step="0.01" id="dep-butcher_meat_value" value="${f('butcher_meat_value')}"></label>
        <label>Rozrábka – platený tovar (€) <input type="number" step="0.01" id="dep-butcher_paid_goods" value="${f('butcher_paid_goods')}"></label>
        <label>Rozrábka – spracovanie (€) <input type="number" step="0.01" id="dep-butcher_process_value" value="${f('butcher_process_value')}"></label>
        <label>Rozrábka – vrátenky (€) <input type="number" step="0.01" id="dep-butcher_returns_value" value="${f('butcher_returns_value')}"></label>

        <label class="col-span-2">Všeobecné náklady (€) <input type="number" step="0.01" id="dep-general_costs" value="${f('general_costs')}"></label>
      </div>
      <div class="row right mt">
        <button id="dep-save" class="btn btn-primary">Uložiť</button>
      </div>
    </div>
  `;
}
function wireDepartmentsCard(){
  const $ = (id)=> document.getElementById(id);
  const saveBtn = $('dep-save');
  if (!saveBtn) { console.warn('[profitability] chýba #dep-save'); return; }

  saveBtn.onclick = async ()=>{
    const body = {
      year: profState.year, month: profState.month,
      exp_stock_prev: +($('dep-exp_stock_prev')?.value || 0),
      exp_from_butchering: +($('dep-exp_from_butchering')?.value || 0),
      exp_from_prod: +($('dep-exp_from_prod')?.value || 0),
      exp_external: +($('dep-exp_external')?.value || 0),
      exp_returns: +($('dep-exp_returns')?.value || 0),
      exp_stock_current: +($('dep-exp_stock_current')?.value || 0),
      exp_revenue: +($('dep-exp_revenue')?.value || 0),
      butcher_meat_value: +($('dep-butcher_meat_value')?.value || 0),
      butcher_paid_goods: +($('dep-butcher_paid_goods')?.value || 0),
      butcher_process_value: +($('dep-butcher_process_value')?.value || 0),
      butcher_returns_value: +($('dep-butcher_returns_value')?.value || 0),
      general_costs: +($('dep-general_costs')?.value || 0),
    };
    const r = await apiRequest('/api/kancelaria/profitability/saveDepartmentData', { method:'POST', body });
    if (r?.error) return toast(r.error, true);
    toast('Oddelenia uložené.');
    await loadData();
    await loadDashboard();
    renderActive();                      // re-render mení DOM...
    requestAnimationFrame(() => {        // ...preto znova naviaž handlery
      try { wireDepartmentsCard(); }
      catch(e){ console.error('[profitability] wire failed', e); }
    });
  };
}

/* ===================== VÝROBA ===================== */
function renderProductionCard(){
  const rows = profState.data?.production_view?.rows || [];
  if (!rows.length){
    return `<div class="card"><p>Žiadne výrobky pre zvolený mesiac.</p></div>`;
  }
  let html = `
    <div class="card">
      <div class="table-wrap">
        <table class="table">
          <thead><tr>
            <th>EAN</th><th>Výrobok</th>
            <th class="num">Predané (kg)</th>
            <th class="num">Transfer €/kg</th>
            <th class="num">Náklad €/kg</th>
            <th class="num">Zisk (€)</th>
          </tr></thead>
          <tbody id="prod-tbody">`;
  for (const r of rows){
    const profit = Number(r.profit||0);
    html += `
      <tr data-ean="${esc(r.ean||'')}">
        <td>${esc(r.ean||'')}</td>
        <td>${esc(r.name||'')}</td>
        <td class="num"><input class="prod-kg" type="number" step="0.001" value="${r.exp_sales_kg||''}"></td>
        <td class="num"><input class="prod-transfer" type="number" step="0.001" value="${r.transfer_price||''}"></td>
        <td class="num">${fx(r.production_cost||0)}</td>
        <td class="num">${fx(profit)}</td>
      </tr>`;
  }
  html += `</tbody></table></div>
      <div class="row right mt"><button id="prod-save" class="btn btn-primary">Uložiť dáta výroby</button></div>
    </div>`;
  return html;
}
function wireProductionCard(){
  const save = document.getElementById('prod-save');
  if (!save) return;
  save.onclick = async ()=>{
    const rows = [];
    document.querySelectorAll('#prod-tbody tr').forEach(tr=>{
      rows.push({
        ean: tr.dataset.ean,
        expedition_sales_kg: Number(tr.querySelector('.prod-kg')?.value || 0),
        transfer_price: Number(tr.querySelector('.prod-transfer')?.value || 0)
      });
    });
    const r = await apiRequest('/api/kancelaria/profitability/saveProductionData', {
      method:'POST', body:{ year: profState.year, month: profState.month, rows }
    });
    if (r?.error) return toast(r.error, true);
    toast('Výroba uložená.');
    await loadData(); await loadDashboard(); renderActive();
  };
}

/* ===================== PREDAJNÉ KANÁLY ===================== */
function renderSalesChannels(){
  const box = document.getElementById('prof-sales-box');
  const sc = profState.data?.sales_channels_view || {};
  const channels = Object.keys(sc);

  if (!channels.length){
    box.innerHTML = `
      <div class="card">
        <p>Nie sú pripravené žiadne kanály pre ${String(profState.month).padStart(2,'0')}/${profState.year}.</p>
        <div class="row wrap mt" style="gap:10px">
          <input id="sc-new-name" placeholder="Názov kanála (napr. Maloobchod)">
          <button id="sc-new-btn" class="btn btn-primary">Pripraviť kanál</button>
        </div>
      </div>`;
    document.getElementById('sc-new-btn').onclick = setupNewChannel;
    return;
  }

  if (!profState.currentSalesChannel) profState.currentSalesChannel = channels[0];
  const active = profState.currentSalesChannel;
  const data = sc[active] || { items:[], summary:{} };

  box.innerHTML = `
    <div class="card">
      <div class="row wrap" style="gap:10px; align-items:flex-end">
        <label>Kanál
          <select id="sc-chooser">
            ${channels.map(c=>`<option value="${esc(c)}" ${c===active?'selected':''}>${esc(c)}</option>`).join('')}
          </select>
        </label>
        <div style="flex:1"></div>
        <input id="sc-new-name" placeholder="Nový kanál (názov)">
        <button id="sc-new-btn" class="btn">Pripraviť kanál</button>
        <button id="sc-save-btn" class="btn btn-primary">Uložiť dáta kanála</button>
      </div>
    </div>

    <div class="card mt">
      <div class="profit-filters">
        <label>Hľadať produkt <input id="sc-search" placeholder="názov/EAN"></label>
        <label>Množstvo – všetkým <input id="sc-bulk-kg" type="number" step="0.001" placeholder="kg"></label>
        <label>Nákup €/kg – všetkým <input id="sc-bulk-buy" type="number" step="0.001" placeholder="0.00"></label>
        <label>Predaj €/kg – všetkým <input id="sc-bulk-sell" type="number" step="0.001" placeholder="0.00"></label>
        <div class="row" style="gap:8px">
          <button id="sc-apply-bulk" class="btn">Aplikovať na vyfiltrované</button>
          <button id="sc-clear-filter" class="btn">Vyčistiť filter</button>
        </div>
      </div>
    </div>

    <div class="card mt">
      <div class="table-wrap">
        <table class="table">
          <thead><tr>
            <th>Produkt</th>
            <th class="num">Predané (kg)</th>
            <th class="num">Nákup netto €/kg</th>
            <th class="num">Predaj netto €/kg</th>
            <th class="num">Zisk spolu (€)</th>
          </tr></thead>
          <tbody id="sc-tbody"></tbody>
          <tfoot>
            <tr>
              <td><strong>Súčet</strong></td>
              <td class="num" id="sc-sum-kg">0</td>
              <td></td><td></td>
              <td class="num" id="sc-sum-profit">0</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  `;

  document.getElementById('sc-chooser').onchange = (e)=>{ profState.currentSalesChannel = e.target.value; renderSalesChannels(); };
  document.getElementById('sc-new-btn').onclick = setupNewChannel;
  document.getElementById('sc-save-btn').onclick = saveSalesChannelRows;

  const searchEl = document.getElementById('sc-search');
  const bulkKg   = document.getElementById('sc-bulk-kg');
  const bulkBuy  = document.getElementById('sc-bulk-buy');
  const bulkSell = document.getElementById('sc-bulk-sell');

  searchEl.oninput = ()=> fillSalesRows(data.items, searchEl.value.trim().toLowerCase(), {bulkKg, bulkBuy, bulkSell});
  document.getElementById('sc-apply-bulk').onclick = ()=>{
    fillSalesRows(data.items, searchEl.value.trim().toLowerCase(), {bulkKg, bulkBuy, bulkSell}, true);
  };
  document.getElementById('sc-clear-filter').onclick = ()=>{
    searchEl.value=''; bulkKg.value=''; bulkBuy.value=''; bulkSell.value='';
    fillSalesRows(data.items, '', {bulkKg, bulkBuy, bulkSell});
  };

  fillSalesRows(data.items, '', {bulkKg, bulkBuy, bulkSell});
}
function fillSalesRows(items, term, bulk, applyBulk=false){
  const tbody = document.getElementById('sc-tbody');
  let html = '';
  let sumKg = 0, sumProfit = 0;
  const norm = v => Number(v || 0);

  const filtered = (items||[]).filter(r=>{
    if (!term) return true;
    const txt = `${r.product_name||''} ${r.product_ean||r.ean||''}`.toLowerCase();
    return txt.includes(term);
  });

  filtered.forEach(r=>{
    let kg   = norm(r.sales_kg);
    let buy  = norm(r.purchase_price_net);
    let sell = norm(r.sell_price_net);

    if (applyBulk){
      if (bulk.bulkKg?.value)   kg   = norm(bulk.bulkKg.value);
      if (bulk.bulkBuy?.value)  buy  = norm(bulk.bulkBuy.value);
      if (bulk.bulkSell?.value) sell = norm(bulk.bulkSell.value);
      r.sales_kg = kg; r.purchase_price_net = buy; r.sell_price_net = sell;
    }

    const profit = (sell - buy) * kg;
    sumKg += kg; sumProfit += profit;

    const ean = r.product_ean || r.ean || '';
    html += `
      <tr data-ean="${esc(ean)}">
        <td>${esc(r.product_name || ean)}</td>
        <td class="num"><input type="number" step="0.001" class="sc-kg"   value="${kg||''}"   style="width:110px"></td>
        <td class="num"><input type="number" step="0.001" class="sc-buy"  value="${buy||''}"  style="width:110px"></td>
        <td class="num"><input type="number" step="0.001" class="sc-sell" value="${sell||''}" style="width:110px"></td>
        <td class="num">${fx(profit)}</td>
      </tr>`;
  });

  tbody.innerHTML = html;
  document.getElementById('sc-sum-kg').textContent = fx(sumKg);
  document.getElementById('sc-sum-profit').textContent = fx(sumProfit);
}
async function setupNewChannel(){
  const name = (document.getElementById('sc-new-name')?.value || '').trim();
  if (!name) { toast('Zadaj názov kanála.', true); return; }
  const r = await apiRequest('/api/kancelaria/profitability/setupSalesChannel', {
    method:'POST', body:{ year: profState.year, month: profState.month, channel_name: name }
  });
  if (r?.error) return toast(r.error, true);
  toast(r?.message || 'Kanál pripravený.');
  await loadData();
  profState.currentSalesChannel = name;
  renderSalesChannels();
}
async function saveSalesChannelRows(){
  const rows = [];
  document.querySelectorAll('#sc-tbody tr').forEach(tr=>{
    rows.push({
      ean: tr.dataset.ean,
      sales_kg: Number(tr.querySelector('.sc-kg')?.value || 0),
      purchase_price_net: Number(tr.querySelector('.sc-buy')?.value || 0),
      purchase_price_vat: 0,
      sell_price_net: Number(tr.querySelector('.sc-sell')?.value || 0),
      sell_price_vat: 0
    });
  });
  if (!rows.length) return toast('Žiadne riadky na uloženie.', true);

  const r = await apiRequest('/api/kancelaria/profitability/saveSalesChannelData', {
    method:'POST', body:{ year: profState.year, month: profState.month, channel: profState.currentSalesChannel, rows }
  });
  if (r?.error) return toast(r.error, true);
  toast('Dáta kanála uložené.');
  await loadData(); await loadDashboard(); renderSalesChannels();
}

/* ===================== KALKULÁCIE ===================== */
function renderCalcsCard(){
  const v = profState.data?.calculations_view || {};
  const list = v.calculations || [];
  const vehicles = v.available_vehicles || [];
  const prods = v.available_products || [];

  const optionsVehicles = ['<option value="">— bez vozidla —</option>']
    .concat(vehicles.map(x=>`<option value="${x.id}">${esc([x.name, x.license_plate].filter(Boolean).join(' '))}</option>`)).join('');

  const optionsProducts = prods.map(p => `<option value="${esc(p.ean)}">${esc(p.nazov_vyrobku)} (${esc(p.ean)})</option>`).join('');

  let chooser = `
    <div class="card">
      <div class="row wrap" style="gap:10px; align-items:flex-end">
        <label>Vybrať kalkuláciu
          <select id="calc-chooser">
            ${list.map(c=>`<option value="${c.id}" ${c.id===profState.currentCalcId?'selected':''}>${esc(c.name)} (#${c.id})</option>`).join('')}
          </select>
        </label>
        <div style="flex:1"></div>
        <button id="calc-new" class="btn">Nová kalkulácia</button>
        <button id="calc-save" class="btn btn-primary">Uložiť</button>
        <button id="calc-del"  class="btn btn-danger">Vymazať</button>
      </div>
    </div>
  `;

  const active = list.find(c => c.id === profState.currentCalcId) || list[0];
  profState.currentCalcId = active?.id || null;

  if (!active){
    return chooser + `<div class="card mt"><p>Zatiaľ nemáš žiadne kalkulácie pre tento mesiac.</p></div>`;
  }

  let itemsHtml = (active.items||[]).map(it=>`
    <tr>
      <td><input class="ci-ean" list="calc-product-list" value="${esc(it.product_ean||'')}" placeholder="EAN"></td>
      <td>${esc(it.product_name||'')}</td>
      <td class="num"><input class="ci-kg"   type="number" step="0.001" value="${it.estimated_kg||''}"></td>
      <td class="num"><input class="ci-buy"  type="number" step="0.001" value="${it.purchase_price_net||''}"></td>
      <td class="num"><input class="ci-sell" type="number" step="0.001" value="${it.sell_price_net||''}"></td>
      <td class="num"><button class="btn btn-danger ci-del-row">X</button></td>
    </tr>
  `).join('');

  return chooser + `
    <div class="card mt">
      <div class="grid-2">
        <label>Názov <input id="calc-name" value="${esc(active.name||'')}" placeholder="Názov kalkulácie"></label>
        <label>Vozidlo
          <select id="calc-vehicle">${optionsVehicles}</select>
        </label>
        <label>Vzdialenosť (km) <input id="calc-km" type="number" step="0.1" value="${Number(active.distance_km||0)}"></label>
        <label>Doprava (€) <input id="calc-transport" type="number" step="0.01" value="${Number(active.transport_cost||0)}"></label>
      </div>
    </div>

    <div class="card mt">
      <div class="row right"><button id="calc-add-row" class="btn">+ Pridať položku</button></div>
      <div class="table-wrap mt">
        <table class="table">
          <thead>
            <tr><th>EAN</th><th>Produkt</th><th class="num">Kg</th><th class="num">Nákup €/kg</th><th class="num">Predaj €/kg</th><th></th></tr>
          </thead>
          <tbody id="calc-tbody">${itemsHtml}</tbody>
        </table>
      </div>
      <datalist id="calc-product-list">${optionsProducts}</datalist>
    </div>
  `;
}
function wireCalcsCard(){
  const v = profState.data?.calculations_view || {};
  const list = v.calculations || [];

  const chooser = document.getElementById('calc-chooser');
  if (chooser) chooser.onchange = ()=>{ profState.currentCalcId = Number(chooser.value)||null; renderActive(); };

  const btnNew = document.getElementById('calc-new');
  if (btnNew) btnNew.onclick = ()=>{
    profState.currentCalcId = null;
    // prázdna kalkulácia v UI
    profState.data.calculations_view.calculations.unshift({
      id: null, name:'Nová kalkulácia', vehicle_id:null, distance_km:0, transport_cost:0, items:[]
    });
    renderActive();
  };

  const btnSave = document.getElementById('calc-save');
  if (btnSave) btnSave.onclick = async ()=>{
    // zozbieraj hodnoty
    const id   = profState.currentCalcId;
    const name = (document.getElementById('calc-name')?.value || '').trim();
    if (!name) return toast('Zadaj názov kalkulácie.', true);
    const vehicle_id = document.getElementById('calc-vehicle')?.value || null;
    const distance_km = Number(document.getElementById('calc-km')?.value || 0);
    const transport_cost = Number(document.getElementById('calc-transport')?.value || 0);

    const items = [];
    document.querySelectorAll('#calc-tbody tr').forEach(tr=>{
      items.push({
        product_ean: tr.querySelector('.ci-ean')?.value || '',
        estimated_kg: Number(tr.querySelector('.ci-kg')?.value || 0),
        purchase_price_net: Number(tr.querySelector('.ci-buy')?.value || 0),
        sell_price_net: Number(tr.querySelector('.ci-sell')?.value || 0)
      });
    });

    const body = { id, name, year: profState.year, month: profState.month, vehicle_id, distance_km, transport_cost, items };
    const r = await apiRequest('/api/kancelaria/profitability/saveCalculation', { method:'POST', body });
    if (r?.error) return toast(r.error, true);
    toast('Kalkulácia uložená.');
    await loadData(); await loadDashboard(); renderActive();
  };

  const btnDel = document.getElementById('calc-del');
  if (btnDel) btnDel.onclick = async ()=>{
    if (!profState.currentCalcId) return toast('Žiadna vybraná kalkulácia.', true);
    const r = await apiRequest('/api/kancelaria/profitability/deleteCalculation', { method:'POST', body:{ id: profState.currentCalcId } });
    if (r?.error) return toast(r.error, true);
    toast('Kalkulácia vymazaná.');
    await loadData(); await loadDashboard(); renderActive();
  };

  const addRow = document.getElementById('calc-add-row');
  if (addRow) addRow.onclick = ()=>{
    const tb = document.getElementById('calc-tbody');
    tb.insertAdjacentHTML('beforeend', `
      <tr>
        <td><input class="ci-ean" list="calc-product-list" placeholder="EAN"></td>
        <td></td>
        <td class="num"><input class="ci-kg" type="number" step="0.001"></td>
        <td class="num"><input class="ci-buy" type="number" step="0.001"></td>
        <td class="num"><input class="ci-sell" type="number" step="0.001"></td>
        <td class="num"><button class="btn btn-danger ci-del-row">X</button></td>
      </tr>
    `);
    wireCalcTable();
  };

  wireCalcTable();
}
function wireCalcTable(){
  const table = document.getElementById('calc-tbody');
  if (!table) return;
  table.onclick = (e)=>{
    const btn = e.target.closest('.ci-del-row');
    if (!btn) return;
    btn.closest('tr')?.remove();
  };
}
