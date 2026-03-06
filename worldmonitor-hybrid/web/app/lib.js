const INTERNAL = process.env.API_URL_INTERNAL || "http://localhost:8000";
const PUBLIC = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let cachedToken = null;
let cachedTokenExpireAt = 0;
let inflightTokenPromise = null;

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

async function getAuthToken() {
  const now = Date.now();
  if (cachedToken && now < cachedTokenExpireAt) return cachedToken;

  if (!inflightTokenPromise) {
    inflightTokenPromise = login()
      .then((token) => {
        cachedToken = token;
        cachedTokenExpireAt = Date.now() + 55 * 1000;
        return token;
      })
      .finally(() => {
        inflightTokenPromise = null;
      });
  }

  return inflightTokenPromise;
}

async function authHeaders() {
  const token = await getAuthToken();
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

function resetCachedToken() {
  cachedToken = null;
  cachedTokenExpireAt = 0;
}

export async function apiGet(path) {
  const headers = await authHeaders();
  let r = await fetch(`${INTERNAL}${path}`, { headers, cache: "no-store" });

  if (r.status === 401) {
    resetCachedToken();
    const retryHeaders = await authHeaders();
    r = await fetch(`${INTERNAL}${path}`, { headers: retryHeaders, cache: "no-store" });
  }

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
  let r = await fetch(`${INTERNAL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (r.status === 401) {
    resetCachedToken();
    const retryHeaders = await authHeaders();
    r = await fetch(`${INTERNAL}${path}`, {
      method: "POST",
      headers: retryHeaders,
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  }

  if (!r.ok) throw new Error(`api post error: ${path}`);
  return r.json();
}

export { PUBLIC };
