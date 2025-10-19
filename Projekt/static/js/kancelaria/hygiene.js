// static/js/kancelaria/hygiene.js
// HYGIENA/HACCP – plán + štart/ukončenie + dokončenie + admin (úlohy/prostriedky)

/* -------------------- Mini modal (bez závislosti) -------------------- */
let __escHandler = null;
function showModal(title, builder){
  const wrap = document.createElement('div');
  wrap.id = 'modal-container';
  wrap.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:99999';

  const card = document.createElement('div');
  card.className = 'modal-card';
  card.style.cssText = 'background:#fff;min-width:360px;max-width:960px;width:92vw;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.2);';
  card.innerHTML = `
    <div class="modal-header" style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px 16px;border-bottom:1px solid #e5e7eb">
      <h3 class="modal-title" style="margin:0;font-size:18px;font-weight:700">${title}</h3>
      <button id="modal-close" class="btn" type="button" style="border:1px solid #e5e7eb;background:#fff;border-radius:8px;padding:6px 10px;cursor:pointer">✕</button>
    </div>
    <div id="modal-body" class="modal-body" style="padding:16px;max-height:70vh;overflow:auto"></div>
    <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;padding:12px 16px;border-top:1px solid #e5e7eb"></div>`;
  wrap.appendChild(card);
  document.body.appendChild(wrap);

  // close handlers
  wrap.addEventListener('click', e => { if (e.target === wrap) closeModal(); });
  __escHandler = e => { if (e.key === 'Escape') closeModal(); };
  document.addEventListener('keydown', __escHandler);
  card.querySelector('#modal-close').onclick = closeModal;

  // render content (footer pred onReady → prvky už existujú)
  Promise.resolve(typeof builder === 'function' ? builder() : builder).then(cfg => {
    const bodyEl   = card.querySelector('#modal-body');
    const footerEl = card.querySelector('.modal-footer');
    bodyEl.innerHTML = cfg.html || '';
    if (cfg.footerHtml) footerEl.innerHTML = cfg.footerHtml;
    cfg.onReady && cfg.onReady({ root: card, body: bodyEl, footer: footerEl });
    const first = bodyEl.querySelector('input, textarea, select, button');
    first && first.focus();
  });
}
function closeModal(){
  const wrap = document.getElementById('modal-container');
  if (wrap) wrap.remove();
  if (__escHandler){ document.removeEventListener('keydown', __escHandler); __escHandler = null; }
}

/* -------------------- Helpers -------------------- */
const esc = s => (s==null?'':String(s)).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const tHHMM = dt => new Date(dt).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
function toast(msg, err=false){ try{ window.showStatus?.(msg, !!err); }catch{ err?alert(msg):console.log(msg);} }

