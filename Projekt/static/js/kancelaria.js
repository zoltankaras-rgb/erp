// static/js/kancelaria.js — robustná navigácia + bezpečné initOnce

document.addEventListener('DOMContentLoaded', () => {
  setupSidebarNavigation();
  initializeOfficeModule();
});

/* ================== CORE HELPERS ================== */

window.__modules_inited  = window.__modules_inited  || {};
window.__modules_waiters = window.__modules_waiters || {};

function resolveInitFn(fnOrName) {
  if (typeof fnOrName === 'function') return fnOrName;
  if (typeof fnOrName === 'string')   return window[fnOrName];
  return undefined;
}

/**
 * Spusť inicializáciu modulu max. 'tries' krát (default 25x) s oneskorením 100 ms.
 */
function initOnce(key, fnOrName, tries = 25, delayMs = 100) {
  if (window.__modules_inited[key]) return;

  const tryInit = () => {
    const fn = resolveInitFn(fnOrName);
    if (typeof fn === 'function') {
      try {
        fn();
        window.__modules_inited[key] = true;
        if (window.__modules_waiters[key]) {
          clearTimeout(window.__modules_waiters[key]);
          delete window.__modules_waiters[key];
        }
        return;
      } catch (e) {
        console.warn(`[initOnce] Modul '${key}' zlyhal pri spustení:`, e);
      }
    }
    if (tries > 0) {
      window.__modules_waiters[key] = setTimeout(() => initOnce(key, fnOrName, tries - 1, delayMs), delayMs);
    } else {
      console.warn(`[initOnce] Modul '${key}' sa nepodarilo spustiť (nenašiel som window.${typeof fnOrName === 'string' ? fnOrName : 'initialize<Modul>'}).`);
    }
  };

  tryInit();
}

/* =============== NAVIGATION / LAYOUT =============== */

function setupSidebarNavigation() {
  const $all = (sel) => Array.from(document.querySelectorAll(sel));
  const navLinks = $all('.nav-link, .sidebar-link');

  const SECTION_INIT = {
    'section-erp'              : 'initializeErpAdminModule', 
    'section-erp-admin'        : 'initializeErpAdminModule',
    'section-stock'            : 'initializeStockModule',
    'section-planning'         : 'initializePlanningModule',
    'section-order-forecast'   : 'initializeOrderForecastModule',
    'section-fleet'            : 'initializeFleetModule',
    'section-hygiene'          : 'initializeHygieneModule',
    'section-profitability'    : 'initializeProfitabilityModule',
    'section-costs'            : 'initializeCostsModule',
    'section-dashboard'        : 'initializeDashboardModule',
    'section-b2b'              : 'initializeB2BModule',
    'section-b2c'              : 'initializeB2CModule',
    'section-ai'               : 'initializeAIModule',
    'section-communication'    : 'initializeCommunicationModule',
    'section-haccp'            : 'initializeHaccpModule',
    'section-akcie'            : 'initializeAkcieModule',

  };

  function normalizeTargetId(sectionKey) {
    if (!sectionKey) return '';
    return sectionKey.startsWith('section-') ? sectionKey : `section-${sectionKey}`;
  }

  function activateSection(targetId) {
    $all('.nav-link, .sidebar-link').forEach(l => l.classList.remove('active'));
    const match = $all('.nav-link, .sidebar-link').find(
      a => normalizeTargetId(a.getAttribute('data-section') || '') === targetId
    );
    if (match) match.classList.add('active');

    $all('.section, .content-section').forEach(sec => sec.classList.remove('active'));
    const target = document.getElementById(targetId);
    if (target) target.classList.add('active');

    try {
      const hash = '#' + targetId.replace(/^section-/, '');
      if (location.hash !== hash) history.replaceState(null, '', hash);
    } catch {}

   const initName = SECTION_INIT[targetId];
if (!initName) {
  console.warn(`[initOnce] Chýba mapovanie pre ${targetId} v SECTION_INIT.`);
} else {
  try {
    initOnce(
      initName.replace(/^initialize/i, '').toLowerCase(),
      initName
    );
  } catch (e) {
    console.warn(`[initOnce] Zlyhalo spustenie ${initName}:`, e);
  }
}


    try { document.querySelector('.content')?.scrollTo({ top: 0, behavior: 'smooth' }); } catch {}
  }

  navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const sectionKey = link.getAttribute('data-section') || '';
      const targetId = normalizeTargetId(sectionKey);
      if (!targetId) return;
      activateSection(targetId);
    });
  });

  window.addEventListener('hashchange', () => {
    const raw = (location.hash || '').replace(/^#/, '');
    const key = (raw.split(':')[0] || '').trim();
    if (!key) return;
    const targetId = normalizeTargetId(key);
    const target = document.getElementById(targetId);
    if (target) activateSection(targetId);
  });
}

