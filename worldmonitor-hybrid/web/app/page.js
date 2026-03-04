import { safeApiGet } from "./lib";
import { mockSummary, executiveHotspots } from "./mockData";
import { HotspotTable, KPI, PanelCard, StatusBadge } from "./components/ui";

export default async function DashboardPage() {
  const summaryRaw = await safeApiGet("/summary", mockSummary);
  const summary = { ...mockSummary, ...(summaryRaw || {}) };

  return (
    <main>
      <h1 className="wm-page-title">WorldMonitor Dashboard</h1>
      <p className="wm-subtitle">NOC overview with API-backed data and graceful fallback.</p>

      <div className="wm-grid-3" style={{ marginBottom: 12 }}>
        <KPI value={summary.open_alerts} label="Open alerts" />
        <KPI value={summary.acked_alerts} label="Acked alerts" />
        <KPI value={summary.open_incidents + " / " + summary.resolved_incidents} label="Open / resolved incidents" />
      </div>

      <PanelCard title="Global status">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
          <StatusBadge status={`critical ${summary.open_alerts}`} />
          <StatusBadge status={`acked ${summary.acked_alerts}`} />
          <StatusBadge status={`resolved ${summary.resolved_incidents}`} />
        </div>
        <HotspotTable rows={executiveHotspots} />
      </PanelCard>
    </main>
  );
}
