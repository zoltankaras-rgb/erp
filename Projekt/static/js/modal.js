
function showModal(title, contentCallback) {
    const container = document.getElementById('modal-container');
    if (!container) return;

    container.innerHTML = '';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'modal-content';

    const header = document.createElement('div');
    header.className = 'modal-header';
    header.innerHTML = `<h3>${title}</h3><button class="close-btn" onclick="document.getElementById('modal-container').style.display='none'">&times;</button>`;

    contentDiv.appendChild(header);

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'modal-body';
    bodyDiv.innerHTML = '<p>Načítavam...</p>';
    contentDiv.appendChild(bodyDiv);
    container.appendChild(contentDiv);
    container.style.display = 'flex';

    Promise.resolve(contentCallback?.()).then(result => {
        if (!result) return bodyDiv.innerHTML = '<p>Chyba načítania obsahu.</p>';
        if (typeof result === 'string') bodyDiv.innerHTML = result;
        else if (typeof result === 'object' && result.html) {
            bodyDiv.innerHTML = result.html;
            result.onReady?.();
        } else {
            bodyDiv.innerHTML = '<p>Neočakávaný formát obsahu.</p>';
        }
    }).catch(err => {
        console.error("Chyba v modále:", err);
        bodyDiv.innerHTML = '<p style="color:red;">Chyba pri načítaní obsahu.</p>';
    });
}
