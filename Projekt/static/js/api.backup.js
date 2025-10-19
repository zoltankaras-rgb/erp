// static/js/api.js

// jednotný POST helper (posiela session cookie; po 401 presmeruje na /kancelaria)
export async function postJSON(url, data = {}) {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  if (res.status === 401) {
    window.location.href = '/kancelaria';   // vypršala session → login
    throw new Error('401 – neprihlásený');
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// GET helper (na ne-JSON POSTy nepoužívaj)
export async function postJSON(url, data = {}) {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  if (res.status === 401) {
    // NEpresmeruj – len vyhoď chybu, aby si videl v konzole
    throw new Error('401 – neprihlásený');
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJSON(url) {
  const res = await fetch(url, { credentials: 'same-origin' });
  if (res.status === 401) {
    throw new Error('401 – neprihlásený');
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
