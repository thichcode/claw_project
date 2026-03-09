import { DataTable, PageHeader, PanelCard, SectionTitle, StatusBadge } from "../components/ui";
import { safeApiGet } from "../lib";

const rcaFallback = {
  incident: { title: "No incident", status: "unknown", severity: "info" },
  hypotheses: [],
  timeline: [],
  impacted_services: [],
  confidence: 0,
  rca_summary: {
    likely_root_cause: "Insufficient evidence",
    evidence_count: 0,
    timeline_events: 0,
    impacted_services_count: 0,
    impacted_services_preview: [],
    incident_story: "No RCA narrative available.",
  },
  evidence_sections: {
    timeline_signals: [],
    dependency_impacts: [],
    ranked_hypotheses: [],
    change_events: [],
  },
};

export default async function RCAPage({ searchParams }) {
  let incidents = [];
  let degraded = false;

  try {
    incidents = await safeApiGet("/incidents", []);
  } catch {
    degraded = true;
  }

  const selectedId = searchParams?.incidentId || incidents?.[0]?.id;
  let rca = rcaFallback;

  if (selectedId) {
    try {
      rca = await safeApiGet(`/incidents/${selectedId}/rca`, rcaFallback);
    } catch {
      degraded = true;
    }
  }

  return (
    <main>
      <PageHeader title="RCA Workspace" subtitle="Correlated evidence and hypothesis ranking" />

      {degraded ? (
        <PanelCard>
          <div style={{ color: "#fca5a5", fontSize: 13 }}>
            RCA live data is unavailable right now. Displaying fallback content.
          </div>
        </PanelCard>
      ) : null}

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
          <div style={{ marginTop: 10, color: "#cbd5e1", fontSize: 13 }}>
            {rca.rca_summary?.incident_story || "No RCA story available."}
          </div>
        </PanelCard>

        <PanelCard>
          <SectionTitle title="Hypotheses" meta={`confidence ${(rca.confidence || 0).toFixed(2)}`} />
          {(rca.hypotheses || []).length === 0 && <p>No hypotheses yet.</p>}
          {(rca.hypotheses || []).map((h) => (
            <p key={h.id}><b>H{h.rank} ({Number(h.confidence).toFixed(2)}):</b> {h.hypothesis}</p>
          ))}
          <div style={{ marginTop: 10, color: "#cbd5e1", fontSize: 13 }}>
            Likely root cause: <b>{rca.rca_summary?.likely_root_cause || "Unknown"}</b>
          </div>
          <div style={{ color: "#94a3b8", fontSize: 12, marginTop: 6 }}>
            Evidence {rca.rca_summary?.evidence_count || 0} · Impacted services {rca.rca_summary?.impacted_services_count || 0}
          </div>
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

      <div className="wm-grid-2" style={{ marginTop: 12 }}>
        <PanelCard>
          <SectionTitle title="Evidence Signals" meta={`${(rca.evidence_sections?.timeline_signals || []).length} timeline items`} />
          <div style={{ display: "grid", gap: 8 }}>
            {(rca.evidence_sections?.timeline_signals || []).map((item, idx) => (
              <div key={`${item.ts}-${idx}`} style={{ display: "grid", gap: 2 }}>
                <strong>{item.event_type}</strong>
                <span>{item.title}</span>
                <span style={{ color: "#94a3b8", fontSize: 12 }}>{item.ts}</span>
              </div>
            ))}
          </div>
        </PanelCard>

        <PanelCard>
          <SectionTitle title="Dependency Impact Chain" meta={`${(rca.evidence_sections?.dependency_impacts || []).length} services`} />
          <div style={{ display: "grid", gap: 8 }}>
            {(rca.evidence_sections?.dependency_impacts || []).map((item, idx) => (
              <div key={`${item.service_name}-${idx}`} style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{item.service_name}</span>
                <strong>{item.criticality || "medium"}</strong>
              </div>
            ))}
          </div>
        </PanelCard>
      </div>

      <PanelCard style={{ marginTop: 12 }}>
        <SectionTitle title="Deploy / Change Evidence" meta={`${(rca.evidence_sections?.change_events || []).length} changes`} />
        <div style={{ display: "grid", gap: 8 }}>
          {(rca.evidence_sections?.change_events || []).length === 0 ? <p>No deployment or config change evidence.</p> : null}
          {(rca.evidence_sections?.change_events || []).map((item, idx) => (
            <div key={`${item.ts}-${idx}`} style={{ display: "grid", gap: 2 }}>
              <strong>{item.event_type}</strong>
              <span>{item.title}</span>
              <span style={{ color: "#94a3b8", fontSize: 12 }}>{item.source || "unknown source"} · {item.ts}</span>
            </div>
          ))}
        </div>
      </PanelCard>
    </main>
  );
}