/* -------------------- INIT UI -------------------- */
export function initializeHygieneModule(){
  const root = document.getElementById('section-hygiene');
  if (!root) return;

  root.innerHTML = `
  <div class="card">
    <div class="row wrap" style="gap:12px; align-items:flex-end;">
      <label style="display:flex;flex-direction:column;gap:6px">
        <span>Dátum</span>
        <input type="date" id="hyg-date">
      </label>
      <label style="display:flex;flex-direction:column;gap:6px">
        <span>Report</span>
        <select id="hyg-period">
          <option value="denne">Denný</option>
          <option value="tyzdenne">Týždenný</option>
          <option value="mesacne">Mesačný</option>
        </select>
      </label>
      <label style="display:flex;flex-direction:column;gap:6px">
        <span>Filter úloha</span>
        <input type="text" id="hyg-filter-task" placeholder="napr. linka, stôl…">
      </label>
      <label style="display:flex;flex-direction:column;gap:6px">
        <span>Filter prípravok</span>
        <select id="hyg-filter-agent"><option value="">Všetky</option></select>
      </label>
      <div style="flex:1"></div>
      <button id="hyg-print"  class="btn">Tlačiť report</button>
      <button id="hyg-agents" class="btn">Prostriedky</button>
      <button id="hyg-tasks"  class="btn btn-primary">Úlohy</button>
    </div>
  </div>

  <div id="hyg-plan" class="card mt">
    <p>Načítavam plán…</p>
  </div>
`;

  const d = document.getElementById('hyg-date');
  d.valueAsDate = new Date();
  d.onchange = () => loadPlan(d.value);

  // naplň výber prípravkov pre filter reportu
  (async ()=>{
    try{
      const agents = await apiRequest('/api/kancelaria/hygiene/getAgents');
      const sel = document.getElementById('hyg-filter-agent');
      (agents||[]).forEach(a => sel.add(new Option(a.agent_name, a.id)));
    }catch{}
  })();

  // tlač reportu (s filtrami)
  document.getElementById('hyg-print').onclick  = () => {
    const p = document.getElementById('hyg-period').value;
    const task  = encodeURIComponent(document.getElementById('hyg-filter-task').value || '');
    const agent = document.getElementById('hyg-filter-agent').value || '';
    let url = `/report/hygiene?date=${d.value}&period=${p}`;
    if (task)  url += `&task=${task}`;
    if (agent) url += `&agent_id=${agent}`;
    window.open(url, '_blank');
  };

  // admin
  document.getElementById('hyg-agents').onclick = openAgentsList;
  document.getElementById('hyg-tasks').onclick  = openTasksList;

  // načítaj plán
  loadPlan(d.value);
}
window.initializeHygieneModule = initializeHygieneModule; // pre initOnce

/* -------------------- LOAD/RENDER PLAN -------------------- */
async function loadPlan(dateStr){
  const box = document.getElementById('hyg-plan');
  box.innerHTML = '<p>Načítavam plán…</p>';
  try{
    const data = await apiRequest(`/api/kancelaria/hygiene/getPlan?date=${dateStr}`);
    renderPlan(box, data.tasks||[], data.planDate||dateStr);
  }catch(e){
    box.innerHTML = `<p class="error">Chyba: ${esc(e.message||'Neznáma chyba')}</p>`;
  }
}

function renderPlan(container, tasks, planDate){
  const head = `<div class="section-header"><h2>Hygiena – ${planDate}</h2></div>`;
  if (!tasks.length){ container.innerHTML = `${head}<p>Žiadne úlohy pre zvolený dátum.</p>`; return; }

  let html = `${head}
  <div class="table-wrap"><table class="table">
    <thead><tr>
      <th>Úloha</th><th>Miesto</th>
      <th>Začiatok</th><th>Koniec pôsobenia</th><th>Koniec oplachu</th>
      <th>Ukončené</th><th>Pracovník</th><th>Akcia</th>
    </tr></thead><tbody>`;

  for (const t of tasks){
    html += `<tr>
      <td>${esc(t.task_name||'')}</td>
      <td>${esc(t.location||'')}</td>
      <td>${t.start_time   ? tHHMM(t.start_time)   : '–'}</td>
      <td>${t.exposure_end ? tHHMM(t.exposure_end) : '–'}</td>
      <td>${t.rinse_end    ? tHHMM(t.rinse_end)    : '–'}</td>
      <td>${t.end_time     ? tHHMM(t.end_time)     : '–'}</td>
      <td>${t.performed_by ? esc(t.performed_by)   : '–'}</td>
      <td class="num">
        <div class="row" style="gap:6px;justify-content:flex-end">
          <button class="btn"             data-act="start"     data-id="${t.task_id}" data-name="${esc(t.task_name||'')}" title="Zadať začiatok">Začať</button>
          <button class="btn btn-primary" data-act="finish"    data-id="${t.task_id}" data-name="${esc(t.task_name||'')}" title="Uložiť ukončenie">Ukončiť</button>
          <button class="btn"             data-act="complete"  data-id="${t.task_id}" data-log="${t.log_id||''}" data-name="${esc(t.task_name||'')}">Dokončenie</button>
        </div>
      </td>
    </tr>`;
  }
  html += `</tbody></table></div>`;
  container.innerHTML = html;

  if (!container.__wired){
    container.addEventListener('click', (e)=>{
      const btn = e.target.closest('button[data-act]'); if(!btn) return;
      const id  = btn.dataset.id; const name = btn.dataset.name; const logId = btn.dataset.log||null;
      if (btn.dataset.act==='start')    openStartModal(id, name);
      else if (btn.dataset.act==='finish')  openFinishModal(id, name);
      else if (btn.dataset.act==='complete')openCompletionModal(id, name, logId);
    });
    container.__wired = true;
  }
}

