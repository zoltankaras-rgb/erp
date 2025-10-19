
function showModal(title, contentCallback) {
    const container = document.getElementById('modal-container');
    if (!container) return;

    container.innerHTML = '';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'modal-content';

    const header = document.createElement('div');
    header.className = 'modal-header';
    header.innerHTML = `<h3>${title}</h3>
        <button class="close-btn" onclick="document.getElementById('modal-container').style.display='none'">&times;</button>`;

    contentDiv.appendChild(header);

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'modal-body';
    bodyDiv.innerHTML = '<p>Načítavam...</p>';
    contentDiv.appendChild(bodyDiv);
    container.appendChild(contentDiv);
    container.style.display = 'flex';

    Promise.resolve(typeof contentCallback === 'function' ? contentCallback() : null)
        .then(result => {
            if (!result) {
                bodyDiv.innerHTML = '<p>Chyba: Nezískal sa obsah modálu.</p>';
                return;
            }
            if (typeof result === 'string') {
                bodyDiv.innerHTML = result;
            } else if (typeof result === 'object' && result.html) {
                bodyDiv.innerHTML = result.html;
                if (typeof result.onReady === 'function') result.onReady();
            } else {
                bodyDiv.innerHTML = '<p>Neočakávaný obsah.</p>';
            }
        })
        .catch(err => {
            console.error("Modál chyba:", err);
            bodyDiv.innerHTML = '<p style="color:red;">Chyba pri načítaní obsahu.</p>';
        });
}
