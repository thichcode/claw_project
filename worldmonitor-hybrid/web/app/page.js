import { safeApiGet } from "./lib";
import { mockSummary } from "./mockData";
import { StatusBadge } from "./components/ui";
import AutoRefresh from "./components/auto-refresh";
import SimulateControls from "./components/simulate-controls";
import WidgetControlsBar from "./components/widget-controls-bar";
import WorldMap from "./components/world-map";
import FloatingWidgets from "./components/floating-widgets";
import styles from "./home.module.css";

function hotspotScore(n) {
  const h = String(n.health || "").toLowerCase();
  const sev = h === "critical" ? 5 : h === "warning" ? 3 : 1;
  return sev * 100 + (n.open_incidents || 0) * 30 + (n.open_alerts || 0) * 8;
}

export default async function DashboardPage({ searchParams }) {
  const location = searchParams?.location || "all";
  const warMode = String(searchParams?.war || "0") === "1";
  const range = String(searchParams?.range || "1h");
  const summaryRaw = await safeApiGet("/summary", mockSummary);
  const summary = { ...mockSummary, ...(summaryRaw || {}) };
  const locations = await safeApiGet("/locations", []);

  const topologyPath = location === "all" ? "/topology" : `/topology?location_code=${encodeURIComponent(location)}`;
  const topology = await safeApiGet(topologyPath, { nodes: [], edges: [] });
  const topologyGlobal = await safeApiGet("/topology", { nodes: [], edges: [] });

  const locCodes = (locations || []).map((l) => l.code);
  const topologyByLocation = await Promise.all(
    locCodes.map(async (code) => ({
      code,
      data: await safeApiGet(`/topology?location_code=${encodeURIComponent(code)}`, { nodes: [] }),
    }))
  );

  const hotspotRows = [...(topology.nodes || [])].sort((a, b) => hotspotScore(b) - hotspotScore(a)).slice(0, 8);
  const rightIncidents = (await safeApiGet("/incidents", [])).slice(0, 8);
  const leftAlerts = (await safeApiGet("/alerts", [])).slice(0, 12);

  const rangeFactor = range === "15m" ? 0.35 : range === "24h" ? 2.4 : 1;
  const estImpactedUsers = Math.round((summary.open_alerts * 230 + summary.open_incidents * 900) * rangeFactor);
  const estRevenueRisk = Math.round((summary.open_incidents * 1200 + summary.open_alerts * 180) * rangeFactor);
  const slaRisk = Math.min(99, Math.round((summary.open_incidents * 8 + summary.open_alerts * 2.3) * (warMode ? 1.2 : 1)));

  return (
    <main className={styles.shell}>
      <div className={styles.topbar}>
        <div className={styles.brand}>
          <span className={styles.brandDot} />
          <div>
            <div className={styles.title}>HORUS-STYLE GLOBAL MONITOR</div>
            <div className={styles.sub}>location → service health intelligence</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <AutoRefresh seconds={8} />
          <StatusBadge status={`critical ${summary.open_alerts || 0}`} />
          <StatusBadge status={`open incidents ${summary.open_incidents || 0}`} />
        </div>
      </div>

      <div style={{ border: "1px dashed #7c2d12", background: "rgba(127,29,29,.22)", color: "#fecaca", borderRadius: 10, padding: "6px 10px", fontSize: 12 }}>
        ⚠ SIMULATED / ESTIMATED DATA (demo mode) — không dùng để ra quyết định production.
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <a href={`/?range=${encodeURIComponent(range)}&war=${warMode ? "1" : "0"}`} style={{ opacity: location === "all" ? 1 : 0.75 }}>Global</a>
          {(locations || []).map((l) => (
            <a key={l.code} href={`/?location=${encodeURIComponent(l.code)}&range=${encodeURIComponent(range)}&war=${warMode ? "1" : "0"}`} style={{ opacity: location === l.code ? 1 : 0.75 }}>
              {l.code}
            </a>
          ))}
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", border: "1px solid #243049", borderRadius: 10, padding: "8px 10px", background: "rgba(10,16,30,.75)" }}>
          <strong style={{ fontSize: 12, color: "#9fb3cd" }}>Quick Mode</strong>
          <a href={`/?location=${encodeURIComponent(location)}&range=${encodeURIComponent(range)}&war=${warMode ? "0" : "1"}`}>
            {warMode ? "Disable War Mode" : "Enable War Mode"}
          </a>
          <span style={{ color: "#64748b" }}>·</span>
          <span style={{ fontSize: 12, color: "#9fb3cd" }}>Time Rewind:</span>
          {[
            { k: "15m", t: "15m" },
            { k: "1h", t: "1h" },
            { k: "24h", t: "24h" },
          ].map((r) => (
            <a key={r.k} href={`/?location=${encodeURIComponent(location)}&range=${r.k}&war=${warMode ? "1" : "0"}`} style={{ opacity: range === r.k ? 1 : 0.7 }}>
              {r.t}
            </a>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(160px,1fr))", gap: 8 }}>
          <div style={{ border: "1px solid #243049", borderRadius: 10, padding: 8, background: "rgba(10,16,30,.75)" }}>
            <div style={{ fontSize: 11, color: "#8ea3be" }}>Estimated impacted users</div>
            <div style={{ fontWeight: 800, color: "#dbeafe" }}>{estImpactedUsers.toLocaleString()}</div>
          </div>
          <div style={{ border: "1px solid #243049", borderRadius: 10, padding: 8, background: "rgba(10,16,30,.75)" }}>
            <div style={{ fontSize: 11, color: "#8ea3be" }}>Revenue risk (USD/hr)</div>
            <div style={{ fontWeight: 800, color: "#fecaca" }}>${estRevenueRisk.toLocaleString()}</div>
          </div>
          <div style={{ border: "1px solid #243049", borderRadius: 10, padding: 8, background: "rgba(10,16,30,.75)" }}>
            <div style={{ fontSize: 11, color: "#8ea3be" }}>SLA breach risk</div>
            <div style={{ fontWeight: 800, color: slaRisk > 50 ? "#fca5a5" : "#fde68a" }}>{slaRisk}%</div>
          </div>
        </div>

        <WidgetControlsBar />
        <SimulateControls />
      </div>

      <div className={styles.content}>
        <div className={styles.fullMapStage}>
          <WorldMap topologyByLocation={topologyByLocation} topologyGlobal={topologyGlobal} warMode={warMode} timeRange={range} />
          <FloatingWidgets
            leftAlerts={leftAlerts}
            rightIncidents={rightIncidents}
            hotspotRows={hotspotRows}
          />
        </div>
      </div>
    </main>
  );
}
