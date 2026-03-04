const INTERNAL = process.env.API_URL_INTERNAL || "http://localhost:8000";
const PUBLIC = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function login() {
  const r = await fetch(`${INTERNAL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "admin" }),
    cache: "no-store",
  });
  if (!r.ok) throw new Error("login failed");
  const data = await r.json();
  return data.access_token;
}

async function authHeaders() {
  const token = await login();
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

export async function apiGet(path) {
  const headers = await authHeaders();
  const r = await fetch(`${INTERNAL}${path}`, { headers, cache: "no-store" });
  if (!r.ok) throw new Error(`api error: ${path}`);
  return r.json();
}

export async function safeApiGet(path, fallbackData) {
  try {
    return await apiGet(path);
  } catch {
    return fallbackData;
  }
}

export async function apiPost(path, payload = {}) {
  const headers = await authHeaders();
  const r = await fetch(`${INTERNAL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`api post error: ${path}`);
  return r.json();
}

export { PUBLIC };
