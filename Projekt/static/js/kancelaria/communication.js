// /static/js/kancelaria/communication.js — PRO webmail + rich compose
(function(){
  const $ = sel => document.querySelector(sel);
  const esc = s => (s==null ? '' : String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m])));
  const fxDate = v => { if(!v) return ''; const d=new Date(v); return isNaN(d)? String(v) : d.toLocaleString('sk-SK'); };

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
    const t = await r.text(); try { return JSON.parse(t);} catch { throw new Error(t);}
  }
  let ALL_ITEMS=[]; let CURRENT_FILTER='ALL'; let EDITOR_CFG=null;

  // --------- list / sync ---------
  async function syncInbox(){ const b=$('#btn-sync'); if(b) b.disabled=true; try{ const res=await postJSON('/api/kancelaria/comm/sync', {}); if(res.error) alert('Sync: '+res.error); await loadList(CURRENT_FILTER);}catch(e){ alert('Sync: '+(e.message||e)); } if(b) b.disabled=false; }
  async function loadList(type='ALL'){ CURRENT_FILTER=type; const data=await postJSON('/api/kancelaria/comm/list',{type}); ALL_ITEMS=data.items||[]; renderCounts(); renderList(); }
  function selectedIds(){ return Array.from(document.querySelectorAll('.mail-item .sel:checked')).map(x=> Number(x.getAttribute('data-id'))).filter(Boolean); }
  async function deleteSelected(purge=false){ const ids=selectedIds(); if(!ids.length){ alert('Vyber správy.'); return;} if(!purge && !confirm('Presunúť do Koša?')) return; if(purge && !confirm('Natrvalo vymazať?')) return; const r=await postJSON('/api/kancelaria/comm/delete',{ids, purge}); if(r.error) alert(r.error); else { await loadList(CURRENT_FILTER); $('#mail-read').innerHTML='<div class="muted empty">Vyberte správu zo zoznamu.</div>'; } }
  async function markSpamSelected(){ const ids=selectedIds(); if(!ids.length){ alert('Vyber správy.'); return;} const r=await postJSON('/api/kancelaria/comm/markSpam',{ids}); if(r.error) alert(r.error); else await loadList(CURRENT_FILTER); }

  async function openMessage(id){
    const data=await postJSON('/api/kancelaria/comm/get',{id}); const msg=data.message||{}; const atts=data.attachments||[];
    document.querySelectorAll('.mail-item.active').forEach(n=> n.classList.remove('active')); const node=document.querySelector(`.mail-item[data-id="${id}"]`); if(node) node.classList.add('active');
    const hdr=`<div class="read-header"><div class="read-title">${esc(msg.subject||'(bez predmetu)')}</div><div class="read-meta"><span class="from">${esc(msg.sender_name||'')} &lt;${esc(msg.sender_email||'')}&gt;</span><span class="dot">•</span><span class="date">${esc(fxDate(msg.date))}</span>${msg.customer_type?`<span class="chip chip-${String(msg.customer_type).toLowerCase()}">${esc(msg.customer_type)}</span>`:''}${msg.has_attachments?`<span class="chip">📎 príloha</span>`:''}</div><div class="read-actions"><button id="act-delete" class="btn">Kôš</button><button id="act-spam" class="btn btn-secondary">Spam</button><button id="act-reply" class="btn btn-primary">Odpovedať</button></div></div>`;
    const body = msg.body_html ? `<div class="read-body html">${msg.body_html}</div>` : `<pre class="read-body">${esc(msg.body_preview||'')}</pre>`;
   const att = atts.length ? `<div class="read-atts">` + atts.map(a =>
  `<a href="/api/kancelaria/comm/attachment/${a.id}" target="_blank" rel="noopener" class="att-link">
     📎 ${esc(a.filename)} <span class="muted">(${a.size} B)</span>
   </a>`
).join('') + `</div>` : '';

    $('#mail-read').innerHTML = hdr + body + att;
    await postJSON('/api/kancelaria/comm/markRead',{id, read:true}); updateUnreadBadge();
    $('#act-delete').onclick=()=> postJSON('/api/kancelaria/comm/delete',{ids:[id]}).then(async r=>{ if(r.error) alert(r.error); else { await loadList(CURRENT_FILTER); $('#mail-read').innerHTML='<div class="muted empty">Vyberte správu zo zoznamu.</div>'; } });
    $('#act-spam').onclick=()=> postJSON('/api/kancelaria/comm/markSpam',{ids:[id]}).then(async r=>{ if(r.error) alert(r.error); else await loadList(CURRENT_FILTER); });
    $('#act-reply').onclick=()=> openCompose({to: msg.sender_email || '', subject: `Re: ${msg.subject||''}`, body: quoteText(msg)});
  }
  function quoteText(msg){ const d=fxDate(msg.date); const header = `\n\nOn ${d}, ${msg.sender_name||msg.sender_email} wrote:\n`; const txt=(msg.body_preview||'').replace(/\r?\n/g,'\n> '); return header+'> '+txt; }

  function renderCounts(){ const c={ALL:0,UNREAD:0,B2B:0,B2C:0,LEAD:0,UNKNOWN:0,SPAM:0,TRASH:0}; (ALL_ITEMS||[]).forEach(it=>{ const del=!!it.is_deleted, sp=!!it.is_spam; if(!del) c.ALL++; if(!del && !it.is_read) c.UNREAD++; const t=String(it.customer_type||'UNKNOWN').toUpperCase(); if(!del && c[t]!=null) c[t]++; if(sp && !del) c.SPAM++; if(del) c.TRASH++; }); ['ALL','UNREAD','B2B','B2C','LEAD','UNKNOWN','SPAM','TRASH'].forEach(k=>{ const el=document.querySelector(`[data-count="${k}"]`); if(el) el.textContent=c[k]?String(c[k]):'';}); const b=$('#badge-unread'); if(b) b.textContent=String(c.UNREAD||0); const menu=$('#menu-unread'); if(menu) menu.textContent=(c.UNREAD>0?c.UNREAD:'');}
  function renderList(){ const list=$('#mail-list'); if(!list) return; const items=ALL_ITEMS.slice(); list.innerHTML = items.map(it=>{ const tag=`<span class="chip chip-${String(it.customer_type||'').toLowerCase()}">${esc(it.customer_type||'')}</span>`; const unread=it.is_read?'':'<span class="unread-dot"></span>'; const attach=it.has_attachments?'<span class="att-flag">📎</span>':''; const chk=`<input type="checkbox" class="sel" data-id="${it.id}">`; return `<div class="mail-item ${it.is_read?'':'unread'}" data-id="${it.id}"><div class="mi-check">${chk}</div><div class="mi-from" title="${esc(it.sender_email||'')}">${esc(it.sender_name || it.sender_email || '(bez mena)')}</div><div class="mi-subj">${unread}<span class="s">${esc(it.subject || '(bez predmetu)')}</span>${attach}</div><div class="mi-meta">${tag}<span class="mi-date">${esc(it.date||'')}</span></div></div>`; }).join(''); list.querySelectorAll('.mail-item').forEach(n=>{ n.onclick=(e)=>{ if(e.target.classList.contains('sel')) return; openMessage(n.getAttribute('data-id')); }; }); }

  function updateUnreadBadge(){ postJSON('/api/kancelaria/comm/unreadCount',{}).then(d=>{ const el=$('#badge-unread'); if(el) el.textContent=String(d.unread||0); const menu=$('#menu-unread'); if(menu) menu.textContent=(d.unread>0?d.unread:'');}).catch(()=>{}); }

  // --------- compose (modal) ---------
 function openCompose(opts){
  const overlay=document.createElement('div');
  overlay.className='compose-overlay';
  overlay.innerHTML = `
    <div class="compose-card">
      <div class="compose-head">
        <div class="title">Nová správa</div>
        <div class="actions">
          <button id="cmp-save-sig" class="btn btn-secondary">Uložiť podpis</button>
          <button id="cmp-settings" class="btn btn-secondary">Nastavenia</button>
          <button id="cmp-close" class="btn">Zatvoriť</button>
        </div>
      </div>

      <div class="compose-fields">
        <input id="cmp-to"  placeholder="Komu" value="${esc(opts?.to||'')}"/>
        <input id="cmp-cc"  placeholder="Kópia (CC)"/>
        <input id="cmp-bcc" placeholder="Skrytá kópia (BCC)"/>
        <input id="cmp-subj" placeholder="Predmet" value="${esc(opts?.subject||'')}"/>
      </div>

      <div class="editor-toolbar" style="flex-wrap:wrap;gap:8px">
        <div class="row" style="gap:6px;align-items:center">
          <label>Podpis</label>
          <select id="cmp-signatures" style="min-width:260px"></select>
          <button id="cmd-insert-sign" class="btn btn-secondary">Vložiť</button>
          <button id="cmd-make-default" class="btn btn-secondary">Predvolený</button>
          <button id="cmd-del-sign" class="btn btn-secondary">Zmazať</button>
        </div>

        <div class="row" style="gap:6px;align-items:center">
          <select id="cmd-fontsize">
            ${[12,14,16,18,20,24,28].map(n=>`<option value="${n}px">${n}px</option>`).join('')}
          </select>
          <input type="color" id="cmd-color" title="Farba písma">
          <button data-cmd="bold" class="btn">B</button>
          <button data-cmd="italic" class="btn"><em>I</em></button>
          <button data-cmd="underline" class="btn"><u>U</u></button>
          <button data-cmd="insertUnorderedList" class="btn">•</button>
          <button data-cmd="insertOrderedList" class="btn">1.</button>
          <button id="cmd-clear" class="btn">Vymazať formát</button>
        </div>
      </div>

      <div id="cmp-editor" class="editor-area" contenteditable="true"></div>

      <div class="compose-files">
        <input id="cmp-files" type="file" multiple>
        <button id="cmp-send" class="btn btn-primary">Odoslať</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  // Načítaj podpisy + prefs a naplň select
  (async ()=>{
    const cfg = await loadEditorConfig(true);
    const sel = document.getElementById('cmp-signatures');
    const sigs = cfg.signatures || [];
    sel.innerHTML = sigs.length
      ? sigs.map(s=>`<option value="${s.id}" ${s.is_default?'selected':''}>${esc(s.display_name||('Podpis '+s.id))}${s.is_default?' • predvolený':''}</option>`).join('')
      : `<option value="">(nemáš uložené podpisy)</option>`;

    const ed = document.getElementById('cmp-editor');
    if(cfg?.prefs){
      ed.style.color = cfg.prefs.font_color || '#111';
      ed.style.fontFamily = cfg.prefs.font_family || 'Inter, Arial, sans-serif';
      document.getElementById('cmd-fontsize').value = cfg.prefs.font_size || '14px';
      document.execCommand('foreColor', false, cfg.prefs.font_color || '#111');
    }
    if(opts?.body){ ed.textContent = opts.body; }
  })();

  // editor toolbar
  document.querySelectorAll('.editor-toolbar [data-cmd]').forEach(btn=>{
    btn.onclick = ()=> document.execCommand(btn.getAttribute('data-cmd'), false, null);
  });
  document.getElementById('cmd-fontsize').onchange = (e)=> document.execCommand('fontSize', false, '4');
  document.getElementById('cmd-color').onchange    = (e)=> document.execCommand('foreColor', false, e.target.value);
  document.getElementById('cmd-clear').onclick     = ()=> document.execCommand('removeFormat', false, null);

  // vložiť zvolený podpis
  document.getElementById('cmd-insert-sign').onclick = async ()=>{
    const cfg = await loadEditorConfig();
    const sel = document.getElementById('cmp-signatures');
    const id  = Number(sel.value);
    const sig = (cfg.signatures||[]).find(s=> Number(s.id)===id);
    if(sig && sig.signature_html){
      insertHTMLAtCursor(sig.signature_html);
    }else{
      alert('Nie je čo vložiť.');
    }
  };

  // nastaviť predvolený podpis
  document.getElementById('cmd-make-default').onclick = async ()=>{
    const cfg = await loadEditorConfig();
    const sel = document.getElementById('cmp-signatures');
    const id  = Number(sel.value||0);
    if(!id){ alert('Vyber podpis.'); return; }
    const r = await postJSON('/api/kancelaria/comm/setDefaultSignature', { id, owner_email: cfg.owner_email });
    if (r.error) alert(r.error); else { alert('Nastavený ako predvolený.'); await loadEditorConfig(true); }
  };

  // zmazať podpis
  document.getElementById('cmd-del-sign').onclick = async ()=>{
    const cfg = await loadEditorConfig();
    const sel = document.getElementById('cmp-signatures');
    const id  = Number(sel.value||0);
    if(!id){ alert('Vyber podpis.'); return; }
    if(!confirm('Naozaj zmazať podpis?')) return;
    const r = await postJSON('/api/kancelaria/comm/deleteSignature', { id, owner_email: cfg.owner_email });
    if (r.error) alert(r.error); else { alert('Podpis zmazaný.'); await loadEditorConfig(true);
      // reload výberu
      const cfg2 = await loadEditorConfig();
      const sigs = cfg2.signatures || [];
      sel.innerHTML = sigs.length
        ? sigs.map(s=>`<option value="${s.id}" ${s.is_default?'selected':''}>${esc(s.display_name||('Podpis '+s.id))}${s.is_default?' • predvolený':''}</option>`).join('')
        : `<option value="">(nemáš uložené podpisy)</option>`;
    }
  };

  // uložiť nový podpis (s tvojím firemným default HTML ako predvyplnený návrh)
  document.getElementById('cmp-save-sig').onclick = async ()=>{
    const cfg = await loadEditorConfig();
    const name = prompt('Názov podpisu …', 'Z. Káras – riadiaci pracovník');
if (name == null) return;
if (name.length > 200) { alert('Názov podpisu je príliš dlhý. Skráť ho, prosím.'); return; }


  const DEFAULT_SIG_HTML = `
<div style="font-family:Inter, Arial, sans-serif; font-size:14px; color:#111;">
  <div><strong>Bc. Zoltán Káras</strong></div>
  <div>+421 907 114 726</div>
  <div style="margin:10px 0;">Za</div>
  <div><strong>MIK, s.r.o.</strong></div>
  <div>Hollého 1999/13</div>
  <div>927 05 Šaľa</div>
  <div>IČO: 34 099 514</div>
  <div>DIČ: 2020374125</div>
  <div>IČ DPH: SK2020374125</div>
  <div style="margin-top:10px;"><strong>Kontakt:</strong> 031 771 2636, +421 908 717 505 – kancelárie; +421 905 518 114 – expedícia</div>
  <div><strong>Mail:</strong> <a href="mailto:miksro@slovanet.sk">miksro@slovanet.sk</a> – kancelárie; <a href="mailto:miksroexpedicia@gmail.com">miksroexpedicia@gmail.com</a> – expedícia</div>
</div>
`.trim();


    const html = prompt('HTML podpis (môžeš upraviť):', DEFAULT_SIG_HTML);
    if(html==null) return;

    const r = await postJSON('/api/kancelaria/comm/saveSignature', {
      owner_email: cfg.owner_email, display_name: name, signature_html: html, make_default: false
    });
    if (r.error) alert(r.error); else { alert('Podpis uložený.'); await loadEditorConfig(true); }
  };

  // nastavenia editora (písmo/veľkosť/farba)
  document.getElementById('cmp-settings').onclick = async ()=>{
    const cfg = await loadEditorConfig();
    const ff  = prompt('Písmo (CSS family):', cfg?.prefs?.font_family || 'Inter, Arial, sans-serif');
    if (ff==null) return;
    const fs  = prompt('Veľkosť písma (px):', cfg?.prefs?.font_size || '14px');
    if (fs==null) return;
    const col = prompt('Farba písma (#hex):', cfg?.prefs?.font_color || '#111111');
    if (col==null) return;
    const r = await postJSON('/api/kancelaria/comm/savePrefs', { owner_email: cfg.owner_email, font_family: ff, font_size: fs, font_color: col });
    if (r.error) alert(r.error); else { alert('Preferencie uložené.'); const ed=document.getElementById('cmp-editor'); ed.style.color = col; ed.style.fontFamily = ff; }
  };

  // odoslať
  document.getElementById('cmp-send').onclick = async ()=>{
    const fd = new FormData();
    fd.append('to',  document.getElementById('cmp-to').value || '');
    fd.append('cc',  document.getElementById('cmp-cc').value || '');
    fd.append('bcc', document.getElementById('cmp-bcc').value || '');
    fd.append('subject', document.getElementById('cmp-subj').value || '');
    const html = document.getElementById('cmp-editor').innerHTML;
    const text = document.getElementById('cmp-editor').innerText;
    fd.append('body', text);
    fd.append('body_html', html);
    const files = document.getElementById('cmp-files').files || [];
    for(let i=0;i<files.length;i++) fd.append('files', files[i]);
    try{
      const r = await fetch('/api/kancelaria/comm/send', {method:'POST', body: fd, credentials:'same-origin'});
      const t = await r.text(); let j; try{ j = JSON.parse(t);} catch{ throw new Error(t); }
      if (j.error) alert('Odoslanie zlyhalo: '+j.error);
      else { alert(j.message || 'Odoslané.'); document.body.removeChild(overlay); await loadList(CURRENT_FILTER); }
    }catch(e){ alert('Odoslanie zlyhalo: '+(e.message||e)); }
  };

  document.getElementById('cmp-close').onclick = ()=> document.body.removeChild(overlay);
}

  async function loadEditorConfig(force=false){
    if (EDITOR_CFG && !force) return EDITOR_CFG;
    const cfg = await postJSON('/api/kancelaria/comm/editorConfig', {});
    EDITOR_CFG = cfg; return cfg;
  }

  function insertHTMLAtCursor(html){
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) { $('#cmp-editor').insertAdjacentHTML('beforeend', html); return; }
    const range = sel.getRangeAt(0); range.deleteContents();
    const el = document.createElement('div'); el.innerHTML = html;
    const frag = document.createDocumentFragment(); let node, lastNode;
    while ((node = el.firstChild)) { lastNode = frag.appendChild(node); }
    range.insertNode(frag);
    if (lastNode) { range.setStartAfter(lastNode); range.collapse(true); sel.removeAllRanges(); sel.addRange(range); }
  }

  // --------- UI shell ---------
  function buildShell(){
    const sec = $('#section-communication'); if (!sec) return;
    sec.innerHTML = `
      <div class="mail-toolbar card">
        <div class="row wrap" style="gap:8px; align-items:center">
          <button id="btn-compose" class="btn btn-primary">Nová správa</button>
          <button id="btn-sync" class="btn">Synchronizovať</button>
          <button id="btn-probe" class="btn btn-secondary">Test pripojenia</button>
          <button id="btn-del" class="btn">Kôš</button>
          <button id="btn-del-hard" class="btn">Vymazať navždy</button>
          <button id="btn-spam" class="btn btn-secondary">Spam</button>
          <div class="spacer"></div>
          <input id="mail-search" type="search" placeholder="Hľadať v správach…"/>
          <span class="badge">Neprečítané: <strong id="badge-unread">0</strong></span>
        </div>
      </div>

      <div class="mail-layout">
        <aside class="mail-filters card">
          <ul>
            <li data-type="ALL" class="active">Doručená pošta <span data-count="ALL" class="count"></span></li>
            <li data-type="UNREAD">Neprečítané <span data-count="UNREAD" class="count"></span></li>
            <li data-type="B2B">B2B <span data-count="B2B" class="count"></span></li>
            <li data-type="B2C">B2C <span data-count="B2C" class="count"></span></li>
            <li data-type="LEAD">LEAD <span data-count="LEAD" class="count"></span></li>
            <li data-type="UNKNOWN">Ostatné <span data-count="UNKNOWN" class="count"></span></li>
            <li data-type="SPAM">Spam <span data-count="SPAM" class="count"></span></li>
            <li data-type="TRASH">Kôš <span data-count="TRASH" class="count"></span></li>
          </ul>
        </aside>

        <section class="mail-list card" id="mail-list"><div class="muted" style="padding:12px">Načítavam…</div></section>
        <section class="mail-read card" id="mail-read"><div class="muted empty">Vyberte správu zo zoznamu.</div></section>
      </div>
    `;
    $('#btn-sync').onclick=syncInbox; $('#btn-probe').onclick=probeSMTP; $('#btn-del').onclick=()=>deleteSelected(false); $('#btn-del-hard').onclick=()=>deleteSelected(true); $('#btn-spam').onclick=markSpamSelected;
    $('#mail-search').oninput=(e)=>{ /* klientské vyhľadávanie – voliteľne doplníme */ };
    document.querySelectorAll('.mail-filters [data-type]').forEach(li=>{ li.onclick=async ()=>{ document.querySelectorAll('.mail-filters [data-type].active').forEach(n=>n.classList.remove('active')); li.classList.add('active'); await loadList(li.getAttribute('data-type')); }; });
    $('#btn-compose').onclick=()=> openCompose({});
    updateUnreadBadge(); loadList('ALL');
  }

  async function probeSMTP(){ try{ const r=await fetch('/api/kancelaria/comm/smtpProbe',{method:'POST', headers:{'Content-Type':'application/json'}, credentials:'same-origin', body:'{}'}); const t=await r.text(); let j; try{ j=JSON.parse(t);} catch{ throw new Error(t);} if(!j.ok) alert(`SMTP PROBE: zlyhalo\nconnected=${j.connected}\nlogin=${j.login}\nerror=${j.error||'?'}\n${j.host}:${j.port} ssl=${j.ssl} tls=${j.tls}`); else alert(`SMTP PROBE: ok\nhost=${j.host}:${j.port}\nssl=${j.ssl} tls=${j.tls}\nfrom=${j.from}\nlogin=${j.login}`);}catch(e){ alert('SMTP PROBE chyba: '+(e.message||e)); } }

  document.addEventListener('DOMContentLoaded', buildShell);
  window.initializeCommunicationModule = buildShell;
})();