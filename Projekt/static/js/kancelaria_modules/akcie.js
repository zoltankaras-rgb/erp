// static/js/kancelaria_modules/akcie.js
// Modul "Akcie": reťazce + promo akcie + odporúčanie výroby + dashboard náhľad
// Registruje: window.initializeAkcieModule()

import { postJSON } from '/static/js/api_with_csrf.js?v=4';

const $   = (sel, r=document) => r.querySelector(sel);
const $$  = (sel, r=document) => Array.from(r.querySelectorAll(sel));
const on  = (el, ev, fn) => el && el.addEventListener(ev, fn);
const html = (el, h) => { if (el) el.innerHTML = h; };
const $id = (x)=> document.getElementById(x);

function ensureAkcieDom(){
  const host = $id('section-akcie');
  if (!host) return;
  if (host.innerHTML.trim()) return;

  html(host, `
    <h2>Akcie</h2>

    <div class="row gap">
      <button class="btn btn-tab active" id="akcie-tab-chains">Reťazce</button>
      <button class="btn btn-tab" id="akcie-tab-actions">Akcie</button>
      <button class="btn btn-tab" id="akcie-tab-dashboard">Nástenka</button>
    </div>

    <!-- Reťazce -->
    <div id="akcie-panel-chains" class="card mt">
      <h3>Reťazce</h3>
      <div class="row gap wrap">
        <input id="chain-name" placeholder="Názov reťazca (napr. COOP Jednota)">
        <input id="chain-mult" type="number" step="0.05" value="1.0" style="width:120px" title="koeficient predaja (1.0 = 100%)">
        <button id="chain-add" class="btn btn-primary">Pridať reťazec</button>
      </div>
      <p id="chain-msg" class="muted"></p>
      <div class="table-wrap mt">
        <table class="table">
          <thead><tr><th>ID</th><th>Názov</th><th>Koeficient</th><th>Vytvorené</th></tr></thead>
          <tbody id="chain-tbody"></tbody>
        </table>
      </div>
    </div>

    <!-- Akcie -->
    <div id="akcie-panel-actions" class="card mt" style="display:none">
      <h3>Vytvoriť akciu</h3>
      <div class="form-grid form-3">
        <label>Reťazec
          <select id="promo-chain"></select>
        </label>
        <label>Výrobok
          <select id="promo-product"></select>
        </label>
        <label>Predajná cena bez DPH (€)
          <input id="promo-price" type="number" step="0.01" min="0">
        </label>
        <label>Od dátumu
          <input id="promo-from" type="date">
        </label>
        <label>Do dátumu
          <input id="promo-to" type="date">
        </label>
        <label class="col-span-2">Poznámka
          <input id="promo-note" placeholder="voliteľné">
        </label>
      </div>
      <div class="row right mt">
        <button id="promo-add" class="btn btn-primary">Uložiť akciu</button>
      </div>
      <p id="promo-msg" class="muted"></p>

      <h3 class="mt">Zoznam akcií</h3>
      <div class="table-wrap">
        <table class="table">
          <thead><tr>
            <th>ID</th><th>Reťazec</th><th>Výrobok</th><th>Od</th><th>Do</th>
            <th>Cena (bez DPH)</th><th></th>
          </tr></thead>
          <tbody id="promo-tbody"></tbody>
        </table>
      </div>

      <div id="akcie-recommend" class="card mt" style="display:none"></div>
    </div>

    <!-- Nástenka (náhľad) -->
    <div id="akcie-panel-dashboard" class="card mt" style="display:none">
      <h3>Upozornenia (5 dní vopred)</h3>
      <ul id="dash-list" style="margin:.5rem 0 0 1rem"></ul>
    </div>
  `);
}

/* ====== pomocné API ====== */
async function apiChainsList(){ return postJSON('/api/kancelaria/akcie/chains/list', {}); }
async function apiChainsAdd(name, mult){ return postJSON('/api/kancelaria/akcie/chains/add', { name, multiplier: mult }); }
async function apiPromosList(upcoming_only=false){ return postJSON('/api/kancelaria/akcie/list', { upcoming_only }); }
async function apiPromosAdd(payload){ return postJSON('/api/kancelaria/akcie/add', payload); }
async function apiDashboard(){ return postJSON('/api/kancelaria/akcie/dashboard', {}); }
async function apiRecommend(promotion_id){ return postJSON('/api/kancelaria/akcie/recommend', { promotion_id }); }
async function apiCreateTask(promotion_id, produce_date, qty_units){
  return postJSON('/api/kancelaria/akcie/create_task', { promotion_id, produce_date, qty_units });
}

// z ERP – produkty (vyrobky). Môžeš vymeniť za iný endpoint s katalogom
async function apiErpProducts(){
  try{
    const r = await postJSON('/api/kancelaria/erp/recipes/products', {});
    return r?.products || [];
  }catch(_){ return []; }
}

