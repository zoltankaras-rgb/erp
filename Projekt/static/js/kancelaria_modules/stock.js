// načítaj kategórie
async function loadRawCategories() {
  const res = await fetch('/api/kancelaria/raw/getCategories', { method:'POST' });
  const data = await res.json();
  // naplň <select> z data.categories
}

// založ surovinu
async function addMaterialProduct({name, ean, category_id, min_stock, dph}) {
  const res = await fetch('/api/kancelaria/raw/addMaterialProduct', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, ean, category_id, min_stock, dph})
  });
  return res.json();
}

// príjem do skladu
async function receiveMaterial({warehouse_id=1, product, qty, unit_cost, supplier}) {
  const res = await fetch('/api/kancelaria/raw/receive', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({warehouse_id, product, qty, unit_cost, supplier})
  });
  return res.json();
}

// odpis zo skladu
async function writeoffMaterial({warehouse_id=1, product, qty, reason_code=1, reason_text, actor_user_id}) {
  const res = await fetch('/api/kancelaria/raw/writeoff', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({warehouse_id, product, qty, reason_code, reason_text, actor_user_id})
  });
  return res.json();
}

// prehľad skladu pre dashboard (len suroviny)
async function loadRawOverview({warehouse_id=1, category_id=null} = {}) {
  const res = await fetch('/api/kancelaria/raw/list', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({warehouse_id, category_id})
  });
  return res.json();
}
