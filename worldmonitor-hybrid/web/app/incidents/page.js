import { safeApiGet } from "../lib";
import { mockIncidents } from "../mockData";
import { DataTable, MetricTile, PageHeader, PanelCard, SectionTitle, StatusBadge } from "../components/ui";

export default async function IncidentsPage({ searchParams }) {
  const locationFilter = searchParams?.location;
  const incidentsRaw = await safeApiGet("/incidents", mockIncidents);
  const locations = await safeApiGet("/locations", []);

  let incidents = Array.isArray(incidentsRaw) ? incidentsRaw : [];
  if (locationFilter) {
    incidents = incidents.filter((i) => String(i.location_code || "").toLowerCase() === String(locationFilter).toLowerCase());
  }

  const openCount = incidents.filter((i) => i.status !== "resolved").length;
  const criticalCount = incidents.filter((i) => String(i.severity).toLowerCase() === "critical").length;

  return (
    <main>
      <PageHeader title="Incidents" subtitle="Lifecycle tracking and escalation context" />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <a href="/incidents" style={{ opacity: !locationFilter ? 1 : 0.75 }}>All locations</a>
        {(locations || []).map((l) => (
          <a key={l.code} href={`/incidents?location=${encodeURIComponent(l.code)}`} style={{ opacity: locationFilter === l.code ? 1 : 0.75 }}>
            {l.code}
          </a>
        ))}
      </div>

      <div className="wm-grid-3" style={{ marginBottom: 14 }}>
        <MetricTile value={incidents.length} label="Total incidents" tone="info" />
        <MetricTile value={openCount} label="Open incidents" tone="warning" />
        <MetricTile value={criticalCount} label="Critical incidents" tone="critical" />
      </div>

      <PanelCard>
        <SectionTitle title="Incident queue" meta={locationFilter || "all locations"} />
        <DataTable>
          <table className="wm-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Service</th>
                <th>Location</th>
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
                  <td>{i.location_code || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataTable>
      </PanelCard>
    </main>
  );
}
