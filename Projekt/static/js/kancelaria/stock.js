// /static/js/kancelaria/stock.js  (v21)
// SINGLE-PANE: všetko sa otvára uprostred stránky (jeden panel naraz).
// ESM modul, ale exportujeme window.initializeStockModule pre kancelaria.js.

import { postJSON, getJSON } from '/static/js/api_with_csrf.js?v=4';
// SAFE STUBS – nech to nikdy nepadne pri načítaní modulu
window.openDeliveryNotesPane   = window.openDeliveryNotesPane   || function(){};
window.openReceiveReportsPane  = window.openReceiveReportsPane  || function(){};

/* ----- DOM aliasy ----- */
const els = {
  section:     document.getElementById('section-stock'),
  // prehľad
  btnOverview: document.getElementById('stock-show-overview'),
  filters:     document.getElementById('stock-filters'),
  overview:    document.getElementById('stock-overview'),
  catSelect:   document.getElementById('stock-category'),
  refreshBtn:  document.getElementById('stock-refresh'),
  tbody:       document.getElementById('stock-tbody'),
  total:       document.getElementById('stock-total'),
  // toolbar
  btnRecMeat:        document.getElementById('stock-open-receive-meat'),
  btnRecOther:       document.getElementById('stock-open-receive-other'),
  btnWriteoff:       document.getElementById('stock-open-writeoff'),
  btnReports:        document.getElementById('stock-open-reports'),
  btnAddMaterialTop: document.getElementById('stock-open-add-material'),
  btnDeliveryNotes:  document.getElementById('open-delivery-notes'),
  btnRecipes:        document.getElementById('stock-open-recipes'),
};

const state = {
  pane: null,
  mode: null,           // 'receive-meat' | 'receive-other' | 'writeoff'
  products: [],
  suppliers: [],
  supplierId: null,
  supplierName: null,
  priceTpl: new Map(),
};

/* ----- utils ----- */
const $id = (x)=> document.getElementById(x);
const $  = (sel, r=document) => r.querySelector(sel);
const esc = s => (s==null?'':String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])));

/* ===== SINGLE-PANE KONTROLA ===== */
function findAddMaterialCard(){
  return document.getElementById('panel-add-material');
}
function closeAllPanels(){
  const addCard = findAddMaterialCard();
  if (addCard) addCard.classList.add('hidden');
  document.getElementById('stock-pane')?.remove();
  state.pane = null;
}
function ensurePane(){
  let pane = document.getElementById('stock-pane');
  if (!pane) {
    pane = document.createElement('div');
    pane.id = 'stock-pane';
    pane.className = 'card stock-pane';
    els.section?.appendChild(pane);
  }
  state.pane = pane;
  return pane;
}
function hideOverview(){
  els.filters?.classList.add('hidden');
  els.overview?.classList.add('hidden');
}
function showOverview(){
  closeAllPanels();
  els.filters?.classList.remove('hidden');
  els.overview?.classList.remove('hidden');
}
function paneHeader(title){
  return `
    <div class="row" style="gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:6px">
      <h2 style="margin:0">${esc(title)}</h2>
      <div style="flex:1"></div>
      <button id="pane-back" class="btn" type="button">Späť na prehľad</button>
    </div>
  `;
}

/* ===== Datasource ===== */
async function listMeatProducts()  { const d = await postJSON('/api/kancelaria/raw/products/meat',  {}); return d.items || []; }
async function listOtherProducts() { const d = await postJSON('/api/kancelaria/raw/products/other', {}); return d.items || []; }
async function listSuppliers()     { const d = await postJSON('/api/kancelaria/erp/suppliers/list', {}); return d.suppliers || []; }

