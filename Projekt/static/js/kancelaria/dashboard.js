// /static/js/kancelaria/dashboard.js — Dashboard bez horných KPI, s kompatibilným initom
(function(){
  // ---------- helpers ----------
  const esc = s => (s==null ? '' : String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m])) );
  const fx  = (n,d=2) => {
    const x = Number(n);
    return Number.isFinite(x) ? x.toLocaleString('sk-SK',{minimumFractionDigits:d,maximumFractionDigits:d}) : (0).toFixed(d);
  };
  function setStatus(msg, ok=true){
    const el = document.getElementById('dash-status');
    if (el) el.innerHTML = msg ? `<span style="color:${ok?'#0a8':'#c33'}">${esc(msg)}</span>` : '';
  }

  async function postJSON(url, body){
    const meta = document.querySelector('meta[name="csrf-token"]');
    const cookie = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    const token = (meta && meta.content) ? meta.content : (cookie ? decodeURIComponent(cookie[1]) : '');
    const r = await fetch(url, {
      method:'POST',
      credentials:'same-origin',
      headers:{ 'Content-Type':'application/json', 'Accept':'application/json', 'X-CSRF-Token': token },
      body: JSON.stringify({ ...(body||{}), csrf_token: token })
    });
    const t = await r.text(); try { return JSON.parse(t); } catch { throw new Error(t); }
  }

  function fmtDate(v){
    if(!v) return '';
    const d=new Date(v);
    return isNaN(d)? String(v) : d.toLocaleString('sk-SK');
  }

  // Google Charts
  function ensureChartsLoaded(){
    return new Promise((resolve)=>{
      function onReady(){
        try{
          google.charts.load('current',{packages:['corechart']});
          google.charts.setOnLoadCallback(resolve);
        }catch{ resolve(); }
      }
      if (window.google && google.charts){ onReady(); return; }
      const s=document.createElement('script'); s.src='https://www.gstatic.com/charts/loader.js';
      s.onload=onReady; s.onerror=()=>resolve(); document.head.appendChild(s);
    });
  }

  // ---------- render: nízke zásoby ----------
  function renderPurchaseTables(dash){
    // suroviny
    const raw = Array.isArray(dash?.lowStockRaw) ? dash.lowStockRaw : [];
    const boxRaw = document.getElementById('dash-buy-raw');
    if (boxRaw){
      if (!raw.length) boxRaw.innerHTML = '<p>Všetky výrobné suroviny sú nad minimom.</p>';
      else {
        let t = '<table class="table"><thead><tr><th>Surovina</th><th class="num">Stav</th><th class="num">Min.</th><th class="num">Navrhnúť</th></tr></thead><tbody>';
        raw.forEach(it=>{
          const q = Number(it.quantity ?? it.currentStock ?? 0), min = Number(it.minStock ?? 0), need = Math.max(0, min - q);
          t += `<tr><td>${esc(it.name||'')}</td><td class="num">${fx(q,3)}</td><td class="num">${fx(min,3)}</td><td class="num"><strong>${fx(need,3)}</strong></td></tr>`;
        });
        boxRaw.innerHTML = t + '</tbody></table>';
      }
    }
    // hotové/tovar
    const goods = dash?.lowStockGoods || {};
    const boxGoods = document.getElementById('dash-buy-goods');
    if (boxGoods){
      if (!goods || !Object.keys(goods).length) boxGoods.innerHTML = '<p>Expedičný tovar je nad minimom.</p>';
      else {
        let html = '';
        Object.keys(goods).forEach(cat=>{
          const items = goods[cat] || [];
          let t = '<table class="table"><thead><tr><th>Produkt</th><th class="num">Stav</th><th class="num">Min.</th><th class="num">Navrhnúť</th></tr></thead><tbody>';
          items.forEach(it=>{
            const q = Number(it.quantity ?? it.currentStock ?? 0), min = Number(it.minStock ?? 0), need = Math.max(0, min - q);
            t += `<tr><td>${esc(it.name||'')}</td><td class="num">${fx(q,3)}</td><td class="num">${fx(min,3)}</td><td class="num"><strong>${fx(need,3)}</strong></td></tr>`;
          });
          html += `<h5 style="margin:12px 0 6px">${esc(cat)}</h5>${t}</tbody></table>`;
        });
        boxGoods.innerHTML = html;
      }
    }
  }

  // ---------- render: Najbližšie promo akcie (5 dní vopred) ----------
  async function renderPromotionsCard(){
    const body = document.getElementById('dash-promos-body');
    if (!body) return;
    try{
      const data = await postJSON('/api/kancelaria/akcie/dashboard', {});
      const items = data?.items || [];
      body.innerHTML = items.length
        ? `<ul class="list" style="margin:.5rem 0 0 1rem">${items.map(x=>`<li>${esc(x.message||'')}</li>`).join('')}</ul>`
        : `<p class="muted">Žiadne akcie v horizonte 5 dní.</p>`;
    }catch(e){
      body.innerHTML = `<p class="muted">Akcie nie sú dostupné.</p>`;
    }
  }

  // ---------- render: B2B/B2C tabuľky + registrácie ----------
  function renderB2B(rows){
    const tb = document.querySelector('#tbl-b2b tbody');
    if (!tb) return;
    if (!Array.isArray(rows) || !rows.length){ tb.innerHTML = `<tr><td colspan="6">Žiadne objednávky.</td></tr>`; return; }
    tb.innerHTML = rows.map(r => `
      <tr>
        <td>${esc(r.cislo_objednavky || r.id)}</td>
        <td>${esc(r.nazov_firmy || '')}</td>
        <td>${fmtDate(r.datum_objednavky)}</td>
        <td>${esc(r.pozadovany_datum_dodania || '')}</td>
        <td>${esc(r.status || '')}</td>
        <td class="num">${fx(r.celkova_suma||0, 2)}</td>
      </tr>`).join('');
  }
  function renderB2C(rows){
    const tb = document.querySelector('#tbl-b2c tbody');
    if (!tb) return;
    if (!Array.isArray(rows) || !rows.length){ tb.innerHTML = `<tr><td colspan="4">Žiadne objednávky.</td></tr>`; return; }
    tb.innerHTML = rows.map(r => `
      <tr>
        <td>${esc(r.id)}</td>
        <td>${fmtDate(r.datum)}</td>
        <td class="num">${fx(r.body||0, 0)}</td>
        <td class="num">${fx(r.celkom_s_dph||0, 2)}</td>
      </tr>`).join('');
  }
  function renderRegsB2B(rows){
    const ul = document.querySelector('#list-b2b-regs');
    if (!ul) return;
    if (!Array.isArray(rows) || !rows.length){ ul.innerHTML = `<li>Žiadne nové B2B registrácie.</li>`; return; }
    ul.innerHTML = rows.map(r => `
      <li>
        <strong>${esc(r.nazov_firmy || r.name || '(bez názvu)')}</strong><br>
        <small>${esc(r.email||'')}${(r.email && r.telefon)?' • ':''}${esc(r.telefon||'')}</small><br>
        <small>${fmtDate(r.datum_registracie || r.created_at)}</small>
      </li>`).join('');
  }
  function renderRegsB2C(rows){
    const ul = document.querySelector('#list-b2c-regs');
    if (!ul) return;
    if (!Array.isArray(rows) || !rows.length){ ul.innerHTML = `<li>Žiadne nové B2C registrácie.</li>`; return; }
    ul.innerHTML = rows.map(r => `
      <li>
        <strong>${esc(r.name || r.nazov_firmy || '(bez názvu)')}</strong><br>
        <small>${esc(r.email||'')}${(r.email && r.phone)?' • ':''}${esc(r.phone||'')}</small><br>
        <small>${fmtDate(r.created_at)}</small>
      </li>`).join('');
  }

  // ---------- render: ziskovosť vs. náklady ----------
  async function renderProfitVsCosts(year, month){
    const box = document.getElementById('dash-profit-costs');
    if (!box) return;
    try{
      const [p, c] = await Promise.allSettled([
        postJSON('/api/kancelaria/profitability/getData', {year, month}),
        postJSON('/api/kancelaria/costs/getDashboard',   {year, month})
      ]);
      let opProfit = 0, totalCosts = 0, companyNet = 0;
      if (p.status==='fulfilled' && p.value?.calculations) opProfit = Number(p.value.calculations.total_profit||0);
      if (c.status==='fulfilled' && c.value?.summary){
        totalCosts = Number(c.value.summary.total_costs||0);
        companyNet = Number(c.value.summary.company_net || (opProfit-totalCosts));
      } else companyNet = opProfit - totalCosts;

      const kpi = (label, value, sub='') =>
        `<div class="stat-card"><div class="stat-title">${esc(label)}</div><div class="stat-value">${esc(value)}</div>${sub?`<div class="stat-sub">${esc(sub)}</div>`:''}</div>`;

      box.innerHTML = `
        <div class="cards">
          ${kpi('Ziskovosť (Operating profit)', '€ '+fx(opProfit,2))}
          ${kpi('Externé náklady (costs)', '€ '+fx(totalCosts,2))}
          ${kpi('Company NET', '€ '+fx(companyNet,2))}
        </div>`;
    }catch{
      box.innerHTML = '<p class="muted">Modul ziskovosť/náklady zatiaľ nie je nakonfigurovaný.</p>';
    }
  }

  // ---------- render: TOP5 + graf ----------
  function renderTopProducts(items){
    const box = document.getElementById('dash-top-products');
    if (!box) return;
    if (!Array.isArray(items) || !items.length){ box.innerHTML = '<p>Žiadne dáta pre TOP produkty (30 dní).</p>'; return; }
    let t = '<table class="table"><thead><tr><th>Produkt</th><th class="num">Vyrobené (kg)</th></tr></thead><tbody>';
    items.forEach(it=> t += `<tr><td>${esc(it.name||'')}</td><td class="num">${fx(it.total||0,3)}</td></tr>`);
    box.innerHTML = t + '</tbody></table>';
  }
  async function drawProductionChart(ts){
    const box = document.getElementById('dash-production-chart');
    if (!box) return;
    if (!Array.isArray(ts) || !ts.length){ box.innerHTML = '<p>Žiadny graf výroby (30 dní).</p>'; return; }
    await ensureChartsLoaded();
    if (!window.google || !google.charts){ box.innerHTML = '<p>Grafický modul nie je dostupný.</p>'; return; }
    const dt = new google.visualization.DataTable();
    dt.addColumn('date', 'Dátum'); dt.addColumn('number', 'Vyrobené kg');
    ts.forEach(r=>{
      const d = r.production_date ? new Date(r.production_date) : null;
      if (d) dt.addRow([d, parseFloat(r.total_kg ?? 0)]);
    });
    const options = { legend:'none', vAxis:{title:'kg', minValue:0}, hAxis:{format:'d.M'} };
    new google.visualization.ColumnChart(box).draw(dt, options);
  }

  // ---------- init shell + load ----------
  async function loadAndRender(year, month){
    setStatus('Načítavam…');
    try{
      const d = await postJSON('/api/kancelaria/getDashboardData', {});
      renderPurchaseTables(d);
      renderB2B(d.b2b_orders || []);
      renderB2C(d.b2c_orders || []);
      renderRegsB2B(d.new_b2b_regs || []);
      renderRegsB2C(d.new_b2c_regs || []);
      renderTopProducts(d.topProducts || []);
      await drawProductionChart(d.timeSeriesData || []);
      await renderProfitVsCosts(year, month);
      await renderPromotionsCard();               // ← karta „Najbližšie akcie“
      setStatus('');
    }catch(e){
      console.error(e);
      setStatus('Nepodarilo sa načítať dáta.', false);
    }
  }

  function buildShell(){
    const section = document.getElementById('section-dashboard');
    if (!section) return null;
    const yNow = new Date().getFullYear(), mNow = new Date().getMonth()+1;

    section.innerHTML = `
      <div class="card">
        <div class="row wrap" style="gap:12px; align-items:flex-end; justify-content:center">
          <label>Rok <select id="dash-year"></select></label>
          <label>Mesiac <select id="dash-month"></select></label>
          <button id="dash-refresh" class="btn">Načítať</button>
        </div>

        <div id="dash-status" class="row" style="justify-content:center;margin-top:8px;min-height:22px;"></div>
      </div>

      <!-- Karta: Najbližšie akcie -->
      <div class="card mt" id="dash-promos">
        <h3 class="card-title">Najbližšie akcie</h3>
        <div id="dash-promos-body"></div>
      </div>

      <div class="grid-dashboard" style="display:grid;grid-template-columns:1.5fr 1.5fr 1fr;gap:16px;align-items:start;margin-top:12px">
        <article class="card">
          <h3 class="card-title">B2B objednávky</h3>
          <div class="table-wrap">
            <table class="table" id="tbl-b2b">
              <thead><tr><th>Číslo</th><th>Zákazník</th><th>Dátum</th><th>Dodanie</th><th>Stav</th><th class="num">Celkom (€)</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </article>

        <article class="card">
          <h3 class="card-title">B2C objednávky</h3>
          <div class="table-wrap">
            <table class="table" id="tbl-b2c">
              <thead><tr><th>ID</th><th>Dátum</th><th class="num">Body</th><th class="num">Celkom s DPH (€)</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </article>

        <aside class="card">
          <h3 class="card-title">Nové registrácie</h3>
          <div class="mt">
            <h4 class="muted">B2B (na schválenie)</h4>
            <ul class="list" id="list-b2b-regs"></ul>
          </div>
          <div class="mt">
            <h4 class="muted">B2C (bez schválenia)</h4>
            <ul class="list" id="list-b2c-regs"></ul>
          </div>
        </aside>
      </div>

      <div class="card mt"><h3>Návrh nákupu – Výroba (suroviny)</h3><div id="dash-buy-raw"></div></div>
      <div class="card mt"><h3>Návrh nákupu – Expedícia (tovar)</h3><div id="dash-buy-goods"></div></div>

      <div class="card mt"><h3>Ziskovosť vs. Náklady (mesiac)</h3><div id="dash-profit-costs"></div></div>

      <div class="card mt">
        <h3>TOP 5 produktov (30 dní)</h3>
        <div id="dash-top-products" class="table-container"></div>
        <h3 style="margin-top:1rem">Graf výroby (30 dní)</h3>
        <div id="dash-production-chart" style="width:100%;height:320px"></div>
      </div>
    `;

    // naplň roky/mesiace
    const ySel = document.getElementById('dash-year');
    const mSel = document.getElementById('dash-month');
    for (let y=yNow; y>=yNow-5; y--) ySel.add(new Option(y, y));
    ["Január","Február","Marec","Apríl","Máj","Jún","Júl","August","September","Október","November","December"]
      .forEach((n,i)=> mSel.add(new Option(n, i+1)));
    ySel.value = String(yNow); mSel.value = String(mNow);

    document.getElementById('dash-refresh').onclick = () => loadAndRender(Number(ySel.value), Number(mSel.value));
    return {yNow, mNow};
  }

  // ---------- init once (kompatibilita s volaním initializeDashboardModule) ----------
  let __inited = false;
  async function initOnce(){
    if (__inited) return;
    __inited = true;
    const section = document.getElementById('section-dashboard');
    if (!section) return;
    const init = buildShell();
    if (init) await loadAndRender(init.yNow, init.mNow);
  }

  // auto-init po načítaní DOM
  document.addEventListener('DOMContentLoaded', initOnce);

  // kompatibilné API (ak niekde inde voláš window.initializeDashboardModule())
  window.initializeDashboardModule = initOnce;
})();