/* -------------------- START / FINISH / COMPLETE -------------------- */
function openStartModal(taskId, taskName){
  showModal(`Začať úlohu – ${esc(taskName)}`, {
    html: `
      <form id="hyg-start-form" class="form">
        <label>Začiatok (HH:MM)
          <input type="time" name="start" value="08:00" required>
        </label>
      </form>`,
    footerHtml: `<button class="btn" id="hyg-start-cancel">Zavrieť</button>
                 <button class="btn btn-primary" id="hyg-start-save">Uložiť</button>`,
    onReady: ()=>{
      document.getElementById('hyg-start-cancel').onclick = closeModal;
      document.getElementById('hyg-start-save').onclick = async ()=>{
        const hhmm = (document.querySelector('#hyg-start-form [name="start"]').value||'').trim();
        if (!hhmm) return;
        try{
          await apiRequest('/api/kancelaria/hygiene/logStart',{ method:'POST', body:{ task_id: taskId, start_time_str: hhmm }});
          closeModal(); toast('Začiatok uložený.');
          const d = document.getElementById('hyg-date').value; d && loadPlan(d);
        }catch(e){ toast('Chyba: '+e.message, true); }
      };
    }
  });
}

function openFinishModal(taskId, taskName){
  showModal(`Ukončiť úlohu – ${esc(taskName)}`, {
    html: `
      <form id="hyg-finish-form" class="form">
        <label>Vykonal
          <input type="text" name="who" placeholder="Meno pracovníka" required>
        </label>
      </form>`,
    footerHtml: `<button class="btn" id="hyg-finish-cancel">Zavrieť</button>
                 <button class="btn btn-primary" id="hyg-finish-save">Uložiť</button>`,
    onReady: ()=>{
      document.getElementById('hyg-finish-cancel').onclick = closeModal;
      document.getElementById('hyg-finish-save').onclick = async ()=>{
        const who = (document.querySelector('#hyg-finish-form [name="who"]').value||'').trim();
        if (!who) return;
        try{
          await apiRequest('/api/kancelaria/hygiene/logFinish',{ method:'POST', body:{ task_id: taskId, performed_by: who }});
          closeModal(); toast('Ukončenie uložené.');
          const d = document.getElementById('hyg-date').value; d && loadPlan(d);
        }catch(e){ toast('Chyba: '+e.message, true); }
      };
    }
  });
}

