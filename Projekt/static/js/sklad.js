// =================================================================
// === MODUL SKLAD ===
// =================================================================

async function initializeSkladModule() {
    const container = document.getElementById('warehouse-container');
    container.innerHTML = '<p>Načítavam sklad...</p>';

    try {
        const data = await apiRequest('/api/sklad/getWarehouse');

        let html = '';
        html += renderWarehouseCategory('Mäso', data.meat);
        html += renderWarehouseCategory('Koreniny', data.spices);
        html += renderWarehouseCategory('Obaly - Črevá', data.casings);
        html += renderWarehouseCategory('Pomocný materiál', data.auxiliary);

        container.innerHTML = html;

    } catch (e) {
        container.innerHTML = `<p class="error">Chyba: ${e.message}</p>`;
    }
}

function renderWarehouseCategory(title, items) {
    if (!items || items.length === 0) {
        return `<h3>${title}</h3><p><i>Žiadne položky</i></p>`;
    }

    let rows = items.map(item => `
        <tr class="${item.quantity < item.minStock ? 'low-stock' : ''}">
            <td>${item.name}</td>
            <td>${item.quantity}</td>
            <td>${item.price} € / kg</td>
            <td>Min: ${item.minStock}</td>
        </tr>
    `).join('');

    return `
        <h3>${title}</h3>
        <div class="table-container">
            <table>
                <thead><tr><th>Názov</th><th>Množstvo</th><th>Cena</th><th>Min. zásoba</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
}
