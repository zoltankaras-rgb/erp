// static/js/kancelaria/fleet.js
// Flotila – vycentrované taby (Kniha jázd / Tankovanie / Náklady / Analýza),
// vždy zobrazená iba jedna podsekcia, čisté modaly a editačné tabuľky.

/* -------------------- Mini modal -------------------- */
let __escHandler = null;
function showModal(title, builder){
  const wrap = document.createElement('div');
  wrap.id = 'modal-container';
  wrap.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:99999';

  const card = document.createElement('div');
  card.className = 'modal-card';
  card.style.cssText = 'background:#fff;min-width:320px;max-width:960px;width:92vw;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.2);';
  card.innerHTML = `
    <div class="modal-header" style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px 16px;border-bottom:1px solid #e5e7eb;">
      <h3 class="modal-title" style="margin:0;font-size:18px;font-weight:700">${title}</h3>
      <button id="modal-close" class="btn" type="button" style="border:1px solid #e5e7eb;background:#fff;border-radius:8px;padding:6px 10px;cursor:pointer">✕</button>
    </div>
    <div id="modal-body" class="modal-body" style="padding:16px;max-height:70vh;overflow:auto"></div>
    <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;padding:12px 16px;border-top:1px solid #e5e7eb"></div>
  `;
  wrap.appendChild(card);
  document.body.appendChild(wrap);

  wrap.addEventListener('click', (e)=>{ if (e.target === wrap) closeModal(); });
  __escHandler = (e)=>{ if (e.key === 'Escape') closeModal(); };
  document.addEventListener('keydown', __escHandler);
  document.getElementById('modal-close').onclick = closeModal;

  Promise.resolve(typeof builder==='function'?builder():builder).then(cfg=>{
    document.getElementById('modal-body').innerHTML = cfg.html || '';
    cfg.onReady && cfg.onReady();
    const first = document.querySelector('#modal-body input, #modal-body textarea, #modal-body select, #modal-body button');
    first && first.focus();
  });
}
function closeModal(){
  const wrap = document.getElementById('modal-container');
  if (wrap) wrap.remove();
  if (__escHandler){ document.removeEventListener('keydown', __escHandler); __escHandler = null; }
}

/* -------------------- Helpers -------------------- */
const esc = s => (s==null?'':String(s)).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const fx  = (n,d=2)=>{ const x=Number(n); return Number.isFinite(x)?x.toFixed(d):''; };

let fleetState = {
  selected_vehicle_id: null,
  selected_year: new Date().getFullYear(),
  selected_month: new Date().getMonth()+1,
  vehicles: [],
  logs: [],
  refuelings: [],
  costs: [],
  analysis: {},
  current_tab: 'logbook' // default viditeľná podsekcia
};
window.fleetState = fleetState;

