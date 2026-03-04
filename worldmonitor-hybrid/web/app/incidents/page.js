import { safeApiGet } from "../lib";
import { mockIncidents } from "../mockData";
import { PanelCard, StatusBadge } from "../components/ui";

export default async function IncidentsPage() {
  const incidentsRaw = await safeApiGet("/incidents", mockIncidents);
  const incidents = Array.isArray(incidentsRaw) ? incidentsRaw : [];

  return (
    <main>
      <h1 className="wm-page-title">Incidents</h1>
      <p className="wm-subtitle">Track incident lifecycle and jump into RCA.</p>

      <PanelCard>
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
      </PanelCard>
    </main>
  );
}
