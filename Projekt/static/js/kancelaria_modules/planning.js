
function initializePlanningModule() {
    document.getElementById('btn-plan-1')?.addEventListener('click', () => {
        showModal("Plánovanie 1", () => ({ html: "<p>Obsah plánovania 1</p>" }));
    });
    document.getElementById('btn-plan-2')?.addEventListener('click', () => {
        showModal("Plánovanie 2", () => ({ html: "<p>Obsah plánovania 2</p>" }));
    });
    document.getElementById('btn-plan-3')?.addEventListener('click', () => {
        showModal("Plánovanie 3", () => ({ html: "<p>Obsah plánovania 3</p>" }));
    });
}
