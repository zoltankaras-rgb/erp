// /static/js/kancelaria/ai.js — jednoduchý chat UI nad AI handlerom
(function(){
  const esc = s => (s==null ? '' : String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m])));

  function readCsrf(){
    const m = document.querySelector('meta[name="csrf-token"]');
    if (m && m.content) return m.content;
    const c = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return c ? decodeURIComponent(c[1]) : '';
  }

  async function postJSON(url, body){
    const token = readCsrf();
    const r = await fetch(url, {
      method:'POST',
      credentials:'same-origin',
      headers:{ 'Content-Type':'application/json', 'Accept':'application/json', 'X-CSRF-Token': token },
      body: JSON.stringify({ ...(body||{}), csrf_token: token })
    });
    const t = await r.text(); try { return JSON.parse(t);} catch { throw new Error(t); }
  }

  function addMsg(who, html){
    const box = document.getElementById('ai-messages');
    const div = document.createElement('div');
    div.className = 'msg ' + (who==='me'?'me':'bot');
    div.innerHTML = html;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function renderTable(table){
    if (!table || !Array.isArray(table.columns) || !Array.isArray(table.rows)) return '';
    const thead = `<tr>${table.columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr>`;
    const rows = table.rows.map(r => {
      if (Array.isArray(r)) return `<tr>${r.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`;
      // object map
      return `<tr>${table.columns.map(c=>`<td>${esc(r[c] ?? r[c.toLowerCase()] ?? '')}</td>`).join('')}</tr>`;
    }).join('');
    return `<div class="table-wrap"><table class="table"><thead>${thead}</thead><tbody>${rows}</tbody></table></div>`;
  }

  async function send(){
    const inp = document.getElementById('ai-input');
    const msg = inp.value.trim();
    if (!msg) return;
    addMsg('me', `<div class="bubble">${esc(msg)}</div>`);
    inp.value = '';
    try{
      const year = Number(document.getElementById('dash-year')?.value) || undefined;
      const month= Number(document.getElementById('dash-month')?.value) || undefined;
      const res = await postJSON('/api/kancelaria/ai/chat', {message: msg, year, month});
      let html = `<div class="bubble">${esc(res.reply || '')}</div>`;
      if (res.table) html += renderTable(res.table);
      addMsg('bot', html);
    }catch(e){
      addMsg('bot', `<div class="bubble error">Chyba: ${esc(e.message||String(e))}</div>`);
    }
  }

  function buildShell(){
    const sec = document.getElementById('section-ai');
    if (!sec) return;
    sec.innerHTML = `
      <div class="card">
        <h3 class="card-title">AI Asistent (beta)</h3>
        <div id="ai-messages" class="ai-messages"></div>
        <div class="ai-input">
          <input id="ai-input" type="text" placeholder="Napíš otázku... (B2B/B2C objednávky, nízke zásoby, TOP produkty)">
          <button id="ai-send" class="btn">Odoslať</button>
        </div>
      </div>
    `;
    document.getElementById('ai-send').onclick = send;
    document.getElementById('ai-input').addEventListener('keydown', (e)=>{ if(e.key==='Enter') send(); });
    // pozdrav
    addMsg('bot', `<div class="bubble">Ahoj! Spýtaj sa na B2B/B2C objednávky, nízke zásoby alebo TOP výrobky.</div>`);
  }

  document.addEventListener('DOMContentLoaded', buildShell);
  window.initializeAIModule = buildShell; // kompatibilný export
})();