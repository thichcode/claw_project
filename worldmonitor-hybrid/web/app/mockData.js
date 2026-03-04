export const mockSummary = {
  open_alerts: 6,
  acked_alerts: 4,
  open_incidents: 3,
  resolved_incidents: 7,
};

export const mockAlerts = [
  { id: 901, source: "zabbix", severity: "critical", title: "Keycloak latency p95 > 2s", status: "open", service_name: "keycloak" },
  { id: 902, source: "alertmanager", severity: "warning", title: "Kafka backlog increased", status: "open", service_name: "data-pipeline" },
  { id: 903, source: "uptimerobot", severity: "high", title: "API gateway 5xx above SLO", status: "acked", service_name: "api-gateway" },
];

export const mockIncidents = [
  { id: 301, title: "Login failures & latency spike", severity: "critical", status: "open", assignee_id: 2, service_name: "keycloak", created_at: "2026-03-04T15:05:00Z" },
  { id: 302, title: "Queue lag on data platform", severity: "high", status: "acked", assignee_id: 1, service_name: "data-pipeline", created_at: "2026-03-04T14:44:00Z" },
];

export const mockIncidentDetail = {
  incident: { id: 301, title: "Login failures & latency spike", severity: "critical", status: "open", service_id: 3, assignee_id: 2, created_at: "2026-03-04T15:05:00Z" },
  events: [
    { id: 1, event_type: "created", payload: { message: "incident created" }, created_at: "2026-03-04T15:05:10Z" },
    { id: 2, event_type: "commented", payload: { comment: "Investigating cache saturation" }, created_at: "2026-03-04T15:09:40Z" },
  ],
};

export const executiveHotspots = [
  { issue: "Keycloak login latency p95 2.1s", trend: "↑ +35%", owner: "IAM Team" },
  { issue: "Redis cluster memory 92%", trend: "↑ +6%", owner: "Platform Team" },
  { issue: "Kafka backlog 120k", trend: "↑ +22%", owner: "Data Team" },
];
