import { DataTable, PageHeader, PanelCard, SectionTitle, StatusBadge } from "../components/ui";
import { safeApiGet } from "../lib";

const rcaFallback = {
  incident: { title: "No incident", status: "unknown", severity: "info" },
  hypotheses: [],
  timeline: [],
  impacted_services: [],
  confidence: 0,
};

export default async function RCAPage({ searchParams }) {
  const incidents = await safeApiGet("/incidents", []);
  const selectedId = searchParams?.incidentId || incidents?.[0]?.id;
  const rca = selectedId
    ? await safeApiGet(`/incidents/${selectedId}/rca`, rcaFallback)
    : rcaFallback;

  return (
    <main>
      <PageHeader title="RCA Workspace" subtitle="Correlated evidence and hypothesis ranking" />

      <div className="wm-grid-2" style={{ marginBottom: 12 }}>
        <PanelCard title={`INC-${rca.incident?.id || "N/A"} · ${rca.incident?.title || "No incident"}`}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <StatusBadge status={rca.incident?.severity || "info"} />
            <StatusBadge status={`Status: ${rca.incident?.status || "unknown"}`} />
            <StatusBadge status={`Confidence: ${(rca.confidence || 0).toFixed(2)}`} />
          </div>
          <div style={{ color: "var(--muted)" }}>
            Service: {rca.incident?.service_name || "unknown"} · Opened {rca.incident?.created_at || "-"}
          </div>
        </PanelCard>

        <PanelCard>
          <SectionTitle title="Hypotheses" meta={`confidence ${(rca.confidence || 0).toFixed(2)}`} />
          {(rca.hypotheses || []).length === 0 && <p>No hypotheses yet.</p>}
          {(rca.hypotheses || []).map((h) => (
            <p key={h.id}><b>H{h.rank} ({Number(h.confidence).toFixed(2)}):</b> {h.hypothesis}</p>
          ))}
        </PanelCard>
      </div>

      <PanelCard>
        <SectionTitle title="Unified Timeline" meta={`${(rca.timeline || []).length} events`} />
        <DataTable>
          <table className="wm-table">
            <thead><tr><th>Time</th><th>Event</th><th>Tag</th></tr></thead>
            <tbody>
              {(rca.timeline || []).map((evt, idx) => (
                <tr key={`${evt.ts}-${idx}`}>
                  <td>{evt.ts}</td>
                  <td>{evt.title}</td>
                  <td>{evt.event_type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataTable>
      </PanelCard>
    </main>
  );
}
