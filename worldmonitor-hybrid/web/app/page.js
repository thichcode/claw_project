import { safeApiGet } from "./lib";
import { mockSummary, executiveHotspots } from "./mockData";
import { DataTable, HotspotTable, MetricTile, PageHeader, PanelCard, SectionTitle, StatusBadge } from "./components/ui";

export default async function DashboardPage() {
  const summaryRaw = await safeApiGet("/summary", mockSummary);
  const summary = { ...mockSummary, ...(summaryRaw || {}) };

  return (
    <main>
      <PageHeader
        title="Global Command Center"
        subtitle="Real-time operational posture"
        right={<span style={{ color: "#7dd3fc", fontSize: 12, fontWeight: 700 }}>● LIVE</span>}
      />

      <div className="wm-grid-3" style={{ marginBottom: 14 }}>
        <MetricTile value={summary.open_alerts} label="Open alerts" tone="critical" />
        <MetricTile value={summary.acked_alerts} label="Acknowledged" tone="info" />
        <MetricTile value={`${summary.open_incidents} / ${summary.resolved_incidents}`} label="Incidents (open/resolved)" tone="warning" />
      </div>

      <PanelCard>
        <SectionTitle title="Hotspots & Signal Quality" meta="last 15m" />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
          <StatusBadge status={`critical ${summary.open_alerts}`} />
          <StatusBadge status={`acked ${summary.acked_alerts}`} />
          <StatusBadge status={`resolved ${summary.resolved_incidents}`} />
        </div>
        <DataTable>
          <HotspotTable rows={executiveHotspots} />
        </DataTable>
      </PanelCard>
    </main>
  );
}