async function loadCategories(){
  const data = await getJSON('/api/kancelaria/raw/getCategories');
  if(!els.catSelect) return;
  els.catSelect.innerHTML = '<option value="">— všetky —</option>';
  (data.categories||[]).forEach(c=>{
    const o = document.createElement('option');
    o.value = c.id; o.textContent = c.nazov;
    els.catSelect.appendChild(o);
  });
}
async function refreshOverview(){
  const data = await postJSON('/api/kancelaria/raw/list', { warehouse_id: 1, category_id: els.catSelect?.value ? Number(els.catSelect.value) : null });
  if (els.tbody) els.tbody.innerHTML = '';
  (data.items||[]).forEach(r=>{
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${r.sklad??''}</td>
      <td>${r.ean??''}</td>
      <td>${r.product??''}</td>
      <td>${r.category??''}</td>
      <td class="num">${Number(r.qty??0).toFixed(3)}</td>
      <td class="num">${Number(r.avg_cost??0).toFixed(4)}</td>
      <td class="num">${Number(r.stock_value??0).toFixed(2)}</td>`;
    els.tbody?.appendChild(tr);
  });
  els.total && (els.total.textContent = Number(data.total_value??0).toFixed(2));
  window.normalizeNumericTables?.(els.section || document);
}

/* ===== Šablóny cien ===== */
async function loadPriceTemplateForSupplier(supplierName, scope){
  state.priceTpl.clear();
  if (!supplierName) return;
  const rep = await postJSON('/api/kancelaria/reports/receipts/summary', { period: 'month', category_scope: (scope||'all') });
  (rep.items||[])
    .filter(it => (it.supplier||'').trim().toLowerCase() === supplierName.trim().toLowerCase())
    .forEach(it => state.priceTpl.set((it.product||'').trim(), Number(it.avg_price||0)));
}
function tplPriceByName(name){ return name && state.priceTpl.has(name) ? state.priceTpl.get(name) : null; }
function lastPrice(pid){ const v = localStorage.getItem(`lastPrice:${pid}`); return v ? Number(v) : null; }
function lastPriceByName(name){ const v = name ? localStorage.getItem(`lastPriceByName:${name.trim().toLowerCase()}`) : null; return v ? Number(v) : null; }

/* ===== PRÍJEM ===== */
function setMsg(id, txt){ const el = document.getElementById(id); if (el) el.textContent = txt || ''; }

function recalcReceiveTotals(){
  let tKg=0, tEur=0;
  state.pane?.querySelectorAll('#rcv-items tr').forEach(tr=>{
    const q = Number(tr.querySelector('.rcv-qty')?.value || 0);
    const p = Number(tr.querySelector('.rcv-price')?.value || 0);
    tKg += q; tEur += q*p;
    const c = tr.querySelector('.rcv-sum'); if (c) c.textContent = (q*p).toFixed(2);
  });
  const elQty = document.getElementById('rcv-total-qty'); if (elQty) elQty.textContent = tKg.toFixed(3);
  const elSum = document.getElementById('rcv-total-sum'); if (elSum) elSum.textContent = tEur.toFixed(2);
  window.normalizeNumericTables?.(state.pane || document);
}

function addReceiveRow(presetId=null, presetPrice=null){
  const tb = state.pane?.querySelector('#rcv-items'); if (!tb) return null;
  const opts = state.products.map(p=>`<option value="${p.id}" data-name="${esc(p.nazov)}">${esc(p.nazov)}</option>`).join('');
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td style="min-width:320px"><select class="rcv-prod">${opts}</select></td>
    <td class="num"><input class="rcv-qty" type="number" step="0.001" min="0" value="0.000" style="max-width:130px"></td>
    <td class="num"><input class="rcv-price" type="number" step="0.0001" min="0" value="0.0000" style="max-width:130px"></td>
    <td class="num rcv-sum">0.00</td>
    <td class="num"><button class="btn btn-danger rcv-del" type="button">Odstrániť</button></td>`;
  tb.appendChild(tr);

  const prodSel  = tr.querySelector('.rcv-prod');
  const priceInp = tr.querySelector('.rcv-price');
  const qtyInp   = tr.querySelector('.rcv-qty');

  if (presetId) prodSel.value = String(presetId);

  const applyPrice = ()=>{
    if (Number(priceInp.value||0) === 0) {
      const pid = Number(prodSel.value||0);
      const nm  = prodSel.selectedOptions?.[0]?.getAttribute('data-name') || prodSel.selectedOptions?.[0]?.textContent || '';
      const tpl = tplPriceByName((nm||'').trim());
      const lp  = lastPrice(pid);
      const lpn = lastPriceByName(nm);
      const fill = (presetPrice!=null ? presetPrice : (tpl ?? lp ?? lpn));
      if (fill != null) priceInp.value = Number(fill).toFixed(4);
    }
    recalcReceiveTotals();
  };

  prodSel.addEventListener('change', applyPrice);
  qtyInp.addEventListener('input', recalcReceiveTotals);
  priceInp.addEventListener('input', recalcReceiveTotals);
  tr.querySelector('.rcv-del')?.addEventListener('click', ()=>{ tr.remove(); recalcReceiveTotals(); });

  applyPrice();
  return tr;
}

function wireSupplierBehavior(){
  const lockMsg = state.pane?.querySelector('#rcv-lock-msg');
  if (state.mode==='receive-meat'){
    const sel = state.pane?.querySelector('#rcv-supplier-text');
    const extra = state.pane?.querySelector('#rcv-supplier-extra');
    if (!sel || !extra) return;
    const updateTpl = async ()=>{
      state.supplierName = (sel.value==='Iné') ? ((extra.value||'').trim() || 'Iné') : sel.value;
      if (lockMsg) lockMsg.textContent = state.supplierName ? `🔒 Dodávateľ: ${state.supplierName}` : '— Dodávateľ nie je zvolený —';
      await loadPriceTemplateForSupplier(state.supplierName, 'meat');
      state.pane?.querySelectorAll('#rcv-items tr').forEach(tr=>{
        const priceInp = tr.querySelector('.rcv-price');
        if (Number(priceInp?.value||0) === 0) {
          const nm = tr.querySelector('.rcv-prod')?.selectedOptions?.[0]?.textContent?.trim() || '';
          const tpl = tplPriceByName(nm);
          if (tpl != null) priceInp.value = Number(tpl).toFixed(4);
        }
      });
      recalcReceiveTotals();
    };
    sel.addEventListener('change', ()=>{
      if (sel.value==='Iné'){ extra.style.display=''; extra.focus(); }
      else { extra.style.display='none'; extra.value=''; }
      updateTpl();
    });
    extra.addEventListener('input', ()=>{ if (sel.value==='Iné') updateTpl(); });
  } else {
    const sel = state.pane?.querySelector('#rcv-supplier-id');
    if (!sel) return;
    sel.addEventListener('change', async ()=>{
      state.supplierId   = Number(sel.value||0) || null;
      state.supplierName = (state.suppliers||[]).find(s=>s.id===state.supplierId)?.name || '';
      if (lockMsg) lockMsg.textContent = state.supplierId ? `🔒 Dodávateľ: ${state.supplierName}` : '— Dodávateľ nie je zvolený —';
      await loadPriceTemplateForSupplier(state.supplierName, 'other');
      state.pane?.querySelectorAll('#rcv-items tr').forEach(tr=>{
        const priceInp = tr.querySelector('.rcv-price');
        if (Number(priceInp?.value||0) === 0) {
          const nm = tr.querySelector('.rcv-prod')?.selectedOptions?.[0]?.textContent?.trim() || '';
          const tpl = tplPriceByName(nm);
          if (tpl != null) priceInp.value = Number(tpl).toFixed(4);
        }
      });
      recalcReceiveTotals();
    });
  }
}

function wireAddSupplierInline(){
  const btn = state.pane?.querySelector('#rcv-add-supplier');
  const sel = state.pane?.querySelector('#rcv-supplier-id');
  const msgId = 'rcv-msg';
  if (!btn || !sel) return;

  btn.addEventListener('click', async () => {
    const name = prompt('Názov dodávateľa:');
    if (!name) return;

    try {
      const resp = await postJSON('/api/kancelaria/erp/suppliers/add', { name: name.trim() });
      if (!resp || !resp.ok || !resp.supplier?.id) {
        setMsg(msgId, '❌ Nepodarilo sa pridať dodávateľa.');
        return;
      }
      state.suppliers = await listSuppliers();
      const exists = Array.from(sel.options).some(o => Number(o.value) === Number(resp.supplier.id));
      if (!exists) {
        const opt = document.createElement('option');
        opt.value = resp.supplier.id;
        opt.textContent = resp.supplier.name;
        sel.appendChild(opt);
      }
      sel.value = String(resp.supplier.id);
      sel.dispatchEvent(new Event('change'));
      setMsg(msgId, '✅ Dodávateľ pridaný.');
    } catch (err) {
      setMsg(msgId, '❌ ' + (err?.message || 'Chyba pri vytváraní dodávateľa.'));
    }
  });
}

/* ===== OPEN PANES ===== */
async function openReceivePane(kind){
  state.mode = (kind==='other') ? 'receive-other' : 'receive-meat';
  closeAllPanels(); hideOverview(); ensurePane();

  state.products  = (state.mode==='receive-meat') ? (await listMeatProducts()) : (await listOtherProducts());
  state.suppliers = (state.mode==='receive-other') ? (await listSuppliers()) : [];

  const supplierBlock = (state.mode==='receive-meat')
    ? `
      <label style="min-width:260px">Dodávateľ
        <select id="rcv-supplier-text">
          <option value="">— vyber —</option>
          <option>Rozrábka</option><option>Expedícia</option>
          <option>Externý dodávateľ</option><option>Iné</option>
        </select>
      </label>
      <input id="rcv-supplier-extra" placeholder="Ak Iné – napíš názov" style="display:none;max-width:320px">
    `
    : `
      <label style="min-width:260px">Dodávateľ
        <select id="rcv-supplier-id">
          <option value="">— vyber —</option>
          ${(state.suppliers||[]).map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('')}
        </select>
      </label>
      <button id="rcv-add-supplier" class="btn" type="button">+ Pridať dodávateľa</button>
    `;

  state.pane.innerHTML = `
    ${paneHeader(state.mode==='receive-meat' ? 'Príjem do výrobného skladu — Mäso' : 'Príjem do výrobného skladu — Koreniny / Obaly / Pomocný materiál')}
    <div class="row" style="gap:12px;align-items:flex-end;flex-wrap:wrap">
      ${supplierBlock}
      <span id="rcv-lock-msg" class="muted" style="margin-left:8px">— Dodávateľ nie je zvolený —</span>
      <div style="flex:1"></div>
      <button id="open-add-material" type="button" class="btn">+ Nová surovina (výroba)</button>
    </div>

    <div class="table-wrap" style="margin-top:10px">
      <table class="table">
        <colgroup><col class="col-name"><col class="col-qty"><col class="col-price"><col class="col-value"><col></colgroup>
        <thead>
          <tr><th>Produkt</th><th class="num">Množstvo (kg)</th><th class="num">Cena/kg (€)</th><th class="num">Spolu (€)</th><th class="num">—</th></tr>
        </thead>
        <tbody id="rcv-items"></tbody>
        <tfoot>
          <tr><td colspan="5">
            <div class="row" style="gap:10px;align-items:center;flex-wrap:wrap">
              <button id="rcv-add-row" class="btn" type="button">+ Pridať riadok</button>
              <span class="muted">1 dodávateľ = 1 doklad</span>
              <div style="flex:1"></div>
              <strong>Σ kg: <span id="rcv-total-qty">0.000</span></strong>
              <strong>Σ €: <span id="rcv-total-sum">0.00</span></strong>
            </div>
          </td></tr>
        </tfoot>
      </table>
    </div>

    <div class="row" style="gap:10px;justify-content:flex-end">
      <button id="rcv-cancel" class="btn" type="button">Zrušiť</button>
      <button id="rcv-submit" class="btn btn-primary" type="button">Prijať všetko</button>
    </div>
    <p id="rcv-msg" class="muted" style="margin-top:.25rem"></p>
  `;

  $('#pane-back')?.addEventListener('click', showOverview);
  $('#rcv-cancel')?.addEventListener('click', showOverview);
  $('#rcv-add-row')?.addEventListener('click', ()=> addReceiveRow());
  $('#open-add-material')?.addEventListener('click', showStaticAddMaterial);

  wireSupplierBehavior();
  if (state.mode==='receive-other') wireAddSupplierInline();

  addReceiveRow();

  $('#rcv-submit')?.addEventListener('click', async ()=>{
    setMsg('rcv-msg','');
    if (state.mode==='receive-meat'){
      if (!state.supplierName){ setMsg('rcv-msg','❌ Vyber dodávateľa (text).'); return; }
    } else {
      if (!state.supplierId){ setMsg('rcv-msg','❌ Vyber dodávateľa (zo zoznamu).'); return; }
    }
    const items = [];
    state.pane?.querySelectorAll('#rcv-items tr').forEach(tr=>{
      const pid   = Number(tr.querySelector('.rcv-prod')?.value || 0);
      const qty   = tr.querySelector('.rcv-qty')?.value || '0';
      const price = tr.querySelector('.rcv-price')?.value || '0';
      if (pid && Number(qty) > 0){ items.push({ product_id: pid, qty, unit_cost: price }); }
    });
    if (!items.length){ setMsg('rcv-msg','❌ Pridaj aspoň jednu položku > 0.'); return; }

    try{
      let resp;
      if (state.mode==='receive-meat'){
        const pack = items.map(i => ({ ...i, supplier_text: state.supplierName }));
        resp = await postJSON('/api/kancelaria/stock/receive/meat', { items: pack });
      } else {
        resp = await postJSON('/api/kancelaria/stock/receive/other', { supplier_id: state.supplierId, items });
      }
      items.forEach(i => localStorage.setItem(`lastPrice:${i.product_id}`, String(i.unit_cost||0)));
      if (resp && (resp.ok || resp.count>=0)){
        setMsg('rcv-msg', `✅ Prijaté položky: ${resp.count || items.length}`);
        setTimeout(async ()=>{ showOverview(); await refreshOverview(); }, 350);
      } else { setMsg('rcv-msg','❌ ' + (resp?.error||'Chyba príjmu.')); }
    }catch(e){ setMsg('rcv-msg','❌ ' + e.message); }
  });
}

async function openWriteoffPane(){
  state.mode = 'writeoff';
  closeAllPanels(); hideOverview(); ensurePane();

  const list = await postJSON('/api/kancelaria/raw/list', { warehouse_id: 1, category_id: null });
  const seen = new Set(); const items = [];
  (list.items || []).forEach(r => { const key = (r.product || '').trim(); if (key && !seen.has(key)) { seen.add(key); items.push({ id: r.product_id, name: r.product }); } });
  const opts = items.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('');

  state.pane.innerHTML = `
    ${paneHeader('Odpis zo skladu (výroba)')}
    <div class="card muted-border" style="padding:10px">
      <div class="row wrap" style="gap:12px;align-items:flex-end">
        <label style="min-width:260px">Produkt<select id="wo-product">${opts}</select></label>
        <label>Množstvo (kg)<input id="wo-qty" type="number" step="0.001" min="0"/></label>
        <label>Kód dôvodu<input id="wo-code" type="number" step="1" value="1"/></label>
        <label style="flex:1">Poznámka<input id="wo-text"/></label>
        <button id="wo-submit" class="btn btn-danger-outline" type="button">Odpísať</button>
      </div>
      <p id="wo-msg" class="muted" style="margin-top:.25rem"></p>
    </div>`;
  $('#pane-back')?.addEventListener('click', showOverview);
  $('#wo-submit')?.addEventListener('click', async ()=>{
    setMsg('wo-msg','');
    const payload = {
      warehouse_id: 1,
      product     : $('#wo-product')?.value,
      qty         : $('#wo-qty')?.value,
      reason_code : Number($('#wo-code')?.value||1),
      reason_text : ($('#wo-text')?.value||'').trim() || null,
      actor_user_id: 1
    };
    if (!payload.product || Number(payload.qty)<=0){ setMsg('wo-msg','❌ Vyber produkt a zadaj množstvo > 0.'); return; }
    try{
      const resp = await postJSON('/api/kancelaria/raw/writeoff', payload);
      setMsg('wo-msg', resp.ok ? '✅ Odpísané' : (resp.error || 'Chyba'));
      await refreshOverview();
    }catch(err){ setMsg('wo-msg','❌ ' + err.message); }
  });
}

/* ===== Statická „Nová surovina“ ===== */
function showStaticAddMaterial(){
  closeAllPanels(); hideOverview();
  const mat = document.getElementById('panel-add-material');
  if (!mat) return;

  // premenovať DPH na CENA (len UI)
  const vatLabel = mat.querySelector('label:nth-of-type(3)');
  if (vatLabel && vatLabel.textContent.includes('DPH')) {
    vatLabel.childNodes[0].textContent = 'Cena (€/kg) ';
  }

  mat.classList.remove('hidden');
  mat.scrollIntoView({ behavior:'smooth', block:'start' });

  const btn = document.getElementById('mat-save');
  if (btn && !btn._bound) {
    btn._bound = true;
    btn.addEventListener('click', async (e)=>{
      e.preventDefault();
      const name = document.getElementById('mat-name')?.value.trim();
      const type = document.getElementById('mat-type')?.value || '';
      const min  = document.getElementById('mat-min')?.value || '0';
      const price= document.getElementById('mat-vat')?.value || '0'; // pole DPH používame ako cenu
      const msg  = document.getElementById('mat-msg'); if (msg) msg.textContent='';

      if (!name){ msg && (msg.textContent='❌ Zadaj názov.'); return; }
      try{
        const cats = await getJSON('/api/kancelaria/raw/getCategories');
        const all  = cats.categories || [];
        const found= all.find(c => (c.nazov||'').trim().toLowerCase() === (type||'').trim().toLowerCase());
        const category_id = found ? Number(found.id) : (all[0]?.id || null);
        const resp = await postJSON('/api/kancelaria/raw/addMaterialProduct', {
          name, ean: null, category_id, min_stock: min, dph: '20.00'
        });
        if (resp && resp.ok){
          const p = Number(price)||0;
          if (p > 0) localStorage.setItem(`lastPriceByName:${name.trim().toLowerCase()}`, String(p));
          msg && (msg.textContent='✅ Surovina uložená.');
        } else {
          msg && (msg.textContent='❌ ' + (resp?.error||'Chyba ukladania.'));
        }
      }catch(err){ msg && (msg.textContent='❌ ' + err.message); }
    });
  }
}

/* ===== Recepty – presmerovanie na existujúci link v menu ===== */
// Otvor "Recepty" v rámci aktuálnej stránky (bez reloadu / nového tabu)
function goToRecipes(){
  // aktivuj sekciu ERP (bez reloadu)
  const link = document.querySelector('.nav .nav-link[data-section="erp"], .sidebar .nav-link[data-section="erp"]');
  if (link) link.click(); else { if (location.hash !== '#erp') location.hash = '#erp'; }

  // počkaj na tlačidlo "Recepty" a klikni
  const waitFor = (sel, tries=30, interval=120) => new Promise((res,rej)=>{
    let t=0; const iv=setInterval(()=>{ const el=document.querySelector(sel);
      if(el){clearInterval(iv);res(el);} else if(++t>=tries){clearInterval(iv);rej();}},interval);
  });
  waitFor('#erp-tab-recipes').then(btn=>{
    btn.click();
    const panel = document.getElementById('erp-panel-recipes');
    if (panel) panel.scrollIntoView({behavior:'smooth',block:'start'});
  }).catch(()=>{
    // fallback: ukáž panel priamo
    const panel = document.getElementById('erp-panel-recipes');
    if (panel){
      ['#erp-panel-overview','#erp-panel-addcat','#erp-panel-addprod'].forEach(sel=>{
        const el = document.querySelector(sel); if (el) el.style.display='none';
      });
      panel.style.display='';
      panel.scrollIntoView({behavior:'smooth',block:'start'});
    } else {
      alert('Recepty som nenašiel. Skontroluj #erp-tab-recipes a #erp-panel-recipes.');
    }
  });
}

/* ===== Delivery notes & Reporty – vlastný panel ===== */
window.openDeliveryNotesPane = function(){
  closeAllPanels(); hideOverview(); ensurePane();

  const today = new Date();
  const iso = (d)=> d.toISOString().slice(0,10);
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

  state.pane.innerHTML = `
    ${paneHeader('Dodacie listy')}
    <div class="card" style="padding:10px">
      <div class="toolbar">
        <label>Od <input id="dl-from" type="date" value="${iso(firstDay)}"></label>
        <label>Do <input id="dl-to" type="date" value="${iso(today)}"></label>
        <button id="dl-run" class="btn btn-primary">Filtrovať</button>
      </div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Dodávateľ</th><th>Dátum</th><th class="num">Položky</th><th class="num">Σ kg</th><th class="num">Σ €</th><th>Akcie</th></tr></thead>
          <tbody id="dl-tbody"></tbody>
        </table>
      </div>
      <div id="dl-detail" class="mt"></div>
    </div>
  `;

  const fmt = (v,n=3)=> (Number(v||0)).toFixed(n).replace('.', ',');
  const toIso = (v)=> {
    const d = new Date(v);
    if (!isNaN(d)) return d.toISOString().slice(0,10);
    const s = String(v||''); const m = s.match(/^(\d{4}-\d{2}-\d{2})/);
    return m ? m[1] : s.slice(0,10);
  };

  async function run(){
    const qs = new URLSearchParams({
      from: $id('dl-from').value,
      to:   $id('dl-to').value
    });
    const res = await fetch('/api/kancelaria/receive/delivery-notes?'+qs);
    if (!res.ok) { alert('Chyba dodacích listov: ' + await res.text()); return; }
    const rows = await res.json();
    const tb = $id('dl-tbody'); tb.innerHTML = '';
    for (const r of (rows||[])){
      const dayIso = toIso(r.day);
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${r.supplier||''}</td>
        <td>${dayIso}</td>
        <td class="num">${r.items||0}</td>
        <td class="num">${fmt(r.total_qty,3)}</td>
        <td class="num">${fmt(r.total_value,2)}</td>
        <td>
          <button class="btn btn-sm dl-show" data-sup="${encodeURIComponent(r.supplier||'')}" data-day="${dayIso}">Detaily</button>
          <a class="btn btn-sm" target="_blank" href="/api/kancelaria/receive/delivery-note/pdf?supplier=${encodeURIComponent(r.supplier||'')}&day=${dayIso}">PDF</a>
        </td>`;
      tb.appendChild(tr);
    }
    window.normalizeNumericTables?.(state.pane || document);
  }

  async function showDetail(supplier, dayIso){
    const qs = new URLSearchParams({ supplier, day: dayIso });
    const res = await fetch('/api/kancelaria/receive/delivery-note/detail?'+qs);
    if (!res.ok) { alert('Chyba detailu DL: ' + await res.text()); return; }
    const data = await res.json();
    const el = $id('dl-detail');
    const rows = data.items || [];
    const body = rows.map(it => `
      <tr>
        <td>${it.produkt||''}</td>
        <td class="num">${fmt(it.mnozstvo,3)}</td>
        <td class="num">${fmt(it.cena,4)}</td>
        <td class="num">${fmt((it.mnozstvo||0)*(it.cena||0),2)}</td>
      </tr>`).join('');
    const total = rows.reduce((s,it)=> s + Number((it.mnozstvo||0)*(it.cena||0)), 0);
    el.innerHTML = `
      <div class="card">
        <div class="row wrap" style="justify-content:space-between">
          <h3 style="margin:0">Dodací list — ${supplier} (${dayIso})</h3>
          <a class="btn" target="_blank" href="/api/kancelaria/receive/delivery-note/pdf?supplier=${encodeURIComponent(supplier)}&day=${dayIso}">Tlačiť PDF</a>
        </div>
        <div class="table-wrap mt">
          <table class="table">
            <thead><tr><th>Produkt</th><th class="num">Množstvo (kg)</th><th class="num">Cena/kg (€)</th><th class="num">Spolu (€)</th></tr></thead>
            <tbody>${body}</tbody>
            <tfoot><tr><td colspan="3" class="num"><strong>Spolu</strong></td><td class="num"><strong>${fmt(total,2)}</strong></td></tr></tfoot>
          </table>
        </div>
      </div>`;
    window.normalizeNumericTables?.(state.pane || document);
  }

  $id('dl-run')?.addEventListener('click', run);
  state.pane.addEventListener('click', (e)=>{
    const btn = e.target.closest?.('.dl-show'); if (!btn) return;
    showDetail(decodeURIComponent(btn.dataset.sup||''), btn.dataset.day);
  });

  run().catch(err => alert('Chyba dodacích listov: ' + err.message));
};


window.openReceiveReportsPane = function(){
  closeAllPanels(); hideOverview(); ensurePane();

  const today = new Date();
  const iso = (d)=> d.toISOString().slice(0,10);
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

  state.pane.innerHTML = `
    ${paneHeader('Reporty príjmu')}
    <div class="card" style="padding:10px">
      <div class="toolbar">
        <label>Od <input id="rep-from" type="date" value="${iso(firstDay)}"></label>
        <label>Do <input id="rep-to" type="date" value="${iso(today)}"></label>
        <label>Dodávateľ <input id="rep-supplier" placeholder="(všetci)"></label>
        <label>Zoskupiť podľa
          <select id="rep-group">
            <option value="supplier">Dodávateľ</option>
            <option value="day">Deň</option>
            <option value="product">Produkt</option>
            <option value="supplier_day">Dodávateľ + Deň</option>
          </select>
        </label>
        <button id="rep-run" class="btn btn-primary">Načítať</button>
        <button id="rep-pdf" class="btn">PDF</button>
      </div>
      <div class="table-wrap">
        <table class="table" id="rep-table">
          <thead id="rep-thead"></thead>
          <tbody id="rep-tbody"></tbody>
          <tfoot><tr><td id="rep-total-label"></td><td class="num" id="rep-total-qty"></td><td class="num" id="rep-total-avg"></td><td class="num" id="rep-total-sum"></td></tr></tfoot>
        </table>
      </div>
    </div>
  `;

  const fmt = (v,n=3)=> (Number(v||0)).toFixed(n).replace('.', ',');

  function drawHead(group){
    const thead = $id('rep-thead');
    if (group==='supplier'){
      thead.innerHTML = `<tr><th>Dodávateľ</th><th class="num">Σ kg</th><th class="num">∅ €/kg</th><th class="num">Σ €</th></tr>`;
    } else if (group==='day'){
      thead.innerHTML = `<tr><th>Dátum</th><th class="num">Σ kg</th><th class="num">∅ €/kg</th><th class="num">Σ €</th></tr>`;
    } else if (group==='product'){
      thead.innerHTML = `<tr><th>Produkt</th><th class="num">Σ kg</th><th class="num">∅ €/kg</th><th class="num">Σ €</th></tr>`;
    } else {
      thead.innerHTML = `<tr><th>Dodávateľ</th><th>Dátum</th><th class="num">Σ kg</th><th class="num">∅ €/kg</th><th class="num">Σ €</th></tr>`;
    }
  }

  async function run(){
    const payload = {
      date_from: $id('rep-from').value,
      date_to:   $id('rep-to').value,
      supplier:  ($id('rep-supplier').value.trim() || null),
      group_by:  $id('rep-group').value
    };
    drawHead(payload.group_by);
    const tb = $id('rep-tbody'); tb.innerHTML = '';
    const res = await postJSON('/api/kancelaria/reports/receipts', payload);
    const rows = res.items || [];
    for (const r of rows){
      const tr = document.createElement('tr');
      if (payload.group_by==='supplier'){
        tr.innerHTML = `<td>${r.supplier||''}</td><td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.avg_price,4)}</td><td class="num">${fmt(r.total_value,2)}</td>`;
      } else if (payload.group_by==='day'){
        tr.innerHTML = `<td>${r.day||''}</td><td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.avg_price,4)}</td><td class="num">${fmt(r.total_value,2)}</td>`;
      } else if (payload.group_by==='product'){
        tr.innerHTML = `<td>${r.product||''}</td><td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.avg_price,4)}</td><td class="num">${fmt(r.total_value,2)}</td>`;
      } else {
        tr.innerHTML = `<td>${r.supplier||''}</td><td>${r.day||''}</td><td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.avg_price,4)}</td><td class="num">${fmt(r.total_value,2)}</td>`;
      }
      tb.appendChild(tr);
    }
    $id('rep-total-label').textContent = 'Spolu';
    $id('rep-total-qty').textContent   = fmt(res.total_qty,3);
    $id('rep-total-avg').textContent   = '';
    $id('rep-total-sum').textContent   = fmt(res.total_value,2);
    window.normalizeNumericTables?.(state.pane || document);
  }

  async function pdf(){
    const payload = {
      date_from: $id('rep-from').value,
      date_to:   $id('rep-to').value,
      supplier:  ($id('rep-supplier').value.trim() || null),
      group_by:  $id('rep-group').value
    };
    const xsrf = document.cookie.split('; ').find(c=>c.startsWith('XSRF-TOKEN='))?.split('=')[1] || '';
    const res  = await fetch('/api/kancelaria/reports/receipts/pdf', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type':'application/json', 'X-CSRF-Token': xsrf },
      body: JSON.stringify(payload)
    });
    if (!res.ok) { alert(await res.text()); return; }
    const blob = await res.blob(); const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'report_prijmu.pdf';
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }

  $id('rep-run')?.addEventListener('click', run);
  $id('rep-pdf')?.addEventListener('click', pdf);

  run().catch(err => alert('Chyba reportu: ' + err.message));

  function drawHead(group){
    const thead = $id('rep-thead');
    if (group==='supplier'){
      thead.innerHTML = `<tr><th>Dodávateľ</th><th class="num">Σ kg</th><th class="num">∅ €/kg</th><th class="num">Σ €</th></tr>`;
    } else if (group==='day'){
      thead.innerHTML = `<tr><th>Dátum</th><th class="num">Σ kg</th><th class="num">∅ €/kg</th><th class="num">Σ €</th></tr>`;
    } else if (group==='product'){
      thead.innerHTML = `<tr><th>Produkt</th><th class="num">Σ kg</th><th class="num">∅ €/kg</th><th class="num">Σ €</th></tr>`;
    } else {
      thead.innerHTML = `<tr><th>Dodávateľ</th><th>Dátum</th><th class="num">Σ kg</th><th class="num">∅ €/kg</th><th class="num">Σ €</th></tr>`;
    }
  }

  async function run(){
    const payload = {
      date_from: $id('rep-from').value,
      date_to:   $id('rep-to').value,
      supplier:  $id('rep-supplier').value.trim() || null,
      group_by:  $id('rep-group').value
    };
    drawHead(payload.group_by);
    const tb = $id('rep-tbody'); tb.innerHTML = '';
    const res = await postJSON('/api/kancelaria/reports/receipts', payload);
    const rows = res.items || [];
    // vykresli
    for (const r of rows){
      const tr = document.createElement('tr');
      if (payload.group_by==='supplier'){
        tr.innerHTML = `<td>${r.supplier||''}</td><td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.avg_price,4)}</td><td class="num">${fmt(r.total_value,2)}</td>`;
      } else if (payload.group_by==='day'){
        tr.innerHTML = `<td>${r.day||''}</td><td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.avg_price,4)}</td><td class="num">${fmt(r.total_value,2)}</td>`;
      } else if (payload.group_by==='product'){
        tr.innerHTML = `<td>${r.product||''}</td><td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.avg_price,4)}</td><td class="num">${fmt(r.total_value,2)}</td>`;
      } else {
        tr.innerHTML = `<td>${r.supplier||''}</td><td>${r.day||''}</td><td class="num">${fmt(r.total_qty)}</td><td class="num">${fmt(r.avg_price,4)}</td><td class="num">${fmt(r.total_value,2)}</td>`;
      }
      tb.appendChild(tr);
    }
    // sumy
    $id('rep-total-label').textContent = 'Spolu';
    $id('rep-total-qty').textContent   = fmt(res.total_qty,3);
    $id('rep-total-avg').textContent   = ''; // ∅ celkom nemá zmysel
    $id('rep-total-sum').textContent   = fmt(res.total_value,2);
    window.normalizeNumericTables?.(state.pane || document);
  }

  async function pdf(){
    const payload = {
      date_from: $id('rep-from').value,
      date_to:   $id('rep-to').value,
      supplier:  $id('rep-supplier').value.trim() || null,
      group_by:  $id('rep-group').value
    };
    const xsrf = document.cookie.split('; ').find(c=>c.startsWith('XSRF-TOKEN='))?.split('=')[1] || '';
    const res  = await fetch('/api/kancelaria/reports/receipts/pdf', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type':'application/json', 'X-CSRF-Token': xsrf },
      body: JSON.stringify(payload)
    });
    if (!res.ok) { alert(await res.text()); return; }
    const blob = await res.blob(); const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'report_prijmu.pdf';
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }

  document.getElementById('rep-run')?.addEventListener('click', run);
  document.getElementById('rep-pdf')?.addEventListener('click', pdf);
  // auto run
  run().catch(err => alert('Chyba reportu: ' + err.message));
}

/* ===== WIRING (iba raz) ===== */
function wireToolbarOnce(){
  if (window.__stockWired) return;
  window.__stockWired = true;

  const on = (id, fn) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('click', (e) => { e.preventDefault(); fn(); });
  };

  on('stock-show-overview', async () => {
    showOverview();
    if(!els.catSelect?.options.length) await loadCategories();
    await refreshOverview();
  });

  on('stock-open-receive-meat',  () => openReceivePane('meat'));
  on('stock-open-receive-other', () => openReceivePane('other'));
  on('stock-open-add-material',  showStaticAddMaterial);
 on('stock-open-reports',       window.openReceiveReportsPane);
 on('open-delivery-notes',      window.openDeliveryNotesPane);
  on('stock-open-writeoff',      openWriteoffPane);
  on('stock-open-recipes',       goToRecipes);
}

/* ===== INIT (export na window) ===== */
function getStockDeepLink(){
  const raw = (location.hash || '').replace(/^#/, '');
  const m = raw.match(/^stock:([a-z\-]+)$/i);
  return m ? m[1].toLowerCase() : null;
}

window.initializeStockModule = async function(){
  if (window.__stockInited) return;
  window.__stockInited = true;

  wireToolbarOnce();

  // default skry všetko
  closeAllPanels();
  els.filters?.classList.add('hidden');
  els.overview?.classList.add('hidden');

  // podpora deeplinku (#stock:...)
  const pane = getStockDeepLink();
  if (pane) {
    switch (pane) {
      case 'receive-meat':   await openReceivePane('meat');   return;
      case 'receive-other':  await openReceivePane('other');  return;
      case 'writeoff':       await openWriteoffPane();        return;
      case 'reports':        window.openReceiveReportsPane();        return;
      case 'delivery-notes': window.openDeliveryNotesPane();         return;
      case 'add-material':   showStaticAddMaterial();         return;
    }
  }

  // default: prehľad
  showOverview();
  if(!els.catSelect?.options.length) await loadCategories();
  await refreshOverview();
};