/* -------------------- Init -------------------- */
export async function initializeFleetModule(){
  const section = document.getElementById('section-fleet');
  if (!section) return;

  section.innerHTML = `
    <div class="fleet-main" style="max-width:1280px;margin:0 auto;">
      <div class="section-header"><h2>Flotila</h2></div>

      <!-- FILTRE (vozidlo/rok/mesiac) -->
      <div class="card">
        <div class="row wrap" style="gap:12px">
          <label>Vozidlo <select id="fleet-vehicle-select" autocomplete="off"></select></label>
          <label>Rok <select id="fleet-year-select" autocomplete="off"></select></label>
          <label>Mesiac <select id="fleet-month-select" autocomplete="off"></select></label>
          <div style="flex:1"></div>
          <button id="print-fleet-report-btn" class="btn">Tlačiť report</button>
        </div>
      </div>

      <!-- TAB TLAČIDLÁ (vycentrované ako v sklade) -->
      <div class="card mt">
        <div class="toolbar toolbar-center fleet-tabs" style="display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;padding:12px;">
          <button class="btn tab-btn" data-tab="logbook">Kniha jázd</button>
          <button class="btn tab-btn" data-tab="refueling">Tankovanie</button>
          <button class="btn tab-btn" data-tab="costs">Náklady</button>
          <button class="btn tab-btn" data-tab="analysis">Analýza</button>
        </div>
      </div>

      <!-- OBSAH – iba jedna view naraz -->
      <div id="fleet-view-logbook"  class="card mt fleet-view">
        <div id="fleet-logbook-container" class="table-wrap"></div>
        <div class="row right"><button id="save-logbook-changes-btn" class="btn btn-primary mt">Uložiť zmeny v knihe jázd</button></div>
      </div>

      <div id="fleet-view-refueling" class="card mt fleet-view">
        <div class="row right"><button id="add-refueling-btn" class="btn btn-primary">Pridať záznam o tankovaní</button></div>
        <div id="fleet-refueling-container" class="table-wrap mt"></div>
      </div>

      <div id="fleet-view-costs" class="card mt fleet-view">
        <div class="row right"><button id="add-cost-btn" class="btn btn-primary">Pridať nový náklad</button></div>
        <div id="fleet-costs-container" class="table-wrap mt"></div>
      </div>

      <div id="fleet-view-analysis" class="card mt fleet-view">
        <div id="fleet-analysis-container"></div>
      </div>
    </div>
  `;

  // init selecty
  const ySel = section.querySelector('#fleet-year-select');
  const mSel = section.querySelector('#fleet-month-select');
  const vSel = section.querySelector('#fleet-vehicle-select');

  const yNow = new Date().getFullYear();
  for (let y=yNow; y>=yNow-5; y--) ySel.add(new Option(y,y));
  ["Január","Február","Marec","Apríl","Máj","Jún","Júl","August","September","Október","November","December"]
    .forEach((n,i)=> mSel.add(new Option(n, i+1)));
  ySel.value = fleetState.selected_year;
  mSel.value = fleetState.selected_month;

  // prepojenia filtrov
  const reload = () => loadAndRenderFleetData();
  vSel.onchange = reload; ySel.onchange = reload; mSel.onchange = reload;

  // akcie
  section.querySelector('#save-logbook-changes-btn').onclick = handleSaveLogbook;
  section.querySelector('#print-fleet-report-btn').onclick = handlePrintFleetReport;

  // tab kliky – vždy len jedna view
  section.querySelectorAll('.fleet-tabs .tab-btn').forEach(btn=>{
    btn.onclick = () => showFleetTab(btn.dataset.tab);
  });

  // akcie pre modalové tlačidlá
  section.querySelector('#add-refueling-btn').onclick = () =>
    openAddRefuelingModal(document.getElementById('fleet-vehicle-select')?.value);
  section.querySelector('#add-cost-btn').onclick = () => openAddEditCostModal();

  // prvé načítanie
  await loadAndRenderFleetData();
  showFleetTab(fleetState.current_tab || 'logbook');
}

