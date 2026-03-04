import { safeApiGet } from "../../lib";
import { mockIncidentDetail } from "../../mockData";
import { PanelCard, StatusBadge } from "../../components/ui";
import IncidentActions from "./IncidentActions";

export default async function IncidentDetailPage({ params }) {
  const data = await safeApiGet(`/incidents/${params.id}`, mockIncidentDetail);
  const incident = data?.incident || {};
  const events = Array.isArray(data?.events) ? data.events : [];

  return (
    <main>
      <h1 className="wm-page-title">Incident #{incident.id || "-"}</h1>
      <p className="wm-subtitle">RCA context and response actions.</p>

      <div className="wm-grid-2">
        <PanelCard title={incident.title || "Untitled incident"}>
          <p><b>Status:</b> <StatusBadge status={incident.status} /></p>
          <p><b>Severity:</b> <StatusBadge status={incident.severity} /></p>
          <p><b>Service ID:</b> {incident.service_id || "-"}</p>

          <h3>Timeline</h3>
          <ul>
            {events.map((e) => (
              <li key={e.id} style={{ marginBottom: 8 }}>
                {e.created_at} · <b>{e.event_type}</b> · {JSON.stringify(e.payload)}
              </li>
            ))}
          </ul>
        </PanelCard>

        <PanelCard title="Action Panel">
          <IncidentActions incidentId={incident.id} />
        </PanelCard>
      </div>
    </main>
  );
}
