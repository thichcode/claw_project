export const mockSummary = {
  open_alerts: 6,
  acked_alerts: 4,
  open_incidents: 3,
  resolved_incidents: 7,
};

export const mockAlerts = [
  { id: 901, source: "zabbix", severity: "critical", title: "Keycloak latency p95 > 2s", status: "open", service_name: "keycloak", location_code: "hcm-dc1" },
  { id: 902, source: "alertmanager", severity: "warning", title: "Kafka backlog increased", status: "open", service_name: "data-pipeline", location_code: "sgp-az1" },
  { id: 903, source: "uptimerobot", severity: "high", title: "API gateway 5xx above SLO", status: "acked", service_name: "api-gateway", location_code: "hcm-dc1" },
];

export const mockIncidents = [
  { id: 301, title: "Login failures & latency spike", severity: "critical", status: "open", assignee_id: 2, service_name: "keycloak", location_code: "hcm-dc1", created_at: "2026-03-04T15:05:00Z" },
  { id: 302, title: "Queue lag on data platform", severity: "high", status: "acked", assignee_id: 1, service_name: "data-pipeline", location_code: "sgp-az1", created_at: "2026-03-04T14:44:00Z" },
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

export const mockInventoryOverview = {
  summary: {
    total_systems: 10,
    healthy_systems: 6,
    degraded_systems: 2,
    critical_systems: 2,
    mapped_systems: 3,
    unmapped_systems: 7,
    owners: 5,
    locations: 3,
    coverage_ratio: 0.3,
  },
  systems: [
    { service_id: 1, name: "api-gateway", owner: "platform", location_code: "hcm-dc1", health: "warning", open_alerts: 1, open_incidents: 0, coverage: "mapped" },
    { service_id: 2, name: "keycloak", owner: "iam", location_code: "hcm-dc1", health: "critical", open_alerts: 1, open_incidents: 1, coverage: "mapped" },
    { service_id: 3, name: "data-pipeline", owner: "data", location_code: "sgp-az1", health: "warning", open_alerts: 1, open_incidents: 1, coverage: "mapped" },
  ],
  owner_matrix: [
    { owner: "platform", total_systems: 3, healthy: 2, degraded: 1, critical: 0, mapped: 1, unmapped: 2 },
    { owner: "iam", total_systems: 1, healthy: 0, degraded: 0, critical: 1, mapped: 1, unmapped: 0 },
  ],
  risk_summary: {
    unmapped_critical: 1,
    unmapped_degraded: 2,
    ownerless_systems: 1,
    priority_actions: ["Map 1 critical systems to locations", "Assign owners to 1 systems"],
  },
  health_matrix: [
    { environment: "prod", location_code: "hcm-dc1", total_systems: 4, healthy: 2, degraded: 1, critical: 1 },
    { environment: "prod", location_code: "unmapped", total_systems: 6, healthy: 4, degraded: 1, critical: 1 },
  ],
};

export const mockTopologySummary = {
  relation_counts: { runtime_call: 3, data_store: 2, cache_layer: 1 },
  layer_counts: { application: 3, data: 2, cache: 1, network: 1 },
  critical_paths: [
    { from_service_id: 1, to_service_id: 2, relation: "runtime_call", criticality: "critical", layer: "application" },
    { from_service_id: 1, to_service_id: 3, relation: "data_store", criticality: "high", layer: "data" },
  ],
  unhealthy_nodes_count: 3,
};
