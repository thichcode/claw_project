import { PanelCard, StatusBadge, KPI } from "../components/ui";

const nodes = [
  { name: "Web App A", meta: "prod · Azure", status: "healthy" },
  { name: "Web App B", meta: "prod · on-prem", status: "warning" },
  { name: "Keycloak", meta: "Auth latency p95 2.1s", status: "critical" },
  { name: "API Gateway", meta: "5xx 2.4%", status: "warning" },
  { name: "Redis", meta: "Mem 92%", status: "critical" },
  { name: "Kafka", meta: "Backlog 120k", status: "warning" },
];

export default function TopologyPage() {
  return (
    <main>
      <h1 className="wm-page-title">System Topology</h1>
      <p className="wm-subtitle">Dependency view and likely choke points.</p>

      <div className="wm-grid-2">
        <PanelCard title="Service map">
          <table className="wm-table">
            <thead><tr><th>Node</th><th>Health</th><th>Details</th></tr></thead>
            <tbody>
              {nodes.map((n) => (
                <tr key={n.name}>
                  <td>{n.name}</td>
                  <td><StatusBadge status={n.status} /></td>
                  <td>{n.meta}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PanelCard>

        <div style={{ display: "grid", gap: 10 }}>
          <KPI value="17" label="Affected services" />
          <KPI value="3" label="Critical edges" />
          <KPI value="High" label="Blast radius" />
        </div>
      </div>
    </main>
  );
}
