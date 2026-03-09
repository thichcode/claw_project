import { safeApiGet } from "../lib";
import { executiveHotspots, mockSummary } from "../mockData";
import { HotspotTable, KPI, PanelCard, StatusBadge } from "../components/ui";

export default async function ExecutivePage() {
  let summary = mockSummary;
  let degraded = false;

  try {
    summary = await safeApiGet("/summary", mockSummary);
  } catch {
    degraded = true;
  }

  return (
    <main>
      <h1 className="wm-page-title">Executive Overview</h1>
      <p className="wm-subtitle">Snapshot for fast operational decisions.</p>

      {degraded ? (
        <PanelCard>
          <div style={{ color: "#fca5a5", fontSize: 13 }}>
            Executive data is temporarily unavailable. Showing limited fallback values.
          </div>
        </PanelCard>
      ) : null}

      <PanelCard>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <StatusBadge status={`Critical: ${summary.open_alerts}`} />
            <StatusBadge status={`Acked: ${summary.acked_alerts}`} />
            <StatusBadge status={`Resolved: ${summary.resolved_incidents}`} />
          </div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>8,200 users impacted</div>
        </div>
      </PanelCard>

      <div className="wm-grid-3" style={{ margin: "12px 0" }}>
        <KPI value="2.1s" label="Auth p95 latency" />
        <KPI value="3.8%" label="Error rate" />
        <KPI value="35m" label="ETA stabilization" />
      </div>

      <PanelCard title="Hotspots">
        <HotspotTable rows={executiveHotspots} />
      </PanelCard>
    </main>
  );
}