function openCompletionModal(taskId, taskName, logId){
  // načítaj dostupných agentov do selectu
  const loadAgents = async ()=>{ try{ return await apiRequest('/api/kancelaria/hygiene/getAgents'); }catch{ return []; } };
  showModal(`Dokončenie – ${esc(taskName)}`, {
    html: `
      <form id="hyg-complete-form" class="form grid-2">
        <input type="hidden" name="task_id" value="${taskId}">
        <label>Prípravok
          <select name="agent_id" id="hyg-comp-agent"><option value="">-- Vybrať --</option></select>
        </label>
        <label>Koncentrácia
          <input type="text" name="concentration" placeholder="napr. 2% alebo 20 ml/l">
        </label>
        <label>Čas pôsobenia
          <input type="text" name="exposure_time" placeholder="napr. 10 min">
        </label>
        <label>Vykonal
          <input type="text" name="performer_name" placeholder="Meno pracovníka" required>
        </label>
        <label class="col-span-2">Poznámka
          <textarea name="notes" rows="2" placeholder="Poznámka (voliteľné)"></textarea>
        </label>
      </form>`,
    footerHtml: `<button class="btn" id="hyg-comp-cancel">Zavrieť</button>
                 <button class="btn btn-primary" id="hyg-comp-save">Uložiť</button>`,
    onReady: async ()=>{
      document.getElementById('hyg-comp-cancel').onclick = closeModal;

      // predvyplň dátum dokončenia = aktuálny z filtra
      const completion_date = document.getElementById('hyg-date')?.value || new Date().toISOString().slice(0,10);

      // naplň prípravky
      const agents = await loadAgents();
      const sel = document.getElementById('hyg-comp-agent');
      (agents||[]).forEach(a => sel.add(new Option(a.agent_name, a.id)));

      document.getElementById('hyg-comp-save').onclick = async ()=>{
        const f = document.getElementById('hyg-complete-form');
        const payload = Object.fromEntries(new FormData(f).entries());
        payload.completion_date = completion_date;
        try{
          const r = await apiRequest('/api/kancelaria/hygiene/logCompletion',{ method:'POST', body: payload });
          if (r?.error) return toast(r.error, true);
          closeModal(); toast('Dokončenie uložené.');
          completion_date && loadPlan(completion_date);
        }catch(e){ toast('Chyba: '+e.message, true); }
      };
    }
  });
}

/* -------------------- AGENTS (ADMIN) -------------------- */
async function openAgentsList(){
  const agents = await apiRequest('/api/kancelaria/hygiene/getAgents');
  const html = `
    <div class="table-wrap"><table class="table">
      <thead><tr><th>Názov prípravku</th><th></th></tr></thead>
      <tbody>
        ${(agents||[]).map(a=>`
          <tr>
            <td>${esc(a.agent_name)}</td>
            <td class="num"><button class="btn" data-act="edit" data-id="${a.id}" data-name="${esc(a.agent_name)}">Upraviť</button></td>
          </tr>
        `).join('')}
      </tbody>
    </table></div>
    <div class="row right mt"><button class="btn btn-primary" id="hyg-agent-new">+ Nový prípravok</button></div>`;
  showModal('Prípravky', {
    html,
    onReady: ()=>{
      document.getElementById('hyg-agent-new').onclick = () => openAgentForm();
      document.getElementById('modal-body').addEventListener('click', e=>{
        const b = e.target.closest('button[data-act="edit"]'); if(!b) return;
        openAgentForm({ id:b.dataset.id, agent_name:b.dataset.name });
      });
    }
  });
}
function openAgentForm(agent=null){
  showModal(agent?'Upraviť prípravok':'Nový prípravok', {
    html: `
      <form id="hyg-agent-form" class="form">
        <input type="hidden" name="id" value="${agent?.id||''}">
        <label>Názov
          <input type="text" name="agent_name" value="${esc(agent?.agent_name||'')}" required>
        </label>
      </form>`,
    footerHtml: `<button class="btn" id="hyg-agent-cancel">Zavrieť</button>
                 <button class="btn btn-primary" id="hyg-agent-save">Uložiť</button>`,
    onReady: ()=>{
      document.getElementById('hyg-agent-cancel').onclick = closeModal;
      document.getElementById('hyg-agent-save').onclick = async ()=>{
        const f = document.getElementById('hyg-agent-form');
        const data = Object.fromEntries(new FormData(f).entries());
        try{
          const r = await apiRequest('/api/kancelaria/hygiene/saveAgent',{ method:'POST', body:data });
        if (r?.error) return toast(r.error, true);
          closeModal(); openAgentsList(); toast('Uložené.');
        }catch(e){ toast('Chyba: '+e.message, true); }
      };
    }
  });
}

