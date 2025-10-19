// static/js/api_with_csrf.js  (Uložiť ako UTF-8, bez BOM)

function getCookie(name) {
  return document.cookie.split("; ").reduce((acc, c) => {
    const [k, v] = c.split("=");
    return k === name ? decodeURIComponent(v) : acc;
  }, "");
}

async function _fetch(url, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const xsrf = getCookie("XSRF-TOKEN");
  if (xsrf) headers["X-CSRF-Token"] = xsrf;

  const res = await fetch(url, { credentials: "same-origin", ...opts, headers });

  if (res.status === 401) {
    // nie si prihlásený → priamo na login Kancelárie
    window.location.href = "/kancelaria";
    throw new Error("401 – neprihlásený");
  }
  if (res.status === 403) {
    const t = await res.text();
    throw new Error(t || "403 – bez oprávnenia");
  }
  if (!res.ok) {
    throw new Error(await res.text());
  }

  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export async function postJSON(url, data = {}) { return _fetch(url, { method: "POST", body: JSON.stringify(data) }); }
export async function putJSON (url, data = {}) { return _fetch(url, { method: "PUT" , body: JSON.stringify(data) }); }
export async function getJSON (url)            { return _fetch(url, { method: "GET"  }); }
export async function delJSON (url, data)     {
  const opts = { method: "DELETE" };
  if (data !== undefined) opts.body = JSON.stringify(data);
  return _fetch(url, opts);
}
