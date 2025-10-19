// static/js/api.js
export async function postJSON(url, data = {}) {
  const res = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  if (res.status === 401) throw new Error("401 – neprihlásený");
  if (res.status === 403) throw new Error("403 – bez oprávnenia");
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJSON(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  if (res.status === 401) throw new Error("401 – neprihlásený");
  if (res.status === 403) throw new Error("403 – bez oprávnenia");
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
