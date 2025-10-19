// static/js/kancelaria_modules/erp_admin.js
// Profi modul ERP: Centrálny katalóg + Recepty
// - Jednoduchý Recipe Builder (vyhľadávanie, rýchly import, bez duplicít)
// - Normy, Postup, QC, Tlač, Export/Import meta
// - Rýchle pridanie produktu (prehľadné)

import { postJSON } from '/static/js/api_with_csrf.js?v=4';
import { openModal, closeModal } from '/static/js/ui/modal.js';

/* ========== Helpers ========== */
const $   = (sel, r=document) => r.querySelector(sel);
const $$  = (sel, r=document) => Array.from(r.querySelectorAll(sel));
const on  = (el, ev, fn) => el && el.addEventListener(ev, fn);
const html = (el, h) => { if (el) el.innerHTML = h; };
const $id = (x)=> document.getElementById(x);
const fmt = (v,n=3)=> (v==null||v==='')?'':Number(v).toFixed(n).replace('.',',');

function showPanel(id) {
  ['erp-panel-overview','erp-panel-addcat','erp-panel-addprod','erp-panel-recipes']
    .forEach(pid => { const e = $id(pid); if (e) e.style.display = (pid===id?'':'none'); });
}

/* ========== Ensure DOM (ak sú panely prázdne v HTML) ========== */
function ensureOverviewDom(){
  const host = $id('erp-panel-overview'); if (!host || host.innerHTML.trim()) return;
  html(host, `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>EAN</th><th>Názov</th><th>DPH %</th>
            <th>Predajná kategória</th><th>Jednotka</th><th>Vyrábam?</th>
          </tr>
        </thead>
        <tbody id="erp-overview-tbody"></tbody>
      </table>
    </div>
  `);
}

function ensureAddCatDom(){
  const host = $id('erp-panel-addcat'); if (!host || host.innerHTML.trim()) return;
  html(host, `
    <h3>Pridať predajnú kategóriu</h3>
    <div class="row gap">
      <input id="erp-cat-name" placeholder="Názov kategórie" />
      <button id="erp-cat-save" class="btn btn-primary">Uložiť</button>
    </div>
    <p id="erp-cat-msg" class="muted mt"></p>
    <div id="erp-cat-list" class="mt"></div>
  `);
}

function ensureAddProdDom(){
  const host = $id('erp-panel-addprod'); if (!host || host.innerHTML.trim()) return;
  html(host, `
    <h3>Rýchle pridanie produktu</h3>
    <div class="card">
      <div class="form-grid form-3">
        <label>Názov produktu
          <input id="sp-name" placeholder="napr. Hydinové párky MIK">
        </label>

        <label>Jednotka
          <select id="sp-unit">
            <option value="kg">kg (vážené)</option>
            <option value="ks">ks (kusové)</option>
          </select>
        </label>

        <label id="sp-piece-wrap" style="display:none;">Hmotnosť 1 ks (g)
          <input id="sp-piece" type="number" step="1" min="1" value="200">
        </label>

        <label>Predajná kategória
          <select id="sp-sc"></select>
        </label>

        <label>DPH %
          <select id="sp-vat">
            <option value="5">5%</option><option value="10">10%</option>
            <option value="19">19%</option><option value="20" selected>20%</option>
            <option value="23">23%</option>
          </select>
        </label>

        <label>EAN (voliteľné)
          <input id="sp-ean" placeholder="napr. 858...">
        </label>

        <label class="col-span-2">
          <input type="checkbox" id="sp-isprod" checked> Je to výrobok (vyrábame ho)
        </label>
      </div>

      <div class="row right gap mt">
        <button id="sp-save" class="btn btn-primary">Uložiť</button>
        <button id="sp-save-next" class="btn">Uložiť a pridať ďalší</button>
        <button id="sp-save-recipe" class="btn">Uložiť a otvoriť Recepty</button>
      </div>
      <p id="sp-msg" class="muted"></p>
    </div>
  `);
}

