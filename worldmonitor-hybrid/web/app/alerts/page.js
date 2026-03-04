import { safeApiGet } from "../lib";
import { mockAlerts } from "../mockData";
import { PanelCard, StatusBadge } from "../components/ui";
import AckButton from "./ack-button";

export default async function AlertsPage() {
  const alertsRaw = await safeApiGet("/alerts", mockAlerts);
  const alerts = Array.isArray(alertsRaw) ? alertsRaw : [];

  return (
    <main>
      <h1 className="wm-page-title">Alerts Inbox</h1>
      <p className="wm-subtitle">Live alerts feed (fallback to demo data if API unreachable).</p>

      <PanelCard>
        <table className="wm-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>Severity</th>
              <th>Title</th>
              <th>Status</th>
              <th>Service</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id}>
                <td>{a.id}</td>
                <td>{a.source || "-"}</td>
                <td><StatusBadge status={a.severity} /></td>
                <td>{a.title || "-"}</td>
                <td><StatusBadge status={a.status} /></td>
                <td>{a.service_name || "-"}</td>
                <td><AckButton alertId={a.id} disabled={a.status !== "open"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>
    </main>
  );
}