/* -------------------- prepínač tabov (iba jedna view) -------------------- */
function showFleetTab(tab){
  const ids = ['logbook','refueling','costs','analysis'];
  ids.forEach(id => {
    const el = document.getElementById(`fleet-view-${id}`);
    if (el) el.style.display = (id === tab) ? 'block' : 'none';
  });
  document.querySelectorAll('.fleet-tabs .tab-btn').forEach(b=>{
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  fleetState.current_tab = tab;

  // lazy načítania
  if (tab === 'costs')      loadAndRenderFleetCosts();
  if (tab === 'analysis')   loadAndRenderFleetAnalysis();
}

/* -------------------- Data load + render -------------------- */
async function loadAndRenderFleetData(){
  const vSel = document.getElementById('fleet-vehicle-select');
  const ySel = document.getElementById('fleet-year-select');
  const mSel = document.getElementById('fleet-month-select');

  const url = `/api/kancelaria/fleet/getData?vehicle_id=${vSel.value||''}&year=${ySel.value}&month=${mSel.value}`;
  const data = await apiRequest(url);
  fleetState = window.fleetState = { ...fleetState, ...data };

  // fill select vozidiel
  const prev = vSel.value;
  vSel.innerHTML = '';
  (data.vehicles||[]).forEach(v => vSel.add(new Option(`${v.name || 'Vozidlo'} ${v.license_plate ? '('+v.license_plate+')':''}`, v.id)));
  if (data.vehicles?.length){
    if (data.vehicles.some(v => String(v.id)===String(prev))) vSel.value = prev;
    else if (data.selected_vehicle_id) vSel.value = data.selected_vehicle_id;
    fleetState.selected_vehicle_id = Number(vSel.value);
  } else {
    fleetState.selected_vehicle_id = null;
  }

  // prerender logbook/refuelings (costs/analysis na vyžiadanie tabu)
  renderLogbookTable(data.logs, data.selected_year, data.selected_month, data.last_odometer);
  renderRefuelingTable(data.refuelings);

  if (fleetState.current_tab === 'analysis')  loadAndRenderFleetAnalysis();
  if (fleetState.current_tab === 'costs')     loadAndRenderFleetCosts();

  document.querySelector('#fleet-logbook-container input[name="driver"]')?.focus();
}

/* -------------------- Logbook table -------------------- */
function renderLogbookTable(logs, year, month, lastOdometer){
  const el = document.getElementById('fleet-logbook-container');
  const days = new Date(year, month, 0).getDate();
  const byDay = new Map((logs||[]).map(l => [new Date(l.log_date).getDate(), l]));

  let html = `<table class="table fleet" style="table-layout:fixed">
    <colgroup>
      <col style="width:12%"><col style="width:18%"><col style="width:11%"><col style="width:11%">
      <col style="width:10%"><col style="width:12%"><col style="width:12%"><col style="width:9%">
    </colgroup>
    <thead>
      <tr>
        <th>Dátum</th>
        <th>Vodič</th>
        <th class="num">Zač. km</th>
        <th class="num">Kon. km</th>
        <th class="num">Najazdené</th>
        <th class="num">Vývoz kg</th>
        <th class="num">Dovoz kg</th>
        <th class="num">DL</th>
      </tr>
    </thead>
    <tbody>`;

  let prevEnd = Number(lastOdometer)||0;

  for (let d=1; d<=days; d++){
    const log = byDay.get(d) || {};
    const start = (log.start_odometer!=null ? Number(log.start_odometer) : (prevEnd||''));
    const end   = (log.end_odometer!=null   ? Number(log.end_odometer)   : '');
    const driven= (Number.isFinite(end) && Number.isFinite(start) && end>start) ? (end-start) : '';

    html += `<tr data-day="${d}">
      <td>${new Date(year, month-1, d).toLocaleDateString('sk-SK')}</td>
      <td><input class="log-input" name="driver" value="${esc(log.driver||'')}" placeholder="vodič" autocomplete="off"></td>
      <td class="num"><input class="log-input num-input odometer-start" name="start_odometer" type="number" inputmode="numeric" value="${start}"></td>
      <td class="num"><input class="log-input num-input odometer-end"   name="end_odometer"   type="number" inputmode="numeric" value="${end}"></td>
      <td class="num driven-km">${driven}</td>
      <td class="num"><input class="log-input num-input" name="goods_out_kg" type="number" step="0.1" inputmode="decimal" value="${log.goods_out_kg||''}"></td>
      <td class="num"><input class="log-input num-input" name="goods_in_kg"  type="number" step="0.1" inputmode="decimal" value="${log.goods_in_kg||''}"></td>
      <td class="num"><input class="log-input num-input" name="delivery_notes_count" type="number" inputmode="numeric" value="${log.delivery_notes_count||''}"></td>
    </tr>`;

    if (Number.isFinite(end)) prevEnd = end;
    else if (Number.isFinite(start)) prevEnd = start;
  }

  html += `</tbody></table>`;
  el.innerHTML = html;

  if (!el.__wired){
    el.addEventListener('input', onLogbookInput);
    el.addEventListener('change', onLogbookInput);
    el.__wired = true;
  }
}

function onLogbookInput(e){
  const t = e.target;
  if (!(t instanceof HTMLInputElement)) return;

  const tr = t.closest('tr'); if (!tr) return;
  const startEl = tr.querySelector('.odometer-start');
  const endEl   = tr.querySelector('.odometer-end');
  const kmEl    = tr.querySelector('.driven-km');

  if (t === startEl || t === endEl){
    const s = Number(startEl.value||0);
    const v = Number(endEl.value||0);
    kmEl.textContent = (Number.isFinite(s) && Number.isFinite(v) && v>s) ? (v-s) : '';

    // reťazový prepočet nasledujúcich dní
    let next = tr.nextElementSibling, currentEnd = Number.isFinite(v) ? v : (Number.isFinite(s)? s : 0);
    while(next){
      const nStart = next.querySelector('.odometer-start');
      const nEnd   = next.querySelector('.odometer-end');
      if (nStart) nStart.value = currentEnd>0 ? currentEnd : '';
      const ns = Number(nStart?.value||0), ne = Number(nEnd?.value||0);
      const nKm = next.querySelector('.driven-km');
      if (nKm) nKm.textContent = (ne>ns) ? (ne-ns) : '';
      currentEnd = Number.isFinite(ne) && ne>0 ? ne : (Number.isFinite(ns)? ns : currentEnd);
      next = next.nextElementSibling;
    }
  }
}

/* -------------------- Save logbook -------------------- */
async function handleSaveLogbook(){
  const y = fleetState.selected_year, m = fleetState.selected_month, vid = fleetState.selected_vehicle_id;
  if (!vid){ window.showStatus?.("Nie je vybrané vozidlo.", true); return; }

  const rows = document.querySelectorAll('#fleet-logbook-container tbody tr');
  const payload = [];
  rows.forEach(row => {
    const day = String(row.dataset.day).padStart(2,'0');
    const base = { vehicle_id: vid, log_date: `${y}-${String(m).padStart(2,'0')}-${day}` };
    const obj = { ...base };
    row.querySelectorAll('input.log-input').forEach(i => {
      obj[i.name] = i.value.trim()==='' ? null : i.value;
    });
    const km = row.querySelector('.driven-km')?.textContent;
    if (km) obj.km_driven = km;
    if (Object.values(obj).some(v => v!==null && v!=='' && v!==base.log_date)) payload.push(obj);
  });

  if (!payload.length){ window.showStatus?.("Žiadne údaje na uloženie.", false); return; }

  const res = await apiRequest('/api/kancelaria/fleet/saveLog', { method:'POST', body:{ logs: payload } });
  if (res?.error) { window.showStatus?.(res.error, true); return; }
  window.showStatus?.("Kniha jázd uložená.", false);
  await loadAndRenderFleetData();
}

/* -------------------- Refuelings -------------------- */
function renderRefuelingTable(refuelings){
  const c = document.getElementById('fleet-refueling-container');
  if (!refuelings?.length){ c.innerHTML = '<p>Žiadne záznamy o tankovaní.</p>'; return; }
  let html = `<table class="table fleet">
    <colgroup><col style="width:18%"><col style="width:22%"><col style="width:15%"><col style="width:15%"><col style="width:20%"><col style="width:10%"></colgroup>
    <thead><tr><th>Dátum</th><th>Vodič</th><th class="num">Litre</th><th class="num">Cena/L</th><th class="num">Spolu</th><th></th></tr></thead><tbody>`;
  refuelings.forEach(r=>{
    html += `<tr>
      <td>${new Date(r.refueling_date).toLocaleDateString('sk-SK')}</td>
      <td>${esc(r.driver||'')}</td>
      <td class="num">${fx(r.liters,3)}</td>
      <td class="num">${r.price_per_liter!=null ? fx(r.price_per_liter,3):''}</td>
      <td class="num">${r.total_price!=null ? fx(r.total_price):''}</td>
      <td class="num">
        <button class="btn btn-danger" data-action="delete-refueling" data-id="${r.id}">Zmazať</button>
      </td>
    </tr>`;
  });
  c.innerHTML = html + `</tbody></table>`;

  // delegovaný listener (bez inline onclick)
  if (!c.__wired){
    c.addEventListener('click', (e)=>{
      const btn = e.target.closest('button[data-action="delete-refueling"]');
      if (btn){ handleDeleteRefueling(btn.dataset.id); }
    });
    c.__wired = true;
  }
}

async function handleDeleteRefueling(id){
  await apiRequest('/api/kancelaria/fleet/deleteRefueling', { method:'POST', body:{ id } });
  await loadAndRenderFleetData();
}

/* -------------------- Vehicles modal -------------------- */
async function openAddEditVehicleModal(vehicleId=null){
  const tpl = document.getElementById('vehicle-modal-template');
  showModal(vehicleId ? 'Upraviť vozidlo' : 'Pridať vozidlo', () => ({
    html: tpl.innerHTML,
    onReady: () => {
      const f = document.getElementById('vehicle-form');
      if (vehicleId){
        const v = (fleetState.vehicles||[]).find(x => String(x.id)===String(vehicleId));
        if (v){
          f.elements.id.value = v.id;
          f.elements.license_plate.value = v.license_plate || '';
          f.elements.name.value = v.name || '';
          f.elements.type.value = v.type || '';
          f.elements.default_driver.value = v.default_driver || '';
          f.elements.initial_odometer.value = v.initial_odometer || 0;
        }
      } else {
        f.reset();
      }
      f.onsubmit = async (e)=>{
        e.preventDefault();
        const data = Object.fromEntries(new FormData(f).entries());
        const r = await apiRequest('/api/kancelaria/fleet/saveVehicle', { method:'POST', body:data });
        if (r?.error){ window.showStatus?.(r.error, true); return; }
        closeModal();
        await loadAndRenderFleetData(true);
      };
    }
  }));
}

/* -------------------- Costs modal & list -------------------- */
async function loadAndRenderFleetCosts(){
  const vid = fleetState.selected_vehicle_id;
  const box = document.getElementById('fleet-costs-container');
  if (!vid){ box.innerHTML = '<p>Vyber vozidlo.</p>'; return; }
  const costs = await apiRequest(`/api/kancelaria/fleet/getCosts?vehicle_id=${vid}`);
  fleetState.costs = costs||[];
  if (!costs?.length){ box.innerHTML = '<p>Žiadne náklady.</p>'; return; }

  let html = `<table class="table fleet">
    <colgroup><col style="width:40%"><col style="width:15%"><col style="width:25%"><col style="width:10%"><col style="width:10%"></colgroup>
    <thead><tr><th>Názov</th><th>Typ</th><th>Platnosť</th><th class="num">Mesačne (€)</th><th></th></tr></thead><tbody>`;
  costs.forEach(c=>{
    const valid = c.valid_to ? `${new Date(c.valid_from).toLocaleDateString('sk-SK')} – ${new Date(c.valid_to).toLocaleDateString('sk-SK')}`
                             : `od ${new Date(c.valid_from).toLocaleDateString('sk-SK')}`;
    html += `<tr>
      <td>${esc(c.cost_name)}</td>
      <td>${esc(c.cost_type)}</td>
      <td>${valid}</td>
      <td class="num">${fx(c.monthly_cost)}</td>
      <td class="num">
        <button class="btn" data-action="edit-cost" data-payload='${JSON.stringify(c).replace(/"/g,"&quot;")}'>Upraviť</button>
        <button class="btn btn-danger" data-action="delete-cost" data-id="${c.id}">Zmazať</button>
      </td>
    </tr>`;
  });
  box.innerHTML = html + `</tbody></table>`;

  // delegovaný listener
  if (!box.__wired){
    box.addEventListener('click', (e)=>{
      const del = e.target.closest('button[data-action="delete-cost"]');
      if (del){ handleDeleteCost(del.dataset.id); return; }
      const edit = e.target.closest('button[data-action="edit-cost"]');
      if (edit){
        try { openAddEditCostModal(JSON.parse(edit.dataset.payload)); }
        catch{ /* ignore */ }
      }
    });
    box.__wired = true;
  }
}

async function openAddEditCostModal(cost=null){
  const vid = fleetState.selected_vehicle_id;
  if (!vid && !cost?.vehicle_id){ window.showStatus?.("Vyber vozidlo.", true); return; }
  const html = `
    <form id="cost-form" class="form grid-2" autocomplete="off">
      <input type="hidden" name="id" value="${cost?.id||''}">
      <input type="hidden" name="vehicle_id" value="${cost?.vehicle_id||vid||''}">
      <label class="col-span-2">Názov <input name="cost_name" value="${esc(cost?.cost_name||'')}" required autocomplete="off"></label>
      <label>Typ
        <select name="cost_type" required>
          ${['MZDA','POISTENIE','SERVIS','PNEUMATIKY','DIALNICNA','SKODA','INE'].map(t=>`<option value="${t}" ${cost?.cost_type===t?'selected':''}>${t}</option>`).join('')}
        </select>
      </label>
      <label>Mesačná suma (€) <input name="monthly_cost" type="number" step="0.01" value="${cost?.monthly_cost||''}" required inputmode="decimal"></label>
      <label>Platné od <input name="valid_from" type="date" value="${cost? new Date(cost.valid_from).toISOString().split('T')[0] : ''}" required></label>
      <label>Platné do <input name="valid_to" type="date" value="${cost?.valid_to? new Date(cost.valid_to).toISOString().split('T')[0] : ''}"></label>
      <div class="col-span-2" style="display:flex;gap:10px;align-items:center">
        <input id="is-vehicle-specific" type="checkbox" ${cost?.vehicle_id||vid?'checked':''} style="width:auto">
        <label for="is-vehicle-specific" style="margin:0">Viazať na toto vozidlo</label>
      </div>
      <div class="col-span-2"><button class="btn btn-primary" style="width:100%">${cost?'Uložiť zmeny':'Vytvoriť náklad'}</button></div>
    </form>`;
  showModal(cost?'Upraviť náklad':'Pridať náklad', { html, onReady: ()=>{
    const f = document.getElementById('cost-form'); const chk = document.getElementById('is-vehicle-specific');
    chk.onchange = () => { f.elements.vehicle_id.value = chk.checked ? (vid||'') : ''; };
    if (!cost) f.elements.valid_from.valueAsDate = new Date();
    f.onsubmit = async (e)=>{
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f).entries());
      const r = await apiRequest('/api/kancelaria/fleet/saveCost', { method:'POST', body:data });
      if (r?.error) { window.showStatus?.(r.error, true); return; }
      closeModal();
      await loadAndRenderFleetAnalysis(); await loadAndRenderFleetCosts();
    };
  }});
}

