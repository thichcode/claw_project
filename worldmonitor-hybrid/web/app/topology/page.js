import { DataTable, MetricTile, PageHeader, PanelCard, SectionTitle, StatusBadge } from "../components/ui";
import { safeApiGet } from "../lib";
import { mockTopologySummary } from "../mockData";

const topologyFallback = {
  nodes: [],
  edges: [],
  topology_summary: mockTopologySummary,
  kpi: { affected_services: 0, critical_edges: 0, blast_radius: "Low" },
};

export default async function TopologyPage({ searchParams }) {
  const location = searchParams?.location;
  let degraded = false;
  let locations = [];

  try {
    locations = await safeApiGet("/locations", []);
  } catch {
    degraded = true;
  }
  const path = location ? `/topology?location_code=${encodeURIComponent(location)}` : "/topology";
  let topology = topologyFallback;

  try {
    topology = await safeApiGet(path, topologyFallback);
  } catch {
    degraded = true;
  }

  return (
    <main>
      <PageHeader title="Service Topology" subtitle="Dependency graph and blast-radius analysis" />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <a href="/topology" style={{ opacity: !location ? 1 : 0.75 }}>All locations</a>
        {(locations || []).map((l) => (
          <a key={l.code} href={`/topology?location=${encodeURIComponent(l.code)}`} style={{ opacity: location === l.code ? 1 : 0.75 }}>
            {l.code}
          </a>
        ))}
      </div>

      {degraded ? (
        <PanelCard>
          <div style={{ color: "#fca5a5", fontSize: 13 }}>
            Topology live data is unavailable. Showing fallback content.
          </div>
        </PanelCard>
      ) : null}

      <div className="wm-grid-2">
        <PanelCard>
          <SectionTitle title="Service map" meta={`${(topology.nodes || []).length} nodes`} />
          <DataTable>
            <table className="wm-table">
              <thead><tr><th>Node</th><th>Health</th><th>Details</th></tr></thead>
              <tbody>
                {(topology.nodes || []).map((n) => (
                  <tr key={n.service_id}>
                    <td>{n.name}</td>
                    <td><StatusBadge status={n.health} /></td>
                    <td>{n.meta || `${n.environment || "prod"} · alerts:${n.open_alerts || 0}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataTable>
        </PanelCard>

        <div style={{ display: "grid", gap: 10 }}>
          <MetricTile value={String(topology.kpi?.affected_services ?? 0)} label="Affected services" tone="warning" />
          <MetricTile value={String(topology.kpi?.critical_edges ?? 0)} label="Critical edges" tone="critical" />
          <MetricTile value={topology.kpi?.blast_radius || "Low"} label="Blast radius" tone="info" />
        </div>
      </div>

      <div className="wm-grid-2" style={{ marginTop: 12 }}>
        <PanelCard>
          <SectionTitle title="Dependency Summary" meta={`${topology.topology_summary?.unhealthy_nodes_count || 0} unhealthy nodes`} />
          <div style={{ display: "grid", gap: 8 }}>
            {Object.entries(topology.topology_summary?.relation_counts || {}).map(([relation, count]) => (
              <div key={relation} style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{relation}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </PanelCard>

        <PanelCard>
          <SectionTitle title="Critical Dependency Paths" meta={`${(topology.topology_summary?.critical_paths || []).length} paths`} />
          <div style={{ display: "grid", gap: 8 }}>
            {(topology.topology_summary?.critical_paths || []).map((path, idx) => (
              <div key={`${path.from_service_id}-${path.to_service_id}-${idx}`} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span>{path.layer || "other"} · {path.relation}</span>
                <strong>{path.from_service_id} → {path.to_service_id} · {path.criticality}</strong>
              </div>
            ))}
          </div>
        </PanelCard>
      </div>

      <PanelCard style={{ marginTop: 12 }}>
        <SectionTitle title="Layer Composition" meta={`${Object.keys(topology.topology_summary?.layer_counts || {}).length} layers`} />
        <div style={{ display: "grid", gap: 8 }}>
          {Object.entries(topology.topology_summary?.layer_counts || {}).map(([layer, count]) => (
            <div key={layer} style={{ display: "flex", justifyContent: "space-between" }}>
              <span>{layer}</span>
              <strong>{count}</strong>
            </div>
          ))}
        </div>
      </PanelCard>
    </main>
  );
}