function ensureRecipesDom(){
  const host = $id('erp-panel-recipes'); if (!host || host.innerHTML.trim()) return;

  html(host, `
    <!-- Hlavička -->
    <div class="rcp-header card">
      <div class="rcp-top">
        <div class="rcp-left">
          <div class="row gap wrap">
            <label class="rcp-search">
              <span>Vyhľadať výrobok</span>
              <input id="rcp-search" placeholder="hľadaj názov / EAN">
            </label>
            <label class="rcp-product">
              <span>Výrobok</span>
              <select id="rcp-product"></select>
            </label>
            <button id="rcp-load" class="btn">Načítať</button>
          </div>
          <div class="rcp-kpis">
            <div class="kpi"><div class="kpi-name">EAN</div><div class="kpi-val" id="kpi-ean">—</div></div>
            <div class="kpi"><div class="kpi-name">Kategória</div><div class="kpi-val" id="kpi-cat">—</div></div>
            <div class="kpi"><div class="kpi-name">Jednotka</div><div class="kpi-val" id="kpi-unit">—</div></div>
            <div class="kpi"><div class="kpi-name">Kusová hmotnosť</div><div class="kpi-val" id="kpi-piece">—</div></div>
            <div class="kpi"><div class="kpi-name"># surovín</div><div class="kpi-val" id="kpi-mats">0</div></div>
            <div class="kpi"><div class="kpi-name">Upravené</div><div class="kpi-val" id="kpi-upd">—</div></div>
          </div>
        </div>
        <div class="rcp-right">
          <div class="row gap wrap right">
            <button id="rcp-export" class="btn">Export JSON</button>
            <button id="rcp-import" class="btn">Import JSON</button>
            <button id="rcp-print-one" class="btn btn-primary">Tlačiť</button>
          </div>
        </div>
      </div>
    </div>

    <!-- META výrobku -->
    <div class="card mt" id="rcp-meta">
      <h4>Parametre výroby</h4>
      <div class="row gap wrap">
        <label>Je výrobok? <input type="checkbox" id="rcp-isprod"></label>
        <label>Výrobná kategória <select id="rcp-prodcat"></select></label>
        <label>Výrobná jednotka
          <select id="rcp-unit"><option value="kg">kg</option><option value="ks">ks</option></select>
        </label>
        <label id="rcp-piece-weight-wrap" style="display:none;">Hmotnosť kusu (g)
          <input type="number" id="rcp-piece-weight" min="1" step="1" value="200">
        </label>
        <button id="rcp-meta-save" class="btn btn-primary">Uložiť parametre</button>
        <button id="rcp-prodcat-manage" class="btn">Správa výrobných kategórií</button>
      </div>
      <p id="rcp-meta-msg" class="muted"></p>
    </div>

    <!-- JEDNODUCHÝ BUILDER (max. jednoduchý import/pridávanie) -->
    <div id="rb2-card" class="card mt">
      <div class="row gap wrap">
        <label>Dávka (kg)
          <input id="rb2-batch" type="number" step="0.001" min="1" value="100">
        </label>
        <div class="chip">Spolu 100 kg: <strong id="rb2-total100">0.000</strong></div>
        <div class="chip">Spolu dávka: <strong id="rb2-totalBatch">0.000</strong></div>
        <div style="flex:1"></div>
        <button id="rb2-fill" class="btn">Načítať uložený</button>
        <button id="rb2-import" class="btn">Rýchly import</button>
        <button id="rb2-clear" class="btn">Vyčistiť</button>
      </div>

      <div class="row gap wrap mt">
        <input id="rb2-find" placeholder="Hľadať surovinu (názov alebo EAN)">
        <input id="rb2-q" type="number" step="0.001" min="0" value="1" style="width:140px">
        <button id="rb2-add-found" class="btn">Pridať</button>
        <span class="muted">Tip: Enter pridá prvú zhodu.</span>
      </div>
      <div id="rb2-suggest" class="mt" style="display:none"></div>

      <div class="table-wrap mt">
        <table class="table">
          <thead><tr>
            <th>Surovina</th>
            <th class="num">kg / 100 kg<br><small class="muted">„na dávku“ sa prepočíta</small></th>
            <th class="num"></th>
          </tr></thead>
          <tbody id="rb2-tbody"></tbody>
        </table>
      </div>

      <div class="row right gap mt">
        <button id="rb2-add" class="btn">+ Položka</button>
        <button id="rb2-save" class="btn btn-primary">Uložiť recept</button>
      </div>
      <p id="rb2-msg" class="muted"></p>
    </div>

    <!-- Doplňujúce tabs -->
    <div class="row gap mt">
      <button class="btn btn-tab active" id="pro-tab-norms">Normy & údaje</button>
      <button class="btn btn-tab" id="pro-tab-process">Postup</button>
      <button class="btn btn-tab" id="pro-tab-qc">Kontroly kvality</button>
      <button class="btn btn-tab" id="pro-tab-print">Tlač</button>
    </div>

    <div id="pro-norms" class="card mt">
      <div class="form-grid form-3">
        <label>Veľkosť dávky (kg)<input id="pro-batch" type="number" step="0.001" value="100"></label>
        <label>Očakávaná výťažnosť (kg)<input id="pro-yield" type="number" step="0.001"></label>
        <label>Trvanlivosť (dni)<input id="pro-shelf" type="number" step="1"></label>
        <label>Teplota skladovania (°C)<input id="pro-storage" type="number" step="0.1"></label>
        <label>Soľ (%)<input id="pro-salt" type="number" step="0.01"></label>
        <label>Tuk (%)<input id="pro-fat" type="number" step="0.01"></label>
        <label>Voda (%)<input id="pro-water" type="number" step="0.01"></label>
        <label>pH cieľ<input id="pro-ph" type="text" placeholder="napr. 5.8"></label>
        <label class="col-span-2">Alergény (CSV)<input id="pro-allergens" placeholder="GLUTEN, MILK"></label>
        <label class="col-span-2">Text etikety (zloženie)<input id="pro-labels"></label>
      </div>
      <div class="mt">
        <h4>Prísady (mg/kg)</h4>
        <div id="pro-additives">
          <div class="row gap">
            <input class="add-name" placeholder="Názov / E-číslo">
            <input class="add-mg" type="number" step="1" placeholder="mg/kg" style="width:120px">
            <button id="pro-add-additive" class="btn">+ Pridať prísadu</button>
          </div>
          <ul id="pro-additives-list" class="mt" style="margin:.5rem 0 0 1rem"></ul>
        </div>
      </div>
      <div class="row right mt">
        <button id="pro-save" class="btn btn-primary">Uložiť receptúru (meta)</button>
      </div>
      <p id="pro-msg" class="muted"></p>
    </div>

    <div id="pro-process" class="card mt" style="display:none">
      <div class="row gap">
        <input id="proc-title" placeholder="Názov kroku (napr. Mletie)">
        <input id="proc-mm" type="number" step="0.1" placeholder="Grinder mm" style="width:130px">
        <input id="proc-temp" type="number" step="0.1" placeholder="Teplota °C" style="width:130px">
        <input id="proc-time" type="number" step="1" placeholder="Čas (min)" style="width:130px">
        <input id="proc-rpm" type="number" step="1" placeholder="RPM" style="width:120px">
      </div>
      <div class="row gap mt">
        <input id="proc-notes" class="w-100" placeholder="Poznámky (postup, radenie mlecích platní, miešanie…)">
        <button id="proc-add" class="btn">+ Pridať krok</button>
      </div>
      <div class="table-wrap mt">
        <table class="table">
          <thead><tr><th>#</th><th>Názov</th><th>Detaily</th><th>Poznámka</th><th></th></tr></thead>
        <tbody id="proc-tbody"></tbody></table>
      </div>
    </div>

    <div id="pro-qc" class="card mt" style="display:none">
      <div class="row gap">
        <input id="qc-title" placeholder="Kontrolný bod (napr. T po miešaní)">
        <input id="qc-spec" placeholder="Špecifikácia (napr. ≤ 4 °C)">
        <input id="qc-notes" placeholder="Poznámka">
        <button id="qc-add" class="btn">+ Pridať kontrolu</button>
      </div>
      <ul id="qc-list" style="margin:.5rem 0 0 1rem"></ul>
    </div>

    <div id="pro-print" class="card mt" style="display:none">
      <div class="row gap wrap">
        <label>Filter – kategória <select id="print-cat"></select></label>
        <label>Filter – hľadať <input id="print-q" placeholder="názov / EAN"></label>
        <button id="print-load" class="btn">Načítať zoznam</button>
      </div>
      <div class="table-wrap mt">
        <table class="table">
          <thead><tr><th></th><th>Názov</th><th>EAN</th><th>Kategória</th></tr></thead>
          <tbody id="print-tbody"></tbody>
        </table>
      </div>
      <div class="row right mt">
        <button id="print-selected" class="btn btn-primary">Tlačiť vybrané</button>
      </div>
    </div>
  `);
}

