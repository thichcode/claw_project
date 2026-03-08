const http = require('http');

let nextAlertId = 1;
let nextIncidentId = 1;

const services = [
  { id: 1, name: 'api-gateway', location_code: 'hcm-dc1' },
  { id: 2, name: 'keycloak', location_code: 'hcm-dc1' },
  { id: 3, name: 'data-pipeline', location_code: 'sgp-az1' },
  { id: 4, name: 'payment', location_code: 'sgp-az1' },
  { id: 5, name: 'redis-cluster', location_code: 'hn-edge' },
];

const locations = [
  { id: 1, code: 'hcm-dc1', name: 'HCM Datacenter 1', level: 'site', services: 2 },
  { id: 2, code: 'sgp-az1', name: 'Singapore AZ1', level: 'zone', services: 2 },
  { id: 3, code: 'hn-edge', name: 'Ha Noi Edge', level: 'site', services: 1 },
];

let alerts = [];
let incidents = [];

function nowIso() { return new Date().toISOString(); }
function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}

function parseBody(req) {
  return new Promise((resolve) => {
    let data = '';
    req.on('data', (chunk) => (data += chunk));
    req.on('end', () => {
      try { resolve(data ? JSON.parse(data) : {}); } catch { resolve({}); }
    });
  });
}

function severityRank(sev) {
  const s = String(sev || '').toLowerCase();
  if (s === 'critical') return 3;
  if (s === 'high') return 2;
  if (s === 'warning') return 1;
  return 0;
}

function computeSummary() {
  return {
    open_alerts: alerts.filter((a) => a.status === 'open').length,
    acked_alerts: alerts.filter((a) => a.status === 'acked').length,
    open_incidents: incidents.filter((i) => i.status === 'open').length,
    resolved_incidents: incidents.filter((i) => i.status === 'resolved').length,
    total_services: services.length,
    services_with_location: services.length,
    location_coverage: 1,
  };
}

function computeTopology(locationCode) {
  const filteredServices = locationCode && locationCode !== 'all'
    ? services.filter((s) => s.location_code === locationCode)
    : services;

  const nodes = filteredServices.map((s) => {
    const openAlerts = alerts.filter((a) => a.service_name === s.name && a.status === 'open').length;
    const openInc = incidents.filter((i) => i.service_name === s.name && i.status !== 'resolved').length;
    let health = 'healthy';
    if (openInc > 0 || openAlerts > 1) health = 'critical';
    else if (openAlerts > 0) health = 'warning';
    return {
      service_id: s.id,
      name: s.name,
      environment: 'prod',
      health,
      meta: `location: ${s.location_code}`,
      open_alerts: openAlerts,
      open_incidents: openInc,
    };
  });

  return {
    generated_at: nowIso(),
    nodes,
    edges: [
      { from_service_id: 1, to_service_id: 2, relation: 'depends_on', criticality: 'high' },
      { from_service_id: 1, to_service_id: 3, relation: 'runtime_call', criticality: 'medium' },
      { from_service_id: 4, to_service_id: 1, relation: 'runtime_call', criticality: 'high' },
    ],
    kpi: {
      affected_services: nodes.filter((n) => n.health !== 'healthy').length,
      critical_edges: 2,
      blast_radius: 'Medium',
    },
  };
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1:8000');
  const p = url.pathname;

  if (req.method === 'GET' && p === '/healthz') return send(res, 200, { status: 'ok', time: nowIso() });
  if (req.method === 'POST' && p === '/auth/login') return send(res, 200, { access_token: 'demo-token', token_type: 'bearer' });

  if (req.method === 'POST' && p === '/demo/reset') {
    alerts = alerts.map((a) => ({ ...a, status: 'acked' }));
    incidents = incidents.map((i) => ({ ...i, status: 'resolved' }));
    return send(res, 200, { ok: true });
  }

  if (req.method === 'POST' && p === '/ingest/zabbix') {
    const body = await parseBody(req);
    const item = {
      id: nextAlertId++,
      source: body.source || 'zabbix',
      severity: body.severity || 'warning',
      title: body.title || 'Incoming alert',
      status: 'open',
      created_at: nowIso(),
      service_name: body.service_name || 'api-gateway',
      location_code: body.location_code || 'hcm-dc1',
    };
    alerts.unshift(item);
    return send(res, 200, { ok: true, event: item });
  }

  if (req.method === 'POST' && p === '/incidents') {
    const body = await parseBody(req);
    const item = {
      id: nextIncidentId++,
      title: body.title || 'Incident',
      severity: body.severity || 'high',
      status: 'open',
      assignee_id: null,
      created_at: nowIso(),
      service_name: 'api-gateway',
      location_code: body.location_code || 'hcm-dc1',
    };
    incidents.unshift(item);
    return send(res, 200, item);
  }

  if (req.method === 'GET' && p === '/summary') return send(res, 200, computeSummary());
  if (req.method === 'GET' && p === '/locations') return send(res, 200, locations);

  if (req.method === 'GET' && p === '/alerts') {
    const location = (url.searchParams.get('location_code') || '').toLowerCase();
    const out = location ? alerts.filter((a) => (a.location_code || '').toLowerCase() === location) : alerts;
    return send(res, 200, out.slice(0, 200));
  }

  if (req.method === 'GET' && p === '/incidents') {
    const location = (url.searchParams.get('location_code') || '').toLowerCase();
    const out = location ? incidents.filter((i) => (i.location_code || '').toLowerCase() === location) : incidents;
    return send(res, 200, out.slice(0, 200));
  }

  if (req.method === 'GET' && p === '/topology') {
    const locationCode = (url.searchParams.get('location_code') || '').toLowerCase() || null;
    return send(res, 200, computeTopology(locationCode));
  }

  send(res, 404, { error: 'not found', path: p });
});

server.listen(8000, '127.0.0.1', () => {
  console.log('Mock API listening on http://127.0.0.1:8000');
});