/* ====== render ====== */
function renderChainsTable(items){
  const tb = $id('chain-tbody'); if (!tb) return;
  tb.innerHTML = '';
  items.forEach(c=>{
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${c.id}</td><td>${c.name}</td><td class="num">${(c.multiplier??1).toFixed(2)}</td><td>${c.created_at?.split('T')[0]||''}</td>`;
    tb.appendChild(tr);
  });
}

async function loadChainsIntoUI(){
  const data = await apiChainsList();
  const items = data?.chains || [];
  renderChainsTable(items);
  // select v akciách
  const sel = $id('promo-chain');
  if (sel) sel.innerHTML = items.map(c=>`<option value="${c.id}">${c.name}</option>`).join('');
}

async function loadProductsIntoUI(){
  const items = await apiErpProducts();
  const sel = $id('promo-product'); if (!sel) return;
  sel.innerHTML = items.map(p=>`<option value="${p.id}" data-unit="${p.production_unit===1?'ks':'kg'}" data-piece="${p.piece_weight_g||0}">${p.nazov}</option>`).join('');
}

function renderPromosTable(items, chainsLookup, productsLookup){
  const tb = $id('promo-tbody'); if (!tb) return;
  tb.innerHTML = '';
  items.forEach(p=>{
    const ch = chainsLookup.get(p.chain_id) || {name:'?'};
    const pr = productsLookup.get(p.product_id) || {nazov:`Produkt #${p.product_id}`};
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${p.id}</td>
      <td>${ch.name}</td>
      <td>${pr.nazov}</td>
      <td>${p.date_from}</td>
      <td>${p.date_to}</td>
      <td class="num">${Number(p.price_net).toFixed(2)}</td>
      <td class="right"><button class="btn" data-rec="${p.id}">Odporučiť výrobu</button></td>`;
    tr.querySelector('button[data-rec]').onclick = ()=> openRecommendation(p.id);
    tb.appendChild(tr);
  });
}

async function loadPromosIntoUI(){
  const [chains, products, promos] = await Promise.all([apiChainsList(), apiErpProducts(), apiPromosList(false)]);
  const chMap = new Map((chains?.chains||[]).map(c=>[c.id, c]));
  const prMap = new Map((products||[]).map(p=>[p.id, p]));
  renderPromosTable(promos?.items||[], chMap, prMap);
}

async function loadDashboardIntoUI(){
  const data = await apiDashboard();
  const ul = $id('dash-list'); if (!ul) return;
  ul.innerHTML = '';
  (data?.items||[]).forEach(x=>{
    const li = document.createElement('li');
    li.textContent = x.message;
    ul.appendChild(li);
  });
}

/* ====== recommendation panel ====== */
function renderRecommendation(res){
  const box = $id('akcie-recommend'); if (!box) return;
  if (!res?.ok){ box.style.display=''; box.innerHTML = `<p class="muted">Nepodarilo sa vypočítať odporúčanie.</p>`; return; }

  const meta = res.product || {};
  const rec  = res.recommendation || {};
  const pe   = res.profit_estimate || {};
  const mats = res.materials || [];

  box.style.display = '';
  box.innerHTML = `
    <h3>Odporúčanie výroby</h3>
    <div class="grid" style="display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:.5rem;">
      <div class="card">
        <div class="muted">Začať výrobu</div>
        <div><strong>${rec.production_start||'-'}</strong></div>
      </div>
      <div class="card">
        <div class="muted">Odporúčané množstvo</div>
        <div><strong>${rec.qty_units ?? '-'} ${rec.qty_units_label||''}</strong></div>
      </div>
      <div class="card">
        <div class="muted">Finálne množstvo (kg)</div>
        <div><strong>${rec.final_kg ?? '-'}</strong></div>
      </div>
    </div>

    <div class="card mt">
      <h4>Zadať do výroby</h4>
      <div class="row gap wrap">
        <label>Dátum výroby
          <input type="date" id="rec-prod-date" value="${rec.production_start||''}">
        </label>
        <label>Množstvo
          <input type="number" id="rec-qty" step="0.01" min="0" value="${(rec.qty_units ?? '')}">
        </label>
        <span class="muted">${meta.unit === 'ks' ? 'ks' : 'kg'}</span>
        <button id="rec-create-task" class="btn btn-primary">Zadať do výroby</button>
      </div>
      <p id="rec-msg" class="muted"></p>
    </div>

    <h4 class="mt">Materiály</h4>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Názov</th><th class="num">Potrebné (kg)</th><th class="num">Sklad (kg)</th><th class="num">Dokúpiť (kg)</th></tr></thead>
        <tbody>
          ${mats.map(m=>`<tr><td>${m.nazov}</td><td class="num">${Number(m.need_kg).toFixed(3)}</td><td class="num">${Number(m.stock_kg).toFixed(3)}</td><td class="num">${Number(m.buy_kg).toFixed(3)}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>

    <h4 class="mt">Odhad zisku</h4>
    <p class="muted">${pe.note || ''}</p>
    <div class="grid" style="display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:.5rem;">
      <div class="card"><div class="muted">Tržba</div><div><strong>${pe.revenue != null ? pe.revenue.toFixed(2) + ' €' : '-'}</strong></div></div>
      <div class="card"><div class="muted">Náklady</div><div><strong>${pe.cost != null ? pe.cost.toFixed(2) + ' €' : '-'}</strong></div></div>
      <div class="card"><div class="muted">Zisk</div><div><strong>${pe.profit != null ? pe.profit.toFixed(2) + ' €' : '-'}</strong></div></div>
    </div>
  `;

  // zapoj tlačidlo „Zadať do výroby“
  $id('rec-create-task')?.addEventListener('click', async ()=>{
    const msg = $id('rec-msg'); if (msg) msg.textContent = '';
    const produce_date = $id('rec-prod-date')?.value || '';
    const qty = Number($id('rec-qty')?.value || 0);
    if (!produce_date || qty <= 0){
      msg && (msg.textContent = 'Zadaj dátum aj množstvo > 0.');
      return;
    }
    try{
      const r = await apiCreateTask(res.promotion.id || res.promotion_id || 0, produce_date, qty);
      msg && (msg.textContent = r?.ok ? '✅ Zadané do výroby.' : ('❌ ' + (r?.error || 'Chyba')));
    }catch(e){
      msg && (msg.textContent = '❌ ' + e.message);
    }
  });
}


async function openRecommendation(promotion_id){
  const res = await apiRecommend(promotion_id);
  renderRecommendation(res);
}

/* ====== wiring ====== */
let __wired = false;
function wireAkcieOnce(){
  if (__wired) return; __wired = true;

  // tabs
  document.addEventListener('click', (e)=>{
    const tabs = [
      {btn:'#akcie-tab-chains',    panel:'#akcie-panel-chains'},
      {btn:'#akcie-tab-actions',   panel:'#akcie-panel-actions'},
      {btn:'#akcie-tab-dashboard', panel:'#akcie-panel-dashboard'},
    ];
    for (const t of tabs){
      if (e.target?.matches(t.btn)){
        tabs.forEach(x=>{
          $id(x.btn.replace('#',''))?.classList.remove('active');
          const p = $id(x.panel.replace('#','')); if (p) p.style.display = 'none';
        });
        e.target.classList.add('active');
        const p = $id(t.panel.replace('#','')); if (p) p.style.display = '';

        if (t.panel==='#akcie-panel-chains') loadChainsIntoUI();
        if (t.panel==='#akcie-panel-actions') { loadChainsIntoUI(); loadProductsIntoUI(); loadPromosIntoUI(); }
        if (t.panel==='#akcie-panel-dashboard') loadDashboardIntoUI();
      }
    }
  });

  // reťazec
  on($id('chain-add'),'click', async ()=>{
    const name = ($id('chain-name')?.value || '').trim();
    const mult = Number($id('chain-mult')?.value || 1);
    const msg  = $id('chain-msg'); if (msg) msg.textContent = '';
    if (!name){ msg.textContent = 'Zadaj názov reťazca.'; return; }
    try{
      const r = await apiChainsAdd(name, mult);
      msg.textContent = r?.ok ? '✅ Uložené.' : ('❌ ' + (r?.error || 'Chyba'));
      await loadChainsIntoUI();
      $id('chain-name').value = '';
      $id('chain-mult').value = '1.0';
    }catch(e){ msg.textContent = '❌ ' + e.message; }
  });

  // akcia
  on($id('promo-add'),'click', async ()=>{
    const payload = {
      chain_id: Number($id('promo-chain')?.value || 0),
      product_id: Number($id('promo-product')?.value || 0),
      price_net: Number($id('promo-price')?.value || 0),
      date_from: $id('promo-from')?.value,
      date_to: $id('promo-to')?.value,
      note: $id('promo-note')?.value || ''
    };
    const msg = $id('promo-msg'); if (msg) msg.textContent='';
    if (!payload.chain_id || !payload.product_id || !payload.price_net || !payload.date_from || !payload.date_to){
      msg.textContent = 'Vyplň všetky povinné polia.'; return;
    }
    try{
      const r = await apiPromosAdd(payload);
      msg.textContent = r?.ok ? '✅ Akcia uložená.' : ('❌ ' + (r?.error || 'Chyba'));
      await loadPromosIntoUI();
    }catch(e){ msg.textContent = '❌ ' + e.message; }
  });
}

/* ====== public init ====== */
window.initializeAkcieModule = function(){
  if (window.__akcieInited) return;
  window.__akcieInited = true;

  const root = $id('section-akcie');
  if (!root){
    console.warn('[Akcie] Sekcia #section-akcie nie je v DOM.');
    return;
  }
  ensureAkcieDom();
  wireAkcieOnce();

  // default tabuľka
  $id('akcie-tab-chains')?.click();
};
