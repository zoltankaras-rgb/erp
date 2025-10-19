
// =============================================================================
// AUTH GATE — jednotné prihlásenie pre všetky moduly (vyroba/expedicia/kancelaria)
// - vždy najprv login
// - skryje moduly, kým nie je session
// - fronta API requestov počas neprihlásenia (žiadne 403)
// =============================================================================

// -------------- Helpers --------------
(function(){
  const APP_IDS = ['expedicia-app','vyroba-app','kancelaria-app'];
  const LOGIN_ID = 'login-wrapper';

  function getCookie(name){
    return document.cookie.split('; ').reduce((acc, cur) => {
      const [k, v] = cur.split('=');
      return k === name ? decodeURIComponent(v) : acc;
    }, '');
  }
  function show(el, on){ if (!el) return; el.style.display = on ? '' : 'none'; }
  function $(sel){ return document.querySelector(sel); }
  function byId(id){ return document.getElementById(id); }
  function msg(el, text, isErr){
    if (!el) return;
    el.textContent = text || '';
    el.style.color = isErr ? '#b91c1c' : '#065f46';
  }

  // -------------- Inject minimal styles --------------
  function injectStyles(){
    if (byId('__auth_gate_css')) return;
    const css = document.createElement('style');
    css.id = '__auth_gate_css';
    css.textContent = `
      #${LOGIN_ID}{max-width:380px;margin:8vh auto;padding:18px;border:1px solid #ddd;border-radius:8px;background:#fff;box-shadow:0 8px 24px rgba(0,0,0,.08)}
      #${LOGIN_ID} .login-card h2{margin:0 0 10px;font-size:20px}
      #${LOGIN_ID} label{display:block;margin:8px 0 4px}
      #${LOGIN_ID} input{width:100%;padding:8px;border:1px solid #ccc;border-radius:6px}
      #${LOGIN_ID} .btn{margin-top:12px;display:inline-block;background:#0ea5e9;color:#fff;border:0;border-radius:6px;padding:8px 12px;cursor:pointer}
      #${LOGIN_ID} .muted{margin-top:8px;color:#666}
      body.auth-locked{background:#f6f7f9}
    `;
    document.head.appendChild(css);
  }

  // -------------- Build login form (if missing) --------------
  function ensureLogin(){
    let wrap = byId(LOGIN_ID);
    if (wrap) return wrap;
    wrap = document.createElement('div');
    wrap.id = LOGIN_ID;
    wrap.className = 'login-container';
    wrap.innerHTML = `
      <div class="login-card">
        <h2>Prihlásenie</h2>
        <form id="login-form" autocomplete="on">
          <label for="username">Používateľské meno</label>
          <input id="username" name="username" type="text" autocomplete="username" required>
          <label for="password">Heslo</label>
          <input id="password" name="password" type="password" autocomplete="current-password" required>
          <button type="submit" class="btn">Prihlásiť</button>
        </form>
        <div id="login-status" class="muted" aria-live="polite"></div>
      </div>
    `;
    document.body.prepend(wrap);
    return wrap;
  }

  function hideApps(){ APP_IDS.forEach(id => show(byId(id), false)); }
  function showApps(){ APP_IDS.forEach(id => show(byId(id), true)); }

  // -------------- CSRF header --------------
  function csrfHeader(h){
    const xsrf = getCookie('XSRF-TOKEN') || getCookie('csrf_token') ||
                 (document.querySelector('meta[name="csrf-token"]')?.content || '');
    if (xsrf && !h['X-CSRF-Token']) h['X-CSRF-Token'] = xsrf;
  }

  // -------------- Fetch queue while unauth --------------
  const _fetch = window.fetch.bind(window);
  let AUTH = { ok: false };
  const queue = [];
  function allowNow(url){
    return url.includes('/api/internal/login') || url.includes('/api/internal/check_session') || !url.includes('/api/');
  }
  window.fetch = function(input, init){
    const url = (typeof input === 'string') ? input : (input?.url || '');
    if (!AUTH.ok && !allowNow(url)){
      return new Promise((resolve, reject) => {
        queue.push({input, init, resolve, reject});
      });
    }
    return _fetch(input, init);
  };
  async function flushQueue(){
    while (queue.length){
      const {input, init, resolve, reject} = queue.shift();
      try{ resolve(await _fetch(input, init)); } catch(e){ reject(e); }
    }
  }

  // -------------- Session check --------------
  async function checkSession(){
    try{
      const r = await _fetch('/api/internal/check_session', {credentials:'include'});
      if (!r.ok) return false;
      const j = await r.json();
      return !!(j && (j.loggedIn || j.authenticated || j.ok || (j.user && j.user.id)));
    }catch(_){ return false; }
  }

  // -------------- Login flow --------------
  async function doLogin(u, p){
    const headers = {'Content-Type':'application/json'}; csrfHeader(headers);
    let r = await _fetch('/api/internal/login', {method:'POST', credentials:'include', headers, body: JSON.stringify({username:u, password:p})});
    if (r.ok) return true;
    // fallback
    r = await _fetch('/api/auth/login', {method:'POST', credentials:'include', headers, body: JSON.stringify({username:u, password:p})});
    if (r.ok) return true;
    const h = {'Content-Type':'application/x-www-form-urlencoded'}; csrfHeader(h);
    r = await _fetch('/login', {method:'POST', credentials:'include', headers:h, body: new URLSearchParams({username:u, password:p})});
    return (r.ok || r.status === 302);
  }

  // -------------- Gate init --------------
  document.addEventListener('DOMContentLoaded', async () => {
    injectStyles();
    const logged = await checkSession();
    if (logged){
      AUTH.ok = true;
      document.body.classList.remove('auth-locked');
      showApps();
      await flushQueue();
      window.dispatchEvent(new CustomEvent('app:auth-ready'));
      return;
    }

    // not logged → show login, hide apps
    document.body.classList.add('auth-locked');
    hideApps();
    const wrap = ensureLogin();
    const form = wrap.querySelector('#login-form');
    const u = wrap.querySelector('#username');
    const p = wrap.querySelector('#password');
    const status = wrap.querySelector('#login-status');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      e.stopImmediatePropagation();
      const user = (u?.value || '').trim();
      const pass = p?.value || '';
      if (!user || !pass){ msg(status, 'Zadajte meno a heslo.', true); return; }
      const btn = form.querySelector('button[type="submit"]'); if (btn) btn.disabled = true;
      try{
        const ok = await doLogin(user, pass);
        if (ok){
          AUTH.ok = true;
          msg(status, 'Prihlásenie OK…', false);
          // Skry login, ukáž app a dobehni zvyšné requesty
          showApps();
          wrap.setAttribute('hidden',''); wrap.style.display='none';
          await flushQueue();
          // daj modulom signál, že môžu inicializovať
          window.dispatchEvent(new CustomEvent('app:auth-ready'));
        } else {
          msg(status, 'Prihlásenie zlyhalo.', true);
        }
      } finally {
        if (btn) btn.disabled = false;
      }
    }, true);
  });
})();
