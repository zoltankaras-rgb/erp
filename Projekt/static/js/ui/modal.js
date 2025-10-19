export function openModal(html){
  const root = document.getElementById('modal-root');
  root.classList.remove('hidden');
  root.innerHTML = `<div class="modal">${html}</div>`;
  root.onclick = (e)=>{ if(e.target===root) closeModal(); };
}
export function closeModal(){
  const root = document.getElementById('modal-root');
  root.classList.add('hidden');
  root.innerHTML = '';
}
