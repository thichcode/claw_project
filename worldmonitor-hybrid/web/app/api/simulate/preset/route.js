import { NextResponse } from "next/server";

const INTERNAL = process.env.API_URL_INTERNAL || "http://localhost:8000";

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

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export async function POST(req) {
  try {
    const body = await req.json().catch(() => ({}));
    const preset = String(body?.preset || "normal").toLowerCase();
    const resetBeforeInject = body?.reset !== false;

    const profiles = {
      normal: { severities: ["info", "warning", "warning"], incidentChance: 0.05, n: 10 },
      degraded: { severities: ["warning", "high", "warning"], incidentChance: 0.25, n: 12 },
      "incident-storm": { severities: ["critical", "high", "critical"], incidentChance: 0.6, n: 14 },
    };

    if (!profiles[preset]) {
      return NextResponse.json({ error: "unsupported preset" }, { status: 400 });
    }

    const services = [
      { name: "api-gateway", loc: "hcm-dc1", title: "API latency elevated" },
      { name: "keycloak", loc: "hcm-dc1", title: "Auth error burst" },
      { name: "data-pipeline", loc: "sgp-az1", title: "Kafka backlog growing" },
      { name: "payment", loc: "sgp-az1", title: "Payment timeout spike" },
      { name: "redis-cluster", loc: "hn-edge", title: "Cache pressure high" },
    ];

    const p = profiles[preset];
    const token = await login();
    const headers = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    };

    let events = 0;
    let incidents = 0;
    let resetAlerts = 0;
    let resetIncidents = 0;

    if (resetBeforeInject) {
      const rr = await fetch(`${INTERNAL}/demo/reset`, {
        method: "POST",
        headers,
        body: JSON.stringify({ preset }),
        cache: "no-store",
      });
      if (rr.ok) {
        // count fields are best-effort display only
        resetAlerts = -1;
        resetIncidents = -1;
      }
    }

    for (let i = 0; i < p.n; i++) {
      const svc = pick(services);
      const severity = pick(p.severities);

      const ingestBody = {
        source: "zabbix",
        fingerprint: `preset-${preset}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
        service_name: svc.name,
        severity,
        title: `[${preset}] ${svc.title}`,
        location_code: svc.loc,
        payload: {
          simulated: true,
          preset,
          ts: new Date().toISOString(),
        },
      };

      const r = await fetch(`${INTERNAL}/ingest/zabbix`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ingestBody),
        cache: "no-store",
      });
      if (r.ok) events += 1;

      if (Math.random() < p.incidentChance) {
        const incSeverity = severity === "critical" ? "critical" : "high";
        const incBody = {
          title: `[${preset}] ${svc.title}`,
          severity: incSeverity,
          location_code: svc.loc,
        };
        const ir = await fetch(`${INTERNAL}/incidents`, {
          method: "POST",
          headers,
          body: JSON.stringify(incBody),
          cache: "no-store",
        });
        if (ir.ok) incidents += 1;
      }
    }

    return NextResponse.json({ ok: true, preset, events, incidents, resetAlerts, resetIncidents });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
