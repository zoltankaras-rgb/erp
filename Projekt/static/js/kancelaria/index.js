function showSection(id){
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  document.getElementById(`section-${id}`).classList.add('active');
  document.querySelectorAll('.sidebar a').forEach(a=>a.classList.remove('active'));
  document.querySelector(`.sidebar a[data-section="${id}"]`)?.classList.add('active');
}
document.querySelectorAll('.sidebar a').forEach(a=>{
  a.addEventListener('click', ()=> showSection(a.dataset.section));
});
// static/js/kancelaria/index.js
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
        headers: { 'Content-Type': 'application/json' }
      });
    } catch {}
    window.location.href = '/kancelaria'; // login
  });
})();
// --- expose pre loader kancelaria.js ---
(function(){
  const candidate =
    (typeof buildShell === 'function'        && buildShell)        ||
    (typeof initOnce === 'function'          && initOnce)          ||
    (typeof initializePlanning === 'function'&& initializePlanning)||
    (typeof initialize === 'function'        && initialize)        ||
    function(){ /* no-op */ };

  window.initializePlanningModule = candidate;
})();
