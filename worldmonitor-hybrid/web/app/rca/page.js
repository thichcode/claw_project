import { PanelCard, StatusBadge } from "../components/ui";

const timeline = [
  ["21:58", "Keycloak realm config changed", "change-event"],
  ["22:00", "Latency p95 crossed 2.0s", "metric-alert"],
  ["22:01", "Redis memory hit 92%", "dependency"],
  ["22:03", "Incident auto-correlated", "system"],
  ["22:05", "On-call ACK and mitigation", "human-action"],
];

export default function RCAPage() {
  return (
    <main>
      <h1 className="wm-page-title">Root Cause Drill-down</h1>
      <p className="wm-subtitle">Correlated timeline and hypotheses.</p>

      <div className="wm-grid-2" style={{ marginBottom: 12 }}>
        <PanelCard title="INC-2026-031 · Login failures & latency spike">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <StatusBadge status="P1 Critical" />
            <StatusBadge status="Impacted users: 8,200" />
            <StatusBadge status="ACKed by IAM on-call" />
          </div>
          <div style={{ color: "var(--muted)" }}>Opened 22:01 · Env: prod · Domain: IAM/Auth</div>
        </PanelCard>

        <PanelCard title="Hypotheses">
          <p><b>H1 (0.92):</b> Keycloak cache saturation from Redis pressure.</p>
          <p><b>H2 (0.61):</b> DB connection bottleneck on primary.</p>
          <p><b>H3 (0.34):</b> External IdP latency.</p>
        </PanelCard>
      </div>

      <PanelCard title="Unified Timeline">
        <table className="wm-table">
          <thead><tr><th>Time</th><th>Event</th><th>Tag</th></tr></thead>
          <tbody>
            {timeline.map(([time, evt, tag]) => (
              <tr key={time + evt}>
                <td>{time}</td>
                <td>{evt}</td>
                <td>{tag}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>
    </main>
  );
}
