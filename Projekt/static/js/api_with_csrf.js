// /static/js/api_with_csrf.js
function readCsrf() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export async function apiRequest(url, { method='GET', body=null, headers={} } = {}) {
  const token = readCsrf();
  const h = {
    'Accept': 'application/json',
    ...(body ? { 'Content-Type': 'application/json' } : {}),
    'X-CSRF-Token': token,
    ...headers
  };
  const opts = { method, credentials: 'same-origin', headers: h };
  if (body) opts.body = (typeof body === 'string') ? body : JSON.stringify({ ...body, csrf_token: token });

  const res = await fetch(url, opts);
  const text = await res.text();
  let data; try { data = JSON.parse(text); } catch { data = { error: text || `HTTP ${res.status}` }; }
  if (!res.ok || data?.error) throw new Error(data?.error || `HTTP ${res.status}`);
  return data;
}

// pohodlné aliasy
export const getJSON  = (url)       => apiRequest(url, { method:'GET' });
export const postJSON = (url, body) => apiRequest(url, { method:'POST', body });