/* ========== PREHĽAD KATALÓGU ========== */
async function loadOverview(){
  const tb = $id('erp-overview-tbody'); if (!tb) return;
  tb.innerHTML = '<tr><td colspan="6">Načítavam…</td></tr>';
  try {
    const data = await postJSON('/api/kancelaria/erp/catalog/overview', {});
    const rows = Array.isArray(data) ? data
               : Array.isArray(data?.items) ? data.items
               : Array.isArray(data?.products) ? data.products
               : Array.isArray(data?.data) ? data.data : [];
    tb.innerHTML = rows.length ? '' : '<tr><td colspan="6">Žiadne položky.</td></tr>';
    rows.forEach(r=>{
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${r.ean ?? r.EAN ?? ''}</td>
        <td>${r.nazov ?? r.name ?? r.product_name ?? ''}</td>
        <td class="num">${(typeof (r.dph ?? r.vat)==='number') ? Number(r.dph ?? r.vat).toFixed(2) : (r.dph ?? r.vat ?? '')}</td>
        <td>${r.predajna_kategoria ?? r.sales_category ?? r.sales_categories ?? ''}</td>
        <td>${r.jednotka ?? r.unit ?? r.unit_label ?? ''}</td>
        <td>${(r.je_vyroba ?? r.is_produced) ? 'Áno' : 'Nie'}</td>`;
      tb.appendChild(tr);
    });
  } catch(e){
    tb.innerHTML = `<tr><td colspan="6">❌ Chyba prehľadu: ${e.message || e}</td></tr>`;
  }
}

/* ========== PREDAJNÉ KATEGÓRIE ========== */
async function listSalesCategories(){ return postJSON('/api/kancelaria/erp/catalog/salesCategories', {}); }
async function loadSalesCategoriesInto(selectEl){
  if (!selectEl) return;
  try{
    const data = await listSalesCategories();
    const items = Array.isArray(data?.categories) ? data.categories
                : Array.isArray(data?.items) ? data.items
                : Array.isArray(data?.data) ? data.data : [];
    selectEl.innerHTML = items.map(c=>{
      const id = c.id ?? c.value ?? c.code ?? '';
      const nm = c.name ?? c.nazov ?? '';
      return `<option value="${id}">${nm}</option>`;
    }).join('');
  }catch(_){ selectEl.innerHTML = ''; }
}
async function refreshCatList(){
  const data = await listSalesCategories();
  const div = $id('erp-cat-list');
  if (div) div.innerHTML = '<ul style="margin:0;padding-left:1rem;">' +
    (data?.categories||[]).map(c=>`<li>${c.name}</li>`).join('') + '</ul>';
}

/* ========== API – RECEPTY & PRODUKCIA ========== */
async function apiRecipesProducts(){ return postJSON('/api/kancelaria/erp/recipes/products', {}); }
async function apiRecipesMaterials(){ return postJSON('/api/kancelaria/erp/recipes/materials', {}); }
async function apiRecipeGet(product_id){ return postJSON('/api/kancelaria/erp/recipes/get', { product_id }); }
async function apiRecipeSave(product_id, items){ return postJSON('/api/kancelaria/erp/recipes/save', { product_id, items }); }
async function apiProdcatList(){ return postJSON('/api/kancelaria/erp/prodcat/list', {}); }
async function apiProdcatAdd(name){ return postJSON('/api/kancelaria/erp/prodcat/add', { name }); }
async function apiProdmetaGet(product_id){ return postJSON('/api/kancelaria/erp/product/prodmeta/get', { product_id }); }
async function apiProdmetaSave(payload){ return postJSON('/api/kancelaria/erp/product/prodmeta/save', payload); }

/* ========== META + KPI ========== */
function updateKPIs({ean, category, unit, piece_g, mats, updated}){
  if ($id('kpi-ean'))  $id('kpi-ean').textContent  = ean || '—';
  if ($id('kpi-cat'))  $id('kpi-cat').textContent  = category || '—';
  if ($id('kpi-unit')) $id('kpi-unit').textContent = unit || '—';
  if ($id('kpi-piece'))$id('kpi-piece').textContent= piece_g ? `${piece_g} g` : '—';
  if ($id('kpi-mats')) $id('kpi-mats').textContent = mats ?? 0;
  if ($id('kpi-upd'))  $id('kpi-upd').textContent  = updated || '—';
}
async function fillMeta(pid){
  try{
    const m = await apiProdmetaGet(pid);
    const chk = $id('rcp-isprod'), selCat = $id('rcp-prodcat'), selU = $id('rcp-unit'),
          wrapPW = $id('rcp-piece-weight-wrap'), inpPW = $id('rcp-piece-weight');
    if (m && chk && selCat && selU){
      chk.checked = !!m.je_vyroba;
      if (m.production_category_id) selCat.value = String(m.production_category_id);
      selU.value = (m.production_unit === 1 ? 'ks' : 'kg');
      if (wrapPW) wrapPW.style.display = (selU.value === 'ks') ? '' : 'none';
      if (inpPW)  inpPW.value = m.piece_weight_g ?? 200;

      updateKPIs({
        ean: m.ean || '', category: m.prod_category || '',
        unit: selU.value, piece_g: m.piece_weight_g || null
      });
    }
  }catch(_){}
}

/* ========== RÝCHLE PRIDÁVANIE PRODUKTOV ========== */
let __prodSimpleWired = false;
function sp_payload(){
  const name  = ($id('sp-name')?.value || '').trim();
  const unit  = $id('sp-unit')?.value || 'kg';
  const piece = unit === 'ks' ? Number($id('sp-piece')?.value || 0) : null;
  const vat   = Number($id('sp-vat')?.value || 20);
  const scId  = Number($id('sp-sc')?.value || 0);
  const ean   = ($id('sp-ean')?.value || '').trim() || null;
  const isProd= !!$id('sp-isprod')?.checked;

  return {
    ean, name, vat, sales_category_id: scId, unit, is_produced: isProd,
    nazov: name, dph: vat, jednotka: unit, je_vyroba: isProd ? 1 : 0,
    piece_weight_g: piece
  };
}
function sp_validate(){
  const name = ($id('sp-name')?.value || '').trim();
  const unit = $id('sp-unit')?.value || 'kg';
  const piece= unit==='ks' ? Number($id('sp-piece')?.value || 0) : 0;
  if (!name) return 'Zadaj názov produktu.';
  if (unit==='ks' && piece<=0) return 'Zadaj hmotnosť 1 ks (g) > 0.';
  return '';
}
async function sp_afterSaveGoToRecipes(maybeId, name, ean){
  $id('erp-tab-recipes')?.click();
  setTimeout(async ()=>{
    try{
      const prod = await apiRecipesProducts();
      const list = prod?.products || [];
      const sel  = $id('rcp-product');
      if (!sel || !list.length) return;

      let pick = null;
      if (maybeId) pick = list.find(p => Number(p.id) === Number(maybeId));
      if (!pick && ean) pick = list.find(p => (p.ean||'') === ean);
      if (!pick) pick = list.find(p => (p.nazov||'').trim().toLowerCase() === (name||'').trim().toLowerCase());

      if (pick) {
        sel.value = String(pick.id);
        $id('rcp-load')?.click();
      }
    }catch(_){}
  }, 250);
}
function setupSimpleProdOnce(){
  if (__prodSimpleWired) return; __prodSimpleWired = true;

  on($id('sp-unit'), 'change', ()=>{
    const wrap = $id('sp-piece-wrap');
    if (wrap) wrap.style.display = ($id('sp-unit').value === 'ks') ? '' : 'none';
  });

  on($id('sp-save'), 'click', async ()=>{
    const msg = $id('sp-msg'); msg && (msg.textContent='');
    const err = sp_validate(); if (err){ msg.textContent = err; return; }
    try{
      const resp = await postJSON('/api/kancelaria/erp/catalog/addProduct', sp_payload());
      msg.textContent = resp?.ok ? '✅ Uložené.' : ('❌ ' + (resp?.error || 'Chyba'));
      if ($id('erp-panel-overview')?.style.display !== 'none') { await loadOverview(); }
    }catch(e){ msg.textContent = '❌ ' + e.message; }
  });

  on($id('sp-save-next'), 'click', async ()=>{
    const msg = $id('sp-msg'); msg && (msg.textContent='');
    const err = sp_validate(); if (err){ msg.textContent = err; return; }
    try{
      const resp = await postJSON('/api/kancelaria/erp/catalog/addProduct', sp_payload());
      msg.textContent = resp?.ok ? '✅ Uložené. Môžeš pridať ďalší…' : ('❌ ' + (resp?.error || 'Chyba'));
      $id('sp-name') && ($id('sp-name').value = '');
      $id('sp-ean')  && ($id('sp-ean').value  = '');
      $id('sp-name')?.focus();
      if ($id('erp-panel-overview')?.style.display !== 'none') { await loadOverview(); }
    }catch(e){ msg.textContent = '❌ ' + e.message; }
  });

  on($id('sp-save-recipe'), 'click', async ()=>{
    const msg = $id('sp-msg'); msg && (msg.textContent='');
    const err = sp_validate(); if (err){ msg.textContent = err; return; }
    const payload = sp_payload();
    try{
      const resp = await postJSON('/api/kancelaria/erp/catalog/addProduct', payload);
      if (resp?.ok){
        msg.textContent = '✅ Uložené. Otváram Recepty…';
        const newId = resp?.product?.id || resp?.id || null;
        await sp_afterSaveGoToRecipes(newId, payload.name, payload.ean);
      } else {
        msg.textContent = '❌ ' + (resp?.error || 'Chyba');
      }
    }catch(e){ msg.textContent = '❌ ' + e.message; }
  });
}

/* ========== JEDNODUCHÝ BUILDER + RÝCHLY IMPORT ========== */
let __builderWired = false, __matsCache = [], __matsLoaded = false;

async function ensureMats(){
  if (__matsLoaded) return;
  try{
    const d = await apiRecipesMaterials();
    __matsCache = d?.materials || [];
  }finally{
    __matsLoaded = true;
  }
}
function optionsHtml(){ return __matsCache.map(m=>`<option value="${m.id}">${m.nazov}</option>`).join(''); }

function mkRow(mid=null, q100="0.000"){
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td style="min-width:320px">
      <select class="rb2-m">${optionsHtml()}</select>
    </td>
    <td class="num">
      <input class="rb2-100" type="number" step="0.001" min="0" value="${q100}" style="max-width:140px">
      <div class="muted" style="font-size:.8em;margin-top:.2rem">na dávku: <strong class="rb2-batch">0.000</strong> kg</div>
    </td>
    <td class="num"><button class="btn btn-danger rb2-del">x</button></td>
  `;
  if (mid) tr.querySelector('.rb2-m').value = String(mid);
  tr.querySelector('.rb2-100').addEventListener('input', recalc);
  tr.querySelector('.rb2-del').addEventListener('click', ()=>{ tr.remove(); recalc(); });
  return tr;
}

function upsertRow(mid, q100){
  const rows = $$('#rb2-tbody tr');
  for (const tr of rows){
    const cur = Number(tr.querySelector('.rb2-m')?.value || 0);
    if (cur === mid){
      tr.querySelector('.rb2-100').value = Number(q100||0).toFixed(3);
      recalc();
      return;
    }
  }
  $id('rb2-tbody')?.appendChild(mkRow(mid, Number(q100||0).toFixed(3)));
  recalc();
}

function recalc(){
  const b = Number($id('rb2-batch')?.value || 100);
  let t100 = 0, tB = 0;
  $$('#rb2-tbody tr').forEach(tr=>{
    const n = Number(tr.querySelector('.rb2-100')?.value || 0);
    const vb = (n * b / 100);
    const el = tr.querySelector('.rb2-batch');
    if (el) el.textContent = fmt(vb,3);
    t100 += n; tB += vb;
  });
  $id('rb2-total100') && ($id('rb2-total100').textContent = fmt(t100,3));
  $id('rb2-totalBatch')&& ($id('rb2-totalBatch').textContent = fmt(tB,3));
  updateKPIs({ mats: $$('#rb2-tbody tr').length });
}

async function fillBuilderFromRecipe(pid){
  await ensureMats();
  const tb = $id('rb2-tbody'); if (!tb) return;
  tb.innerHTML = '';
  try{
    const rec = await apiRecipeGet(pid);
    const items = rec?.recipe?.items || [];
    if (items.length){
      items.forEach(it => upsertRow(Number(it.material_id), Number(it.qty_per_100kg||0)));
    }else{
      tb.appendChild(mkRow());
      recalc();
    }
  }catch(e){
    $id('rb2-msg') && ($id('rb2-msg').textContent = '❌ ' + e.message);
  }
}

function collectBuilderItems(){
  const items = [];
  const seen = new Set();
  $$('#rb2-tbody tr').forEach(tr=>{
    const mid = Number(tr.querySelector('.rb2-m')?.value || 0);
    const q   = Number(tr.querySelector('.rb2-100')?.value || 0);
    if (!mid || q<=0) return;
    if (seen.has(mid)) return;
    seen.add(mid);
    items.push({ material_id: mid, qty_per_100kg: q });
  });
  return items;
}

function findMaterials(q){
  const s = (q||'').toLowerCase().trim();
  if (!s) return [];
  return __matsCache.filter(m =>
    (m.nazov||'').toLowerCase().includes(s) || (String(m.ean||'')).includes(s)
  ).slice(0, 8);
}

function showSuggestions(q){
  const box = $id('rb2-suggest'); if (!box) return;
  if (!q){ box.style.display='none'; box.innerHTML=''; return; }
  const hits = findMaterials(q);
  if (!hits.length){ box.style.display='none'; box.innerHTML=''; return; }
  box.style.display='';
  box.innerHTML = `
    <div class="card" style="padding:.5rem">
      ${hits.map(h=>`<button class="btn btn-light rb2-pick" data-id="${h.id}" style="margin:.2rem">${h.nazov}</button>`).join('')}
    </div>`;
  $$('.rb2-pick', box).forEach(btn=>{
    btn.onclick = ()=>{
      const id = Number(btn.dataset.id);
      const qv = Number($id('rb2-q')?.value || 1);
      upsertRow(id, qv);
      $id('rb2-find').value = '';
      showSuggestions('');
    };
  });
}

function parseImportText(raw){
  const rows = [];
  const lines = (raw||'').split(/\r?\n/).map(l=>l.trim()).filter(Boolean);
  for (const line of lines){
    // rozdelovače: ; , tab | forma: nazov; množstvo
    const parts = line.split(/;|,|\t/).map(s=>s.trim()).filter(Boolean);
    if (parts.length < 2) continue;
    const last = parts[parts.length-1];
    const qty = parseFloat(String(last).replace(',', '.'));
    if (isNaN(qty) || qty<=0) continue;
    const name = parts.slice(0, parts.length-1).join(' ');
    rows.push({ name, qty });
  }
  return rows;
}

function matchMaterialByName(name){
  const s = (name||'').toLowerCase();
  // 1) presná zhoda (case-insensitive)
  let hit = __matsCache.find(m => (m.nazov||'').toLowerCase() === s);
  if (hit) return hit;
  // 2) začiatok názvu
  hit = __matsCache.find(m => (m.nazov||'').toLowerCase().startsWith(s));
  if (hit) return hit;
  // 3) substring
  hit = __matsCache.find(m => (m.nazov||'').toLowerCase().includes(s));
  return hit || null;
}

function openImportDialog(){
  openModal(`
    <div class="sheet">
      <h3>Rýchly import receptu</h3>
      <p class="muted">Formát: <code>názov_suroviny; množstvo_kg_na_100kg</code> &nbsp; (napr. <em>Soľ; 1.8</em> alebo <em>Bravčové mäso; 60</em>)</p>
      <textarea id="imp-text" rows="10" style="width:100%;"></textarea>
      <div class="row gap mt">
        <button id="imp-preview" class="btn">Náhľad</button>
        <button id="imp-apply" class="btn btn-primary" disabled>Vložiť do receptu</button>
        <button id="imp-close" class="btn">Zavrieť</button>
      </div>
      <div id="imp-out" class="mt"></div>
    </div>
  `);

  const out = $id('imp-out');
  let preview = [];

  on($id('imp-preview'),'click', async ()=>{
    await ensureMats();
    const rows = parseImportText($id('imp-text')?.value || '');
    if (!rows.length){ out.innerHTML = '<p class="muted">Nenašiel som žiadne riadky s číselným množstvom.</p>'; $id('imp-apply').disabled = true; return; }
    const mapped = rows.map(r=>{
      const mat = matchMaterialByName(r.name);
      return { ...r, mat };
    });
    preview = mapped;
    const ok = mapped.filter(x=>x.mat);
    const nok= mapped.filter(x=>!x.mat);
    out.innerHTML = `
      <div class="card">
        <p><strong>Našlo sa:</strong> ${ok.length} &nbsp;|&nbsp; <strong>Bez zhody:</strong> ${nok.length}</p>
        ${nok.length ? `<p class="muted">Bez zhody (uprav názvy): ${nok.map(x=>`<code>${x.name}</code>`).join(', ')}</p>`:''}
        ${ok.length ? `
          <table class="table mt">
            <thead><tr><th>Surovina</th><th class="num">kg/100 kg</th></tr></thead>
            <tbody>${ok.map(x=>`<tr><td>${x.mat.nazov}</td><td class="num">${Number(x.qty).toFixed(3)}</td></tr>`).join('')}</tbody>
          </table>` : ''}
      </div>`;
    $id('imp-apply').disabled = ok.length===0;
  });

  on($id('imp-apply'),'click', ()=>{
    const ok = preview.filter(x=>x.mat);
    ok.forEach(x=> upsertRow(Number(x.mat.id), Number(x.qty)));
    recalc(); closeModal();
  });
  on($id('imp-close'),'click', closeModal);
}

/* ========== PRO TABS + AKCIE ========== */
let __proWired = false;
function wireProOnce(){
  if (__proWired) return; __proWired = true;

  // prepínanie tabov
  document.addEventListener('click', (e)=>{
    const tabs = [
      {btn:'#pro-tab-norms',   view:'#pro-norms'},
      {btn:'#pro-tab-process', view:'#pro-process'},
      {btn:'#pro-tab-qc',      view:'#pro-qc'},
      {btn:'#pro-tab-print',   view:'#pro-print'},
    ];
    for (const t of tabs){
      if (e.target?.matches(t.btn)){
        tabs.forEach(x=>{
          $id(x.btn.replace('#',''))?.classList.remove('active');
          const v = $id(x.view.replace('#','')); if (v) v.style.display = 'none';
        });
        e.target.classList.add('active');
        const v = $id(t.view.replace('#','')); if (v) v.style.display = '';
      }
    }
  });

  // prísady
  on($id('pro-add-additive'),'click', ()=>{
    const name = ($('.add-name')?.value || '').trim();
    const mg   = Number($('.add-mg')?.value || 0);
    if (!name || mg<=0) return;
    const li = document.createElement('li');
    li.textContent = `${name} – ${mg} mg/kg`;
    li.dataset.name = name; li.dataset.mg = mg;
    $id('pro-additives-list')?.appendChild(li);
  });

  // postup
  on($id('proc-add'),'click', ()=>{
    const tb = $id('proc-tbody'); if (!tb) return;
    const no = tb.children.length + 1;
    const title = ($id('proc-title')?.value || '').trim();
    const mm    = $id('proc-mm')?.value || '';
    const temp  = $id('proc-temp')?.value || '';
    const time  = $id('proc-time')?.value || '';
    const rpm   = $id('proc-rpm')?.value || '';
    const notes = $id('proc-notes')?.value || '';
    const details = [mm && `mletie ${mm} mm`, temp && `t ${temp} °C`, time && `${time} min`, rpm && `${rpm} RPM`].filter(Boolean).join(', ');
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${no}</td><td>${title}</td><td>${details}</td><td>${notes}</td><td><button class="btn btn-danger del">x</button></td>`;
    tr.querySelector('.del').onclick = ()=> tr.remove();
    tb.appendChild(tr);
  });

  // QC
  on($id('qc-add'),'click', ()=>{
    const ul = $id('qc-list'); if (!ul) return;
    const t = ($id('qc-title')?.value || '').trim();
    const s = ($id('qc-spec')?.value || '').trim();
    const n = ($id('qc-notes')?.value || '').trim();
    if (!t) return;
    const li = document.createElement('li');
    li.innerHTML = `<strong>${t}</strong> — ${s} ${n ? `(<em>${n}</em>)` : ''}`;
    li.dataset.title = t; li.dataset.spec = s; li.dataset.notes = n;
    ul.appendChild(li);
  });

  // uloženie META (normy + postup + QC)
  on($id('pro-save'),'click', async ()=>{
    const pid = Number($id('rcp-product')?.value || 0);
    if (!pid){ $id('pro-msg').textContent = 'Vyber výrobok.'; return; }
    const rec = await apiRecipeGet(pid);
    const recipe_id = rec?.recipe?.id || rec?.id || 0;
    if (!recipe_id){ $id('pro-msg').textContent = 'Recept neexistuje (najprv ulož suroviny).'; return; }

    const meta = {
      version: 1,
      header: {
        batch_size_kg: Number($id('pro-batch')?.value || 100),
        yield_expected_kg: $id('pro-yield')?.value ? Number($id('pro-yield').value) : null,
        shelf_life_days: $id('pro-shelf')?.value ? Number($id('pro-shelf').value) : null,
        storage_temp_c: $id('pro-storage')?.value ? Number($id('pro-storage').value) : null,
        allergens: ($id('pro-allergens')?.value || '').split(',').map(s=>s.trim()).filter(Boolean),
        labels_text: $id('pro-labels')?.value || ''
      },
      norms: {
        salt_pct: $id('pro-salt')?.value ? Number($id('pro-salt').value) : null,
        fat_pct:  $id('pro-fat') ?.value ? Number($id('pro-fat').value)  : null,
        water_pct:$id('pro-water')?.value? Number($id('pro-water').value): null,
        ph_target:$id('pro-ph')?.value || null,
        additives: Array.from($id('pro-additives-list')?.children || []).map(li => ({
          name: li.dataset.name, mg_per_kg: Number(li.dataset.mg || 0)
        }))
      },
      process: Array.from($id('proc-tbody')?.children || []).map((tr,i)=>({
        no: i+1,
        title: tr.children[1]?.textContent || '',
        details: tr.children[2]?.textContent || '',
        notes: tr.children[3]?.textContent || ''
      })),
      qc: Array.from($id('qc-list')?.children || []).map(li => ({
        title: li.dataset.title, spec: li.dataset.spec, notes: li.dataset.notes
      })),
      notes: ''
    };

    try{
      const resp = await postJSON('/api/kancelaria/erp/recipes/meta/save', { recipe_id, meta });
      $id('pro-msg').textContent = resp?.ok ? '✅ Receptúra – meta uložená' : ('❌ ' + (resp?.error || 'Chyba'));
    }catch(e){ $id('pro-msg').textContent = '❌ ' + e.message; }
  });

  // PRINT
  on($id('print-load'),'click', async ()=>{
    const cat = Number($id('print-cat')?.value || 0) || null;
    const q   = ($id('print-q')?.value || '').trim() || null;
    const data = await postJSON('/api/kancelaria/erp/recipes/list', { category_id: cat, q });
    const tb = $id('print-tbody'); tb.innerHTML = '';
    (data?.items||[]).forEach(r=>{
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><input type="checkbox" class="pick" value="${r.recipe_id}"></td><td>${r.nazov||''}</td><td>${r.ean||''}</td><td>${r.prod_category||''}</td>`;
      tb.appendChild(tr);
    });
  });

  on($id('print-selected'),'click', async ()=>{
    const ids = Array.from($$('#print-tbody .pick:checked')).map(i=>Number(i.value));
    if (!ids.length){ alert('Vyber aspoň 1 recept.'); return; }
    const xsrf = document.cookie.split('; ').find(c=>c.startsWith('XSRF-TOKEN='))?.split('=')[1] || '';
    const res  = await fetch('/api/kancelaria/erp/recipes/print', {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-CSRF-Token':xsrf},
      body: JSON.stringify({ recipe_ids: ids, variant:'single' })
    });
    if (!res.ok){ alert(await res.text()); return; }
    const blob = await res.blob(); const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'receptury.pdf';
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  });
}

/* ========== HEADER: export/import/print current + KPI ========== */
let __hdrWired = false;
function wireHeaderOnce(){
  if (__hdrWired) return; __hdrWired = true;

  on($id('rcp-export'), 'click', async ()=>{
    const pid = Number($id('rcp-product')?.value||0);
    if (!pid) return alert('Vyber výrobok.');
    const rec = await apiRecipeGet(pid);
    const rid = rec?.recipe?.id || rec?.id;
    if (!rid) return alert('Recept neexistuje.');
    const meta = await postJSON('/api/kancelaria/erp/recipes/meta/get', { recipe_id: rid });
    const blob = new Blob([JSON.stringify(meta.meta||{}, null, 2)], {type:'application/json;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = `recipe_${rid}_meta.json`;
    document.body.appendChild(a); a.click(); a.remove();
  });

  on($id('rcp-import'), 'click', ()=>{
    const input = document.createElement('input'); input.type='file'; input.accept='.json,application/json';
    input.onchange = async (ev)=>{
      const f = ev.target.files[0]; if(!f) return;
      try{
        const txt = await f.text(); const meta = JSON.parse(txt);
        const pid = Number($id('rcp-product')?.value||0);
        if (!pid) return alert('Vyber výrobok.');
        const rec = await apiRecipeGet(pid);
        const rid = rec?.recipe?.id || rec?.id; if (!rid) return alert('Recept neexistuje.');
        const resp = await postJSON('/api/kancelaria/erp/recipes/meta/save', { recipe_id: rid, meta });
        alert(resp?.ok ? '✅ Importované a uložené.' : (resp?.error || 'Chyba'));
      }catch(e){ alert('Chybný JSON: '+e.message); }
    };
    input.click();
  });

  on($id('rcp-print-one'),'click', async ()=>{
    const pid = Number($id('rcp-product')?.value||0);
    if (!pid) return alert('Vyber výrobok.');
    const rec = await apiRecipeGet(pid);
    const rid = rec?.recipe?.id || rec?.id; if (!rid) return alert('Recept neexistuje.');
    const xsrf = document.cookie.split('; ').find(c=>c.startsWith('XSRF-TOKEN='))?.split('=')[1] || '';
    const res  = await fetch('/api/kancelaria/erp/recipes/print', {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-CSRF-Token':xsrf},
      body: JSON.stringify({ recipe_ids:[rid], variant:'single' })
    });
    if (!res.ok){ alert(await res.text()); return; }
    const blob = await res.blob(); const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'receptura.pdf';
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  });

  on($id('rcp-product'),'change', ()=>{
    const opt = $id('rcp-product')?.selectedOptions?.[0];
    if (!opt) return;
    updateKPIs({
      ean: opt.dataset.ean||'', category: opt.dataset.cat||'',
      unit: opt.dataset.unit||'', piece_g: opt.dataset.piece||''
    });
  });
}

/* ========== RECIPES: vyhľadanie, meta save, načítanie ========== */
let __recipesWired = false;
function wireRecipesOnce(){
  if (__recipesWired) return; __recipesWired = true;

  on($id('rcp-unit'),'change', ()=>{
    const wrap = $id('rcp-piece-weight-wrap');
    if (wrap) wrap.style.display = ($id('rcp-unit').value === 'ks') ? '' : 'none';
  });

  on($id('rcp-load'), 'click', async ()=>{
    const pid = Number($id('rcp-product')?.value || 0);
    if (!pid) return;
    await fillMeta(pid);
    await fillBuilderFromRecipe(pid);
  });

  on($id('rcp-meta-save'), 'click', async ()=>{
    const pid = Number($id('rcp-product')?.value || 0);
    const payload = {
      product_id: pid,
      is_produced: $id('rcp-isprod')?.checked,
      production_category_id: Number($id('rcp-prodcat')?.value || 0),
      production_unit: $id('rcp-unit')?.value || 'kg',
      piece_weight_g: ($id('rcp-unit')?.value === 'ks') ? Number($id('rcp-piece-weight')?.value || 0) : null
    };
    const msg = $id('rcp-meta-msg'); if (msg) msg.textContent = '';
    try{
      const resp = await apiProdmetaSave(payload);
      msg && (msg.textContent = resp?.ok ? '✅ Parametre uložené' : (resp?.error || 'Chyba'));
    }catch(e){ msg && (msg.textContent = '❌ '+e.message); }
  });

  on($id('rcp-prodcat-manage'), 'click', async ()=>{
    const data = await apiProdcatList();
    const list = (data?.production_categories||[]).map(c=>`<li>${c.name}</li>`).join('');
    openModal(`
      <div class="sheet">
        <h3>Výrobné kategórie</h3>
        <ul style="margin:0 0 .5rem 1rem;">${list}</ul>
        <div class="row gap">
          <input id="pc-new" placeholder="Nová kategória">
          <button id="pc-add" class="btn btn-primary">Pridať</button>
          <button id="pc-close" class="btn">Zavrieť</button>
        </div>
        <p id="pc-msg" class="muted"></p>
      </div>
    `);
    on($id('pc-close'),'click', closeModal);
    on($id('pc-add'),'click', async ()=>{
      const name = $id('pc-new')?.value.trim(); const pmsg = $id('pc-msg');
      if (!name){ pmsg.textContent='Zadaj názov'; return; }
      pmsg.textContent='';
      try{
        const r = await apiProdcatAdd(name);
        pmsg.textContent = r?.ok ? '✅ Pridané' : (r?.error || 'Chyba');
        const cats = await apiProdcatList();
        const selCat = $id('rcp-prodcat');
        const printCat = $id('print-cat');
        if (selCat) selCat.innerHTML = (cats?.production_categories||[]).map(c=>`<option value="${c.id}">${c.name}</option>`).join('');
        if (printCat) printCat.innerHTML = `<option value="">(všetky)</option>` + (cats?.production_categories||[]).map(c=>`<option value="${c.id}">${c.name}</option>`).join('');
      }catch(e){ pmsg.textContent = '❌ '+e.message; }
    });
  });
}

/* ========== BUILDER WIRING (vyhľadávanie, import, save) ========== */
function wireSimpleBuilderOnce(){
  if (__builderWired) return; __builderWired = true;

  on($id('rb2-batch'),'input', recalc);

  on($id('rb2-add'),'click', async ()=>{
    await ensureMats();
    $id('rb2-tbody')?.appendChild(mkRow());
    recalc();
  });

  on($id('rb2-clear'),'click', ()=>{
    const tb = $id('rb2-tbody'); if (!tb) return;
    tb.innerHTML = ''; recalc();
  });

  on($id('rb2-fill'),'click', async ()=>{
    const pid = Number($id('rcp-product')?.value || 0);
    if (!pid) return;
    await fillBuilderFromRecipe(pid);
  });

  // Rýchly import
  on($id('rb2-import'),'click', openImportDialog);

  // Vyhľadávanie – návrhy a pridanie
  on($id('rb2-find'), 'input', async (e)=>{
    await ensureMats();
    showSuggestions(e.target.value);
  });
  on($id('rb2-find'), 'keydown', async (e)=>{
    if (e.key === 'Enter'){
      e.preventDefault();
      await ensureMats();
      const hits = findMaterials($id('rb2-find')?.value || '');
      if (hits.length){
        const qv = Number($id('rb2-q')?.value || 1);
        upsertRow(Number(hits[0].id), qv);
        $id('rb2-find').value = '';
        showSuggestions('');
      }
    }
  });
  on($id('rb2-add-found'),'click', async ()=>{
    await ensureMats();
    const hits = findMaterials($id('rb2-find')?.value || '');
    if (!hits.length) return;
    const qv = Number($id('rb2-q')?.value || 1);
    upsertRow(Number(hits[0].id), qv);
    $id('rb2-find').value = '';
    showSuggestions('');
  });

  // Uloženie
  on($id('rb2-save'),'click', async ()=>{
    const pid = Number($id('rcp-product')?.value || 0);
    if (!pid){ $id('rb2-msg') && ($id('rb2-msg').textContent='Vyber výrobok.'); return; }
    const items = collectBuilderItems();
    if (!items.length){ $id('rb2-msg') && ($id('rb2-msg').textContent='Pridaj aspoň 1 surovinu > 0.'); return; }
    try{
      const resp = await apiRecipeSave(pid, items);
      $id('rb2-msg') && ($id('rb2-msg').textContent = resp?.ok ? '✅ Recept uložený' : ('❌ ' + (resp?.error || 'Chyba')));
    }catch(e){ $id('rb2-msg') && ($id('rb2-msg').textContent = '❌ ' + e.message); }
  });

  // prvý riadok pri prvom otvorení
  (async ()=>{ await ensureMats(); if ($id('rb2-tbody')?.children.length===0){ $id('rb2-tbody').appendChild(mkRow()); recalc(); }})();
}

/* ========== TABS & HLAVIČKA ========== */
let __erpWired = false, __prodCache = [];
function wireTabsOnce(){
  if (__erpWired) return; __erpWired = true;

  on($id('erp-tab-overview'), 'click', async ()=>{
    ensureOverviewDom(); showPanel('erp-panel-overview'); await loadOverview();
  });

  on($id('erp-tab-addcat'), 'click', async ()=>{
    ensureAddCatDom(); showPanel('erp-panel-addcat'); await refreshCatList();
  });

  on($id('erp-tab-addprod'), 'click', async ()=>{
    ensureAddProdDom(); showPanel('erp-panel-addprod');
    await loadSalesCategoriesInto($id('sp-sc'));
    setupSimpleProdOnce();
  });

  on($id('erp-tab-recipes'), 'click', async ()=>{
    ensureRecipesDom(); showPanel('erp-panel-recipes');

    try{
      const prod = await apiRecipesProducts();
      __prodCache = prod?.products || [];
      const selProd = $id('rcp-product');
      if (selProd) selProd.innerHTML = __prodCache.map(
        p=>`<option value="${p.id}" data-ean="${p.ean||''}" data-cat="${p.prod_category||''}" data-unit="${p.production_unit===1?'ks':'kg'}" data-piece="${p.piece_weight_g||''}">${p.nazov}</option>`
      ).join('');
      on($id('rcp-search'),'input',()=>{
        const q = ($id('rcp-search')?.value||'').toLowerCase().trim();
        if (!selProd) return;
        const list = q ? __prodCache.filter(p => (p.nazov||'').toLowerCase().includes(q) || (p.ean||'').includes(q)) : __prodCache;
        selProd.innerHTML = list.map(
          p=>`<option value="${p.id}" data-ean="${p.ean||''}" data-cat="${p.prod_category||''}" data-unit="${p.production_unit===1?'ks':'kg'}" data-piece="${p.piece_weight_g||''}">${p.nazov}</option>`
        ).join('');
      });
    }catch(_){}

    try{
      const cats = await apiProdcatList();
      const selCat = $id('rcp-prodcat'), printCat = $id('print-cat');
      if (selCat)   selCat.innerHTML   = (cats?.production_categories||[]).map(c=>`<option value="${c.id}">${c.name}</option>`).join('');
      if (printCat) printCat.innerHTML = `<option value="">(všetky)</option>` + (cats?.production_categories||[]).map(c=>`<option value="${c.id}">${c.name}</option>`).join('');
    }catch(_){}

    const pid = Number($id('rcp-product')?.value || 0);
    if (pid) { await fillMeta(pid); await fillBuilderFromRecipe(pid); }

    wireSimpleBuilderOnce(); wireProOnce(); wireHeaderOnce(); wireRecipesOnce();
  });

  // panel Kategórie – uloženie novej
  document.addEventListener('click', async (e)=>{
    if (e.target?.id === 'erp-cat-save'){
      const name = $id('erp-cat-name')?.value.trim(), msg = $id('erp-cat-msg');
      if (!name){ msg && (msg.textContent='Zadaj názov kategórie.'); return; }
      msg && (msg.textContent = '');
      try{
        const resp = await postJSON('/api/kancelaria/erp/catalog/addSalesCategory', { name });
        msg && (msg.textContent = resp?.ok ? '✅ Uložené' : ('❌ ' + (resp?.error || 'Chyba')));
        await refreshCatList();
        const scSel = $id('sp-sc'); if (scSel) await loadSalesCategoriesInto(scSel);
      }catch(err){ msg && (msg.textContent = '❌ ' + err.message); }
    }
  });
}

/* ========== Globálny init pre kancelaria.js ========== */
window.initializeErpAdminModule = function(){
  if (window.__erpAdminInited) return;
  window.__erpAdminInited = true;

  const root = $id('section-erp') || $id('section-erp-admin');
  if (!root) {
    console.warn('[ERP Admin] Sekcia #section-erp nie je v DOM.');
    return;
  }

  ensureOverviewDom();
  ensureAddCatDom();
  ensureAddProdDom();
  ensureRecipesDom();

  wireTabsOnce();
  wireHeaderOnce();

  // default: Prehľad
  const btnOverview = $id('erp-tab-overview');
  if (btnOverview) btnOverview.click();
  else { showPanel('erp-panel-overview'); loadOverview(); }
};