async function handleDeleteCost(id){
  await apiRequest('/api/kancelaria/fleet/deleteCost', { method:'POST', body:{ id } });
  await loadAndRenderFleetAnalysis();
  await loadAndRenderFleetCosts();
}

/* -------------------- Analysis + Report -------------------- */
async function loadAndRenderFleetAnalysis(){
  const { selected_vehicle_id:vid, selected_year:y, selected_month:m } = fleetState;
  const box = document.getElementById('fleet-analysis-container');
  if (!vid){ box.innerHTML='<p>Vyber vozidlo.</p>'; return; }
  const data = await apiRequest(`/api/kancelaria/fleet/getAnalysis?vehicle_id=${vid}&year=${y}&month=${m}`);
  fleetState.analysis = data;
  box.innerHTML = `
    <div class="grid-2">
      <div class="card"><h4>Celkové náklady</h4><div><strong>${fx(data.total_costs)}</strong> €</div></div>
      <div class="card"><h4>Celkovo najazdené</h4><div><strong>${data.total_km}</strong> km</div></div>
      <div class="card"><h4>Náklady na 1 km</h4><div><strong>${fx(data.cost_per_km)}</strong> €</div></div>
      <div class="card"><h4>Priemerná spotreba</h4><div><strong>${fx(data.avg_consumption)}</strong> L/100km</div></div>
      <div class="card"><h4>Celkový vývoz</h4><div><strong>${fx(data.total_goods_out_kg)}</strong> kg</div></div>
      <div class="card"><h4>Cena na 1 kg</h4><div><strong>${fx(data.cost_per_kg_goods)}</strong> €</div></div>
    </div>`;
}

