import { safeApiGet } from "../lib";
import { mockAlerts } from "../mockData";
import { DataTable, PageHeader, PanelCard, PillTabs, SectionTitle, StatusBadge } from "../components/ui";
import AckButton from "./ack-button";

export default async function AlertsPage({ searchParams }) {
  const statusFilter = searchParams?.status;
  const locationFilter = searchParams?.location;

  const alertsRaw = await safeApiGet("/alerts", mockAlerts);
  const locations = await safeApiGet("/locations", []);

  let alerts = Array.isArray(alertsRaw) ? alertsRaw : [];

  if (statusFilter) {
    alerts = alerts.filter((a) => String(a.status).toLowerCase() === String(statusFilter).toLowerCase());
  }
  if (locationFilter) {
    alerts = alerts.filter((a) => String(a.location_code || "").toLowerCase() === String(locationFilter).toLowerCase());
  }

  const base = statusFilter ? `/alerts?status=${encodeURIComponent(statusFilter)}` : "/alerts";

  return (
    <main>
      <PageHeader title="Alerts Inbox" subtitle="Prioritized feed for active operator response">
        <PillTabs
          active={statusFilter || "all"}
          items={[
            { key: "all", label: "All", href: locationFilter ? `/alerts?location=${encodeURIComponent(locationFilter)}` : "/alerts" },
            { key: "open", label: "Open", href: locationFilter ? `/alerts?status=open&location=${encodeURIComponent(locationFilter)}` : "/alerts?status=open" },
            { key: "acked", label: "Acked", href: locationFilter ? `/alerts?status=acked&location=${encodeURIComponent(locationFilter)}` : "/alerts?status=acked" },
          ]}
        />
      </PageHeader>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <a href={statusFilter ? `/alerts?status=${encodeURIComponent(statusFilter)}` : "/alerts"} style={{ opacity: !locationFilter ? 1 : 0.75 }}>All locations</a>
        {(locations || []).map((l) => (
          <a
            key={l.code}
            href={`${base}${base.includes("?") ? "&" : "?"}location=${encodeURIComponent(l.code)}`}
            style={{ opacity: locationFilter === l.code ? 1 : 0.75 }}
          >
            {l.code}
          </a>
        ))}
      </div>

      <PanelCard>
        <SectionTitle title="Live queue" meta={`${alerts.length} alerts`} />
        <DataTable compact>
          <table className="wm-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Source</th>
                <th>Severity</th>
                <th>Title</th>
                <th>Status</th>
                <th>Service</th>
                <th>Location</th>
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
                  <td>{a.location_code || "-"}</td>
                  <td><AckButton alertId={a.id} disabled={a.status !== "open"} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataTable>
      </PanelCard>
    </main>
  );
}
