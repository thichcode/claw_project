import { safeApiGet } from "../lib";
import { mockIncidents } from "../mockData";
import { DataTable, MetricTile, PageHeader, PanelCard, SectionTitle, StatusBadge } from "../components/ui";

export default async function IncidentsPage() {
  const incidentsRaw = await safeApiGet("/incidents", mockIncidents);
  const incidents = Array.isArray(incidentsRaw) ? incidentsRaw : [];
  const openCount = incidents.filter((i) => i.status !== "resolved").length;
  const criticalCount = incidents.filter((i) => String(i.severity).toLowerCase() === "critical").length;

  return (
    <main>
      <PageHeader title="Incidents" subtitle="Lifecycle tracking and escalation context" />

      <div className="wm-grid-3" style={{ marginBottom: 14 }}>
        <MetricTile value={incidents.length} label="Total incidents" tone="info" />
        <MetricTile value={openCount} label="Open incidents" tone="warning" />
        <MetricTile value={criticalCount} label="Critical incidents" tone="critical" />
      </div>

      <PanelCard>
        <SectionTitle title="Incident queue" />
        <DataTable>
          <table className="wm-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Service</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((i) => (
                <tr key={i.id}>
                  <td><a href={`/incidents/${i.id}`}>#{i.id}</a></td>
                  <td>{i.title}</td>
                  <td><StatusBadge status={i.severity} /></td>
                  <td><StatusBadge status={i.status} /></td>
                  <td>{i.service_name || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataTable>
      </PanelCard>
    </main>
  );
}
