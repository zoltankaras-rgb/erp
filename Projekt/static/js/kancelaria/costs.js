// static/js/kancelaria/costs.js — komplet (rozdelené pod-karty, null-safe, profi status bar)
function initializeCostsModule(){
  const root = document.getElementById('section-costs');
  if (!root) return;

  // ====== STATE ======
  const costsState = window.costsState = {
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
    activeTab: 'energy',
    activeEnergyTab: 'electricity', // 'electricity' | 'gas' | 'water'
    data: null,
    dash: null
  };

  // ====== HELPERS ======
  const apiPost = async (url, body) => {
    if (window.apiRequest) return await apiRequest(url, { method:'POST', body });
    const r = await fetch(url, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      credentials:'same-origin',
      body: JSON.stringify(body || {})
    });
    const text = await r.text();
    try { return JSON.parse(text); }
    catch { throw new Error(`Neočakávaný formát odpovede: ${text.slice(0,60)}…`); }
  };
  const fx = (n, d=2) => {
    const x = Number(n);
    return Number.isFinite(x) ? x.toFixed(d) : Number(0).toFixed(d);
  };
  const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  const $ = (id) => document.getElementById(id);

  // ====== SHELL UI ======
  root.innerHTML = `
    <div class="card">
      <div class="row wrap" style="gap:12px; align-items:flex-end; justify-content:center">
        <label>Rok <select id="cost-year"></select></label>
        <label>Mesiac <select id="cost-month"></select></label>
      </div>
      <div class="row wrap" style="gap:10px; justify-content:center; margin-top:12px">
        <button data-tab="energy" class="btn active">Energie</button>
        <button data-tab="hr" class="btn">HR (mzdy/odvody)</button>
        <button data-tab="op" class="btn">Prevádzka</button>
        <button data-tab="cats" class="btn">Kategórie</button>
      </div>
      <div id="cost-status" class="row" style="justify-content:center;margin-top:8px;min-height:22px;"></div>
    </div>
    <div id="cost-body"></div>
  `;

  const status = (msg, ok=true) => {
    const el = $('cost-status'); if (!el) return;
    el.innerHTML = msg ? `<span style="color:${ok ? '#0a8' : '#c33'}">${msg}</span>` : '';
  };

  // ====== YEAR/MONTH ======
  const ySel = $('cost-year'); const mSel = $('cost-month');
  const yNow = new Date().getFullYear();
  for (let y=yNow; y>=yNow-5; y--) ySel.add(new Option(y, y));
  ["Január","Február","Marec","Apríl","Máj","Jún","Júl","August","September","Október","November","December"]
    .forEach((n,i)=> mSel.add(new Option(n, i+1)));
  ySel.value = costsState.year; mSel.value = costsState.month;

  ySel.onchange = async ()=>{ costsState.year = Number(ySel.value); await loadAll(); };
  mSel.onchange = async ()=>{ costsState.month = Number(mSel.value); await loadAll(); };

  // ====== TABS ======
  root.querySelectorAll('button[data-tab]').forEach(b=>{
    b.onclick = ()=> {
      root.querySelectorAll('button[data-tab]').forEach(x=>x.classList.remove('active'));
      b.classList.add('active');
      costsState.activeTab = b.dataset.tab;
      render();
    };
  });

  // ====== LOADERS ======
  async function loadData(){
    try{
      status('Načítavam…', true);
      const res = await apiPost('/api/kancelaria/costs/getData', { year: costsState.year, month: costsState.month });
      if (res?.error) { status(res.error, false); costsState.data = null; return; }
      costsState.data = res || {};
      status('');
    }catch(e){ status(String(e.message||e), false); }
  }
  async function loadDash(){
    try{
      const res = await apiPost('/api/kancelaria/costs/getDashboard', { year: costsState.year, month: costsState.month });
      costsState.dash = res || {};
    }catch{ /* dashboard nie je kritický */ }
  }
  async function loadAll(){ await loadData(); await loadDash(); render(); }

  // ====== RENDER SWITCH ======
  function render(){
    const host = $('cost-body');
    const title = (t)=>`<div class="section-header"><h2>Náklady – ${t} (${String(costsState.month).padStart(2,'0')}/${costsState.year})</h2></div>`;
    if (costsState.activeTab==='energy'){ host.innerHTML = title('Energie') + renderEnergy(); wireEnergy(); return; }
    if (costsState.activeTab==='hr'){     host.innerHTML = title('HR') + renderHR(); wireHR(); return; }
    if (costsState.activeTab==='op'){     host.innerHTML = title('Prevádzka') + renderOP(); wireOP(); return; }
    if (costsState.activeTab==='cats'){   host.innerHTML = title('Kategórie') + renderCats(); wireCats(); return; }
  }

  // ====== ENERGY (view) ======
  function renderEnergy(){
    const e   = (costsState.data?.energy)||{};
    const el  = e.electricity || {};
    const gas = e.gas         || {};
    const w   = e.water       || {};
    const comp= e.computed    || {};
    const elc = comp.electricity || {};
    const gsc = comp.gas         || {};
    const wtc = comp.water       || {};

    const style = `
      <style>
        .energy-tabs{display:flex;gap:8px;justify-content:center;margin-bottom:10px}
        .energy-tabs .btn.active{background:#111;color:#fff}
        .grid-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
        .kpi .lbl{opacity:.7;font-size:12px}
        .kpi .val{font-size:18px;font-weight:600}
        table.table{width:100%;border-collapse:collapse}
        table.table th, table.table td{border:1px solid #ddd;padding:6px}
        .num{text-align:right}
        .btn[disabled]{opacity:.6;pointer-events:none}
      </style>`;

    const pane = (()=> {
      if (costsState.activeEnergyTab==='electricity'){
        return `
          <div class="card">
            <h3>Elektrina</h3>
            <div class="form-grid form-3">
              <label>Začiatočný stav (kWh) <input id="el-start" type="number" step="0.001" value="${el.meter_start_kwh??''}"></label>
              <label>Koncový stav (kWh)     <input id="el-end"   type="number" step="0.001" value="${el.meter_end_kwh??''}"></label>
              <label>Cena bez DPH / kWh (€) <input id="el-price-net" type="number" step="0.000001" value="${el.unit_price_kwh_net??''}"></label>
              <label>DPH (%)                <input id="el-vat"       type="number" step="0.01" value="${el.vat_rate??20}"></label>
            </div>
            <div class="grid-3" style="margin-top:10px">
              <div class="kpi"><div class="lbl">Spotreba (kWh)</div><div class="val" id="el-cons">${fx(elc.consumption_kwh,3)}</div></div>
              <div class="kpi"><div class="lbl">Jedn. cena s DPH (€/kWh)</div><div class="val" id="el-unit-br">${fx(elc.unit_price_kwh_gross,6)}</div></div>
              <div class="kpi"><div class="lbl">Celkom s DPH</div><div class="val" id="el-total-br">€ ${fx(elc.total_gross_eur,2)}</div></div>
            </div>
            <div class="row right mt"><button id="el-save" class="btn btn-primary">Uložiť elektrinu</button></div>

            <div class="card mt">
              <h4>Prehľad</h4>
              <table class="table">
                <thead><tr><th>Ukazovateľ</th><th class="num">Hodnota</th></tr></thead>
                <tbody>
                  <tr><td>Spotreba (kWh)</td><td class="num" id="t-el-cons">${fx(elc.consumption_kwh,3)}</td></tr>
                  <tr><td>Priemer denne (kWh/deň)</td><td class="num" id="t-el-avgk">${fx(elc.avg_daily_kwh,3)}</td></tr>
                  <tr><td>Celková cena s DPH</td><td class="num" id="t-el-total">€ ${fx(elc.total_gross_eur,2)}</td></tr>
                  <tr><td>Priemerná cena s DPH (€/kWh)</td><td class="num" id="t-el-avgp">€ ${fx(elc.avg_unit_price_gross,6)}</td></tr>
                </tbody>
              </table>
            </div>
          </div>`;
      }
      if (costsState.activeEnergyTab==='gas'){
        return `
          <div class="card">
            <h3>Plyn</h3>
            <div class="form-grid form-3">
              <label>Začiatočný stav (m³)      <input id="gas-start" type="number" step="0.001" value="${gas.meter_start_m3??''}"></label>
              <label>Koncový stav (m³)          <input id="gas-end"   type="number" step="0.001" value="${gas.meter_end_m3??''}"></label>
              <label>Koeficient (kWh/m³)        <input id="gas-coeff" type="number" step="0.0001" value="${gas.coeff_kwh_per_m3??10.5000}"></label>
              <label>Cena bez DPH / kWh (€)     <input id="gas-price-net" type="number" step="0.000001" value="${gas.unit_price_kwh_net??''}"></label>
              <label>DPH (%)                    <input id="gas-vat"       type="number" step="0.01" value="${gas.vat_rate??20}"></label>
            </div>
            <div class="grid-3" style="margin-top:10px">
              <div class="kpi"><div class="lbl">Spotreba (m³)</div><div class="val" id="gas-m3">${fx(gsc.consumption_m3,3)}</div></div>
              <div class="kpi"><div class="lbl">Spotreba (kWh)</div><div class="val" id="gas-kwh">${fx(gsc.consumption_kwh,3)}</div></div>
              <div class="kpi"><div class="lbl">Celkom s DPH</div><div class="val" id="gas-total-br">€ ${fx(gsc.total_gross_eur,2)}</div></div>
            </div>
            <div class="row right mt"><button id="gas-save" class="btn btn-primary">Uložiť plyn</button></div>

            <div class="card mt">
              <h4>Prehľad</h4>
              <table class="table">
                <thead><tr><th>Ukazovateľ</th><th class="num">Hodnota</th></tr></thead>
                <tbody>
                  <tr><td>Spotreba (m³)</td><td class="num" id="t-gas-m3">${fx(gsc.consumption_m3,3)}</td></tr>
                  <tr><td>Spotreba (kWh)</td><td class="num" id="t-gas-kwh">${fx(gsc.consumption_kwh,3)}</td></tr>
                  <tr><td>Celková cena s DPH</td><td class="num" id="t-gas-total">€ ${fx(gsc.total_gross_eur,2)}</td></tr>
                </tbody>
              </table>
            </div>
          </div>`;
      }
      // Voda
      return `
        <div class="card">
          <h3>Voda</h3>
         <div class="form-grid form-3">
            <label>Začiatočný stav (m³)  <input id="w-prev" type="number" step="0.001" value="${w.meter_prev??''}"></label>
            <label>Koncový stav (m³)      <input id="w-curr" type="number" step="0.001" value="${w.meter_curr??''}"></label>
            <label>Cena bez DPH / m³ (€)  <input id="w-price-net" type="number" step="0.000001" value="${w.unit_price??''}"></label>
            <label>DPH (%)                <input id="w-vat" type="number" step="0.01" value="${w.vat_rate??20}"></label>
          </div>
          <div class="grid-3" style="margin-top:10px">
            <div class="kpi"><div class="lbl">Spotreba (m³)</div><div class="val" id="w-m3">${fx(wtc.delta_m3,3)}</div></div>
            <div class="kpi"><div class="lbl">Celkom s DPH</div><div class="val" id="w-total-br">€ ${fx(wtc.total_gross_eur,2)}</div></div>
          </div>
          <div class="row right mt"><button id="w-save" class="btn btn-primary">Uložiť vodu</button></div>

          <div class="card mt">
            <h4>Prehľad</h4>
            <table class="table">
              <thead><tr><th>Ukazovateľ</th><th class="num">Hodnota</th></tr></thead>
              <tbody>
                <tr><td>Spotreba (m³)</td><td class="num" id="t-w-m3">${fx(wtc.delta_m3,3)}</td></tr>
                <tr><td>Celková cena s DPH</td><td class="num" id="t-w-total">€ ${fx(wtc.total_gross_eur,2)}</td></tr>
              </tbody>
            </table>
          </div>
        </div>`;
    })();

    const annual = `
      <div class="card mt">
        <h3>Ročný prehľad</h3>
        <div class="row wrap" style="gap:10px; align-items:end">
          <label>Rok
            <select id="annual-year"></select>
          </label>
          <label>Typ
            <select id="annual-type">
              <option value="electricity">Elektrina</option>
              <option value="gas">Plyn</option>
              <option value="water">Voda</option>
              <option value="all">Všetko</option>
            </select>
          </label>
          <button id="annual-load" class="btn">Načítať</button>
          <button id="annual-print" class="btn">Tlačiť report</button>
        </div>
        <div id="annual-table" class="mt"></div>
      </div>
    `;

    return `
      ${style}
      <div class="card">
        <div class="energy-tabs">
          <button class="btn ${costsState.activeEnergyTab==='electricity'?'active':''}" data-energy="electricity">Elektrina</button>
          <button class="btn ${costsState.activeEnergyTab==='gas'?'active':''}"         data-energy="gas">Plyn</button>
          <button class="btn ${costsState.activeEnergyTab==='water'?'active':''}"       data-energy="water">Voda</button>
        </div>
        <div id="energy-pane">${pane}</div>
      </div>
      ${annual}
    `;
  }

  // ====== ENERGY (wiring) ======
  function wireEnergy(){
    const days = new Date(costsState.year, costsState.month, 0).getDate();

    // prepínač pod-kariet
    document.querySelectorAll('.energy-tabs [data-energy]').forEach(btn=>{
      btn.onclick = ()=>{
        document.querySelectorAll('.energy-tabs .btn').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        costsState.activeEnergyTab = btn.dataset.energy;
        // Prekresli len kartu Energie
        const host = document.getElementById('cost-body');
        if (!host) return;
        host.innerHTML = `<div class="section-header"><h2>Náklady – Energie (${String(costsState.month).padStart(2,'0')}/${costsState.year})</h2></div>` + renderEnergy();
        wireEnergy();
      };
    });

    // Recalc helpers
    const recalcElectricity = ()=>{
      const s = +(document.getElementById('el-start')?.value||0);
      const e = +(document.getElementById('el-end')?.value||0);
      const net= +(document.getElementById('el-price-net')?.value||0);
      const vat= +(document.getElementById('el-vat')?.value||0);
      const cons = Math.max(0, e - s), unitBr = net*(1+vat/100), totBr = cons*unitBr;
      const avgK = cons/(days||1), avgE = totBr/(days||1), avgP = cons>0? totBr/cons : unitBr;
      setText('el-cons', fx(cons,3)); setText('el-unit-br', fx(unitBr,6)); setText('el-total-br','€ '+fx(totBr,2));
      setText('t-el-cons', fx(cons,3)); setText('t-el-avgk', fx(avgK,3)); setText('t-el-total', '€ '+fx(totBr,2)); setText('t-el-avgp','€ '+fx(avgP,6));
    };
    const recalcGas = ()=>{
      const s=+(document.getElementById('gas-start')?.value||0);
      const e=+(document.getElementById('gas-end')?.value||0);
      const c=+(document.getElementById('gas-coeff')?.value||0);
      const net=+(document.getElementById('gas-price-net')?.value||0);
      const vat=+(document.getElementById('gas-vat')?.value||0);
      const m3 = Math.max(0, e-s), kwh = m3*c, unitBr = net*(1+vat/100), totBr = kwh*unitBr;
      setText('gas-m3', fx(m3,3)); setText('gas-kwh', fx(kwh,3)); setText('gas-total-br','€ '+fx(totBr,2));
      setText('t-gas-m3', fx(m3,3)); setText('t-gas-kwh', fx(kwh,3)); setText('t-gas-total', '€ '+fx(totBr,2));
    };
    const recalcWater = ()=>{
      const p=+(document.getElementById('w-prev')?.value||0);
      const c=+(document.getElementById('w-curr')?.value||0);
      const net=+(document.getElementById('w-price-net')?.value||0);
      const vat=+(document.getElementById('w-vat')?.value||0);
      const m3 = Math.max(0, c-p), unitBr = net*(1+vat/100), totBr = m3*unitBr;
      setText('w-m3', fx(m3,3)); setText('w-total-br','€ '+fx(totBr,2));
      setText('t-w-m3', fx(m3,3)); setText('t-w-total', '€ '+fx(totBr,2));
    };

    // live prepočty a SAVE pre aktívnu pod-kartu
    if (costsState.activeEnergyTab==='electricity'){
      ['el-start','el-end','el-price-net','el-vat'].forEach(id=>{
        const el = document.getElementById(id); if (el) el.oninput = recalcElectricity;
      });
      recalcElectricity();
      const save = document.getElementById('el-save');
      if (save) save.onclick = async ()=>{
        status('Ukladám elektrinu…', true);
        const payload = {
          year: costsState.year, month: costsState.month,
          electricity: {
            meter_start_kwh:+(document.getElementById('el-start')?.value||0),
            meter_end_kwh:  +(document.getElementById('el-end')?.value||0),
            unit_price_kwh_net:+(document.getElementById('el-price-net')?.value||0),
            vat_rate:+(document.getElementById('el-vat')?.value||0),
          }
        };
        const r = await apiPost('/api/kancelaria/costs/saveEnergy', payload);
        if (r?.error){ status(r.error, false); return; }
        status('Elektrina uložená.', true);
        await loadAll();
      };
    } else if (costsState.activeEnergyTab==='gas'){
      ['gas-start','gas-end','gas-coeff','gas-price-net','gas-vat'].forEach(id=>{
        const el = document.getElementById(id); if (el) el.oninput = recalcGas;
      });
      recalcGas();
      const save = document.getElementById('gas-save');
      if (save) save.onclick = async ()=>{
        status('Ukladám plyn…', true);
        const payload = {
          year: costsState.year, month: costsState.month,
          gas: {
            meter_start_m3:+(document.getElementById('gas-start')?.value||0),
            meter_end_m3:  +(document.getElementById('gas-end')?.value||0),
            coeff_kwh_per_m3:+(document.getElementById('gas-coeff')?.value||0),
            unit_price_kwh_net:+(document.getElementById('gas-price-net')?.value||0),
            vat_rate:+(document.getElementById('gas-vat')?.value||0),
          }
        };
        const r = await apiPost('/api/kancelaria/costs/saveEnergy', payload);
        if (r?.error){ status(r.error, false); return; }
        status('Plyn uložený.', true);
        await loadAll();
      };
    } else {
      ['w-prev','w-curr','w-price-net','w-vat'].forEach(id=>{
        const el = document.getElementById(id); if (el) el.oninput = recalcWater;
      });
      recalcWater();
      const save = document.getElementById('w-save');
      if (save) save.onclick = async ()=>{
        status('Ukladám vodu…', true);
        const payload = {
          year: costsState.year, month: costsState.month,
          water: {
            meter_prev:+(document.getElementById('w-prev')?.value||0),
            meter_curr:+(document.getElementById('w-curr')?.value||0),
            unit_price_net:+(document.getElementById('w-price-net')?.value||0),
            vat_rate:+(document.getElementById('w-vat')?.value||0),
            total_bez_dph:0, dph:0, total_s_dph:0
          }
        };
        const r = await apiPost('/api/kancelaria/costs/saveEnergy', payload);
        if (r?.error){ status(r.error, false); return; }
        status('Voda uložená.', true);
        await loadAll();
      };
    }

    // ===== Ročný prehľad =====
    (function wireAnnual(){
      const ySel = document.getElementById('annual-year');
      const tSel = document.getElementById('annual-type');
      const loadBtn = document.getElementById('annual-load');
      const printBtn= document.getElementById('annual-print');
      const yNow = new Date().getFullYear();

      if (ySel && !ySel.options.length){
        for (let y=yNow; y>=yNow-5; y--) ySel.add(new Option(y, y));
        ySel.value = String(costsState.year);
      }
      if (tSel && !tSel.value) tSel.value = 'electricity';

      async function loadAnnual(){
        const y   = Number(ySel?.value || costsState.year);
        const typ = (tSel?.value || 'electricity');
        status('Načítavam ročný prehľad…', true);
        try{
          const data = await apiPost('/api/kancelaria/costs/getAnnual', { year: y, types: typ });
          if (data?.error){ status(data.error, false); return; }
          renderAnnualTable(data);
          status('');
        }catch(e){ status(String(e.message||e), false); }
      }

      function renderAnnualTable(data){
        const box = document.getElementById('annual-table'); if (!box) return;
        const t = (data.types||'electricity');
        const s = data.series||[];
        const sum = data.summary||{};

        const tableElectricity = ()=>{
          const rows = s.map(r=>{
            const e = r.electricity||{};
            return `<tr>
              <td>${String(r.month).padStart(2,'0')}</td>
              <td class="num">${fx(e.cons_kwh,3)}</td>
              <td class="num">${fx(e.unit_avg_gross,6)}</td>
              <td class="num">€ ${fx(e.total_br,2)}</td>
            </tr>`;
          }).join('');
          const ss = sum.electricity||{};
          return `<h4>Elektrina ${data.year}</h4>
            <table class="table">
              <thead><tr><th>Mesiac</th><th class="num">kWh</th><th class="num">€/kWh</th><th class="num">€ spolu</th></tr></thead>
              <tbody>${rows}</tbody>
              <tfoot>
                <tr><td><strong>Súčet</strong></td><td class="num"><strong>${fx(ss.cons_kwh_sum,3)}</strong></td>
                    <td class="num"><strong>${fx(ss.unit_avg_weighted,6)}</strong></td>
                    <td class="num"><strong>€ ${fx(ss.total_br_sum,2)}</strong></td></tr>
              </tfoot>
            </table>`;
        };

        const tableGas = ()=>{
          const rows = s.map(r=>{
            const g = r.gas||{};
            return `<tr>
              <td>${String(r.month).padStart(2,'0')}</td>
              <td class="num">${fx(g.cons_m3,3)}</td>
              <td class="num">${fx(g.cons_kwh,3)}</td>
              <td class="num">${fx(g.unit_avg_gross,6)}</td>
              <td class="num">€ ${fx(g.total_br,2)}</td>
            </tr>`;
          }).join('');
          const ss = sum.gas||{};
          return `<h4>Plyn ${data.year}</h4>
            <table class="table">
              <thead><tr><th>Mesiac</th><th class="num">m³</th><th class="num">kWh</th><th class="num">€/kWh</th><th class="num">€ spolu</th></tr></thead>
              <tbody>${rows}</tbody>
              <tfoot>
                <tr><td><strong>Súčet</strong></td>
                    <td class="num"><strong>${fx(ss.cons_m3_sum,3)}</strong></td>
                    <td class="num"><strong>${fx(ss.cons_kwh_sum,3)}</strong></td>
                    <td class="num"><strong>${fx(ss.unit_avg_weighted,6)}</strong></td>
                    <td class="num"><strong>€ ${fx(ss.total_br_sum,2)}</strong></td></tr>
              </tfoot>
            </table>`;
        };

        const tableWater = ()=>{
          const rows = s.map(r=>{
            const w = r.water||{};
            return `<tr>
              <td>${String(r.month).padStart(2,'0')}</td>
              <td class="num">${fx(w.cons_m3,3)}</td>
              <td class="num">${fx(w.unit_avg_gross,6)}</td>
              <td class="num">€ ${fx(w.total_br,2)}</td>
            </tr>`;
          }).join('');
          const ss = sum.water||{};
          return `<h4>Voda ${data.year}</h4>
            <table class="table">
              <thead><tr><th>Mesiac</th><th class="num">m³</th><th class="num">€/m³</th><th class="num">€ spolu</th></tr></thead>
              <tbody>${rows}</tbody>
              <tfoot>
                <tr><td><strong>Súčet</strong></td>
                    <td class="num"><strong>${fx(ss.cons_m3_sum,3)}</strong></td>
                    <td class="num"><strong>${fx(ss.unit_avg_weighted,6)}</strong></td>
                    <td class="num"><strong>€ ${fx(ss.total_br_sum,2)}</strong></td></tr>
              </tfoot>
            </table>`;
        };

        let html = '';
        if (t==='all') html = tableElectricity()+tableGas()+tableWater();
        else if (t==='electricity') html = tableElectricity();
        else if (t==='gas') html = tableGas();
        else html = tableWater();

        box.innerHTML = html;
      }

      if (loadBtn) loadBtn.onclick = loadAnnual;
      if (printBtn) printBtn.onclick = ()=>{
        const y   = Number(ySel?.value || costsState.year);
        const typ = tSel?.value || 'electricity';
        window.open(`/report/costs/energyAnnual?year=${y}&types=${encodeURIComponent(typ)}`, '_blank');
      };

      // predvyplň a načítaj
      if (ySel && !ySel.value) ySel.value = String(costsState.year);
      if (tSel && !tSel.value) tSel.value = 'electricity';
      loadAnnual();
    })();
  }

  // ====== HR ======
  function renderHR(){
    const hr = costsState.data?.hr || {};
    return `
      <div class="card">
        <div class="grid-3">
          <label>Mzdy spolu (€) <input id="hr-salaries" type="number" step="0.01" value="${hr.total_salaries||''}"></label>
          <label>Odvody spolu (€) <input id="hr-levies" type="number" step="0.01" value="${hr.total_levies||''}"></label>
        </div>
        <div class="row right mt"><button id="hr-save" class="btn btn-primary">Uložiť HR</button></div>
      </div>
    `;
  }
  function wireHR(){
    const btn = $('hr-save');
    if (!btn) return;
    btn.onclick = async ()=>{
      btn.disabled = true; status('Ukladám HR…', true);
      const payload = {
        year: costsState.year, month: costsState.month,
        total_salaries: +($('hr-salaries')?.value||0),
        total_levies: +($('hr-levies')?.value||0)
      };
      const r = await apiPost('/api/kancelaria/costs/saveHR', payload);
      btn.disabled = false;
      if (r?.error){ status(r.error, false); return; }
      status('HR uložené.', true);
      await loadAll();
    };
  }

  // ====== PREVÁDZKA ======
  function renderOP(){
    const cats = (costsState.data?.operational?.categories)||[];
    const items = (costsState.data?.operational?.items)||[];
    const options = cats.map(c=>`<option value="${c.id}">${c.name}</option>`).join('');
    const rows = items.map(it=>`
      <tr>
        <td>${it.entry_date}</td>
        <td>${it.category_name}</td>
        <td>${it.name}</td>
        <td class="num">€ ${fx(it.amount_net,2)}</td>
        <td>${it.vendor_name||''}</td>
        <td>${it.invoice_no||''}</td>
        <td><button class="btn btn-danger btn-sm" data-del="${it.id}">X</button></td>
      </tr>
    `).join('');
    return `
      <div class="card">
        <div class="grid-3">
          <label>Dátum <input id="op-date" type="date"></label>
          <label>Kategória <select id="op-cat">${options}</select></label>
          <label>Názov položky <input id="op-name" placeholder="napr. servis stroja"></label>
          <label>Popis <input id="op-desc"></label>
          <label>Suma bez DPH (€) <input id="op-amount" type="number" step="0.01"></label>
          <label>DPH % <input id="op-vat" type="number" step="0.01" placeholder="20"></label>
          <label>Dodávateľ <input id="op-vendor"></label>
          <label>Faktúra č. <input id="op-inv"></label>
          <label>Stredisko <input id="op-cc" placeholder="company/expedition/butchering/..."></label>
          <label class="row" style="align-items:center; gap:8px"><input id="op-rec" type="checkbox"> Pravidelné</label>
        </div>
        <div class="row right mt"><button id="op-add" class="btn btn-primary">Pridať náklad</button></div>
      </div>

      <div class="card mt">
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th>Dátum</th><th>Kategória</th><th>Názov</th><th class="num">Suma bez DPH</th><th>Dodávateľ</th><th>Faktúra</th><th></th></tr></thead>
            <tbody id="op-tbody">${rows || '<tr><td colspan="7">Žiadne položky</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    `;
  }
  function wireOP(){
    const mm = String(costsState.month).padStart(2,'0');
    const today = `${costsState.year}-${mm}-28`;
    const dateEl = $('op-date'); if (dateEl) dateEl.value = today;

    const add = $('op-add');
    if (add){
      add.onclick = async ()=>{
        add.disabled = true; status('Ukladám náklad…', true);
        const payload = {
          entry_date: $('op-date')?.value,
          category_id: +($('op-cat')?.value||0),
          name: $('op-name')?.value,
          description: $('op-desc')?.value,
          amount_net: +($('op-amount')?.value || 0),
          vat_rate: +($('op-vat')?.value || 0),
          vendor_name: $('op-vendor')?.value,
          invoice_no: $('op-inv')?.value,
          cost_center: $('op-cc')?.value || 'company',
          is_recurring: $('op-rec')?.checked
        };
        if (!payload.entry_date || !payload.category_id || !payload.name){
          status('Vyplň dátum, kategóriu a názov.', false); add.disabled=false; return;
        }
        const r = await apiPost('/api/kancelaria/costs/saveOperational', payload);
        add.disabled = false;
        if (r?.error){ status(r.error, false); return; }
        status('Náklad pridaný.', true);
        await loadAll();
      };
    }

    const tbody = $('op-tbody');
    if (tbody){
      tbody.onclick = async (e)=>{
        const btn = e.target.closest('button[data-del]'); if (!btn) return;
        const id = +btn.dataset.del;
        if (!confirm('Vymazať náklad?')) return;
        status('Mažem náklad…', true);
        const r = await apiPost('/api/kancelaria/costs/deleteOperational', { id });
        if (r?.error){ status(r.error, false); return; }
        await loadAll();
        status('Náklad vymazaný.', true);
      };
    }
  }

  // ====== KATEGÓRIE ======
  function renderCats(){
    const cats = (costsState.data?.operational?.categories)||[];
    const rows = cats.map(c=>`<tr><td>${c.id}</td><td>${c.name}</td></tr>`).join('');
    return `
      <div class="card">
        <div class="row wrap" style="gap:10px; align-items:flex-end">
          <label>Nová kategória <input id="cat-name" placeholder="napr. Telekom – mobil"></label>
          <button id="cat-add" class="btn btn-primary">Pridať</button>
        </div>
      </div>
      <div class="card mt">
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th>ID</th><th>Názov</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="2">Žiadne kategórie</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    `;
  }
  function wireCats(){
    const add = $('cat-add');
    if (!add) return;
    add.onclick = async ()=>{
      add.disabled = true; status('Pridávam kategóriu…', true);
      const name = ($('cat-name')?.value||'').trim();
      if (!name){ status('Zadaj názov kategórie.', false); add.disabled=false; return; }
      const r = await apiPost('/api/kancelaria/costs/saveCategory', { name });
      add.disabled = false;
      if (r?.error){ status(r.error, false); return; }
      status('Kategória pridaná.', true);
      await loadAll();
    };
  }

  // initial
  loadAll();
}

// export init
window.initializeCostsModule = initializeCostsModule;
