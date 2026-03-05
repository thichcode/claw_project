import { DataTable, MetricTile, PageHeader, PanelCard, SectionTitle, StatusBadge } from "../components/ui";
import { safeApiGet } from "../lib";

const topologyFallback = {
  nodes: [],
  edges: [],
  kpi: { affected_services: 0, critical_edges: 0, blast_radius: "Low" },
};

export default async function TopologyPage() {
  const topology = await safeApiGet("/topology", topologyFallback);

  return (
    <main>
      <PageHeader title="Service Topology" subtitle="Dependency graph and blast-radius analysis" />

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
    </main>
  );
}