async function handlePrintFleetReport(){
  const { selected_vehicle_id:vid, selected_year:y, selected_month:m } = fleetState;
  if (!vid){ window.showStatus?.("Vyber vozidlo.", true); return; }
  window.open(`/report/fleet?vehicle_id=${vid}&year=${y}&month=${m}`, '_blank');
}

/* --- sprístupnenie pre externé volania (ak ich niekde používaš) --- */
window.initializeFleetModule = initializeFleetModule;
window.openAddRefuelingModal = openAddRefuelingModal;
window.openAddEditCostModal  = openAddEditCostModal;
window.handleDeleteCost      = handleDeleteCost;
window.handleDeleteRefueling = handleDeleteRefueling;

/* -------------------- Modal: Pridať tankovanie -------------------- */
function openAddRefuelingModal(vehicleId){
  const tpl = document.getElementById('refueling-modal-template');
  if (!tpl) { window.showStatus?.("Chýba template #refueling-modal-template v HTML.", true); return; }
  const vid = vehicleId || document.getElementById('fleet-vehicle-select')?.value;
  if (!vid) { window.showStatus?.("Najprv vyberte vozidlo.", true); return; }

  showModal('Pridať tankovanie', () => ({
    html: tpl.innerHTML,
    onReady: () => {
      const f = document.getElementById('refueling-form');
      f.elements.vehicle_id.value = vid;
      f.elements.refueling_date.valueAsDate = new Date();
      const v = (window.fleetState?.vehicles || []).find(x => String(x.id) === String(vid));
      if (v) f.elements.driver.value = v.default_driver || '';
      f.onsubmit = async (e)=>{
        e.preventDefault();
        const data = Object.fromEntries(new FormData(f).entries());
        const r = await apiRequest('/api/kancelaria/fleet/saveRefueling', { method:'POST', body:data });
        if (r?.error) { window.showStatus?.(r.error, true); return; }
        closeModal();
        await loadAndRenderFleetData();
      };
    }
  }));
}