/* -------------------- TASKS (ADMIN) -------------------- */
async function openTasksList(){
  const tasks = await apiRequest('/api/kancelaria/hygiene/getTasks');
  const html = `
    <div class="table-wrap"><table class="table">
      <thead><tr>
        <th>Názov</th><th>Umiestnenie</th><th>Frekvencia</th><th>Stav</th><th></th>
      </tr></thead>
      <tbody>
        ${(tasks||[]).map(t=>`
          <tr>
            <td>${esc(t.task_name||'')}</td>
            <td>${esc(t.location||'')}</td>
            <td>${esc(t.frequency||'')}</td>
            <td>${t.is_active ? 'Aktívna':'Neaktívna'}</td>
            <td class="num"><button class="btn" data-act="edit" data-payload='${JSON.stringify(t).replace(/"/g,"&quot;")}'>Upraviť</button></td>
          </tr>
        `).join('')}
      </tbody>
    </table></div>
    <div class="row right mt"><button class="btn btn-primary" id="hyg-task-new">+ Nová úloha</button></div>`;
  showModal('Úlohy', {
    html,
    onReady: ()=>{
      document.getElementById('hyg-task-new').onclick = () => openTaskForm();
      document.getElementById('modal-body').addEventListener('click', e=>{
        const b = e.target.closest('button[data-act="edit"]'); if(!b) return;
        try { openTaskForm(JSON.parse(b.dataset.payload)); } catch {}
      });
    }
  });
}
async function openTaskForm(task=null){
  // Prípravky do selectu (nepovinné)
  const agents = await apiRequest('/api/kancelaria/hygiene/getAgents').catch(()=>[]);
  const agentOptions = (agents||[]).map(a =>
    `<option value="${a.id}" ${task?.default_agent_id==a.id?'selected':''}>${esc(a.agent_name)}</option>`
  ).join('');
  showModal(task?'Upraviť úlohu':'Nová úloha', {
    html: `
      <form id="hyg-task-form" class="form grid-2">
        <input type="hidden" name="id" value="${task?.id||''}">
        <label>Názov úlohy <input type="text" name="task_name" value="${esc(task?.task_name||'')}" required></label>
        <label>Umiestnenie  <input type="text" name="location"   value="${esc(task?.location||'')}" required></label>
        <label>Frekvencia
          <select name="frequency" required>
            ${['denne','tyzdenne','mesacne','stvrtronne','rocne'].map(f=>`<option value="${f}" ${task?.frequency===f?'selected':''}>${f}</option>`).join('')}
          </select>
        </label>
        <label>Predvolený prípravok
          <select name="default_agent_id"><option value="">-- Žiadny --</option>${agentOptions}</select>
        </label>
        <label>Predvolená koncentrácia <input type="text" name="default_concentration" value="${esc(task?.default_concentration||'')}"></label>
        <label>Predvolený čas pôsobenia <input type="text" name="default_exposure_time" value="${esc(task?.default_exposure_time||'')}"></label>
        <label class="col-span-2">Popis <textarea name="description" rows="2">${esc(task?.description||'')}</textarea></label>
        <label class="col-span-2" style="display:flex;align-items:center;gap:8px">
          <input type="checkbox" name="is_active" ${task ? (task.is_active ? 'checked':'') : 'checked'} style="width:auto"> Úloha je aktívna
        </label>
      </form>`,
    footerHtml: `<button class="btn" id="hyg-task-cancel">Zavrieť</button>
                 <button class="btn btn-primary" id="hyg-task-save">Uložiť</button>`,
    onReady: ()=>{
      document.getElementById('hyg-task-cancel').onclick = closeModal;
      document.getElementById('hyg-task-save').onclick = async ()=>{
        const f = document.getElementById('hyg-task-form');
        const data = Object.fromEntries(new FormData(f).entries());
        data.is_active = !!f.elements.is_active.checked;
        try{
          const r = await apiRequest('/api/kancelaria/hygiene/saveTask',{ method:'POST', body:data });
          if (r?.error) return toast(r.error, true);
          closeModal(); openTasksList(); toast('Uložené.');
        }catch(e){ toast('Chyba: '+e.message, true); }
      };
    }
  });
}