/* =============== DEFAULT STARTUP =============== */
function initializeOfficeModule() {
  const rawHash = (location.hash || '').replace(/^#/, '');
  const hashKey = (rawHash.split(':')[0] || '');
  const hashTarget = hashKey
    ? document.getElementById(hashKey.startsWith('section-') ? hashKey : `section-${hashKey}`)
    : null;

  let defaultLink =
    (hashTarget && document.querySelector(`.nav-link[data-section="${hashKey}"], .sidebar-link[data-section="${hashKey}"]`)) ||
    document.querySelector('.nav-link[data-section="dashboard"]') ||
    document.querySelector('.sidebar-link[data-section="section-dashboard"]') ||
    document.querySelector('.nav-link, .sidebar-link');

  defaultLink?.click();

  if (hashTarget && !defaultLink) {
    const targetId = hashKey.startsWith('section-') ? hashKey : `section-${hashKey}`;
    const SECTION_INIT = { 'section-stock':'initializeStockModule' };
    document.querySelectorAll('.section, .content-section').forEach(sec => sec.classList.remove('active'));
    hashTarget.classList.add('active');
    const initName = SECTION_INIT[targetId];
    if (initName) initOnce(initName.replace(/^initialize/i, '').toLowerCase(), initName);
  }
}

/* =============== CSRF + LOGOUT =============== */
function getCookie(name){
  return document.cookie.split('; ').reduce((a,c)=>{
    const [k,v]=c.split('='); return k===name?decodeURIComponent(v):a;
  },'');
}

(function(){
  const btn = document.getElementById('logout-btn');
  if (!btn) return;
  btn.setAttribute('type', 'button');
  btn.addEventListener('click', async (e)=>{
    e.preventDefault();
    e.stopPropagation();
    try {
      await fetch('/api/internal/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCookie('XSRF-TOKEN')
        }
      });
    } catch {}
    window.location.href = '/kancelaria';
  });
})();
/* === Globálny init pre kancelaria.js === */
window.initializeErpAdminModule = window.initializeErpAdminModule || function(){
  if (window.__erpAdminInited) return;
  window.__erpAdminInited = true;

  // sekcia ERP musí existovať
  const root = document.getElementById('section-erp') || document.getElementById('section-erp-admin');
  if (!root) {
    console.warn('[ERP Admin] Sekcia #section-erp nie je v DOM.');
    return;
  }

  // ak tvoja kostra tlačidiel ešte nebola vložená, spraví ju kód hore;
  // tu len ukážeme prehľad a načítame dáta
  const tabOverview = document.getElementById('erp-tab-overview');
  if (tabOverview) {
    tabOverview.click();              // spustí tvoj onClick → showPanel('erp-panel-overview') + loadOverview()
  } else {
    // fallback: skry ostatné panely a ukáž prehľad + načítaj dáta
    ['erp-panel-overview','erp-panel-addcat','erp-panel-addprod','erp-panel-recipes']
      .forEach(pid => { const el = document.getElementById(pid); if (el) el.style.display = (pid==='erp-panel-overview'?'':'none'); });
    loadOverview();
  }
};
