import { safeApiGet } from "../lib";
import { mockAlerts } from "../mockData";
import { DataTable, PageHeader, PanelCard, PillTabs, SectionTitle, StatusBadge } from "../components/ui";
import AckButton from "./ack-button";

export default async function AlertsPage({ searchParams }) {
  const statusFilter = searchParams?.status;
  const alertsRaw = await safeApiGet("/alerts", mockAlerts);
  let alerts = Array.isArray(alertsRaw) ? alertsRaw : [];

  if (statusFilter) {
    alerts = alerts.filter((a) => String(a.status).toLowerCase() === String(statusFilter).toLowerCase());
  }

  return (
    <main>
      <PageHeader title="Alerts Inbox" subtitle="Prioritized feed for active operator response">
        <PillTabs
          active={statusFilter || "all"}
          items={[
            { key: "all", label: "All", href: "/alerts" },
            { key: "open", label: "Open", href: "/alerts?status=open" },
            { key: "acked", label: "Acked", href: "/alerts?status=acked" },
          ]}
        />
      </PageHeader>

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
        </DataTable>
      </PanelCard>
    </main>
  );
}
