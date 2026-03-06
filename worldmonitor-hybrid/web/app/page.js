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
  const openIncidents = toSafeNumber(n?.open_incidents);
  const openAlerts = toSafeNumber(n?.open_alerts);
  return sev * 100 + openIncidents * 30 + openAlerts * 8;
}

function ensureArray(value) {
  return Array.isArray(value) ? value : [];
}

function toSafeNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export default async function DashboardPage({ searchParams }) {
  const location = searchParams?.location || "all";
  const warMode = String(searchParams?.war || "0") === "1";
  const range = String(searchParams?.range || "1h");
  const summaryRaw = await safeApiGet("/summary", mockSummary);
  const summary = {
    ...mockSummary,
    ...(summaryRaw || {}),
    open_alerts: toSafeNumber(summaryRaw?.open_alerts ?? mockSummary.open_alerts),
    open_incidents: toSafeNumber(summaryRaw?.open_incidents ?? mockSummary.open_incidents),
  };
  const locations = await safeApiGet("/locations", []);
  const normalizedLocations = Array.from(
    new Map(
      (locations || [])
        .map((item) => {
          const code = String(item?.code || "").trim();
          return code ? [code, { ...item, code }] : null;
        })
        .filter(Boolean)
    ).values()
  );

  const topologyPath = location === "all" ? "/topology" : `/topology?location_code=${encodeURIComponent(location)}`;
  const topologyPromise = safeApiGet(topologyPath, { nodes: [], edges: [] });
  const topologyGlobalPromise =
    location === "all" ? topologyPromise : safeApiGet("/topology", { nodes: [], edges: [] });

  const locCodes = Array.from(
    new Set([
      ...normalizedLocations.map((l) => l.code),
      ...(location !== "all" ? [location] : []),
    ])
  );
  const topologyByCodePromise = new Map();
  if (location !== "all") topologyByCodePromise.set(location, topologyPromise);

  const topologyByLocationPromise = Promise.all(
    locCodes.map(async (code) => {
      if (!topologyByCodePromise.has(code)) {
        topologyByCodePromise.set(
          code,
          safeApiGet(`/topology?location_code=${encodeURIComponent(code)}`, { nodes: [] })
        );
      }
      return {
        code,
        data: await topologyByCodePromise.get(code),
      };
    })
  );

  const incidentsPath =
    location === "all" ? "/incidents" : `/incidents?location_code=${encodeURIComponent(location)}`;
  const alertsPath =
    location === "all" ? "/alerts" : `/alerts?location_code=${encodeURIComponent(location)}`;

  const [topology, topologyGlobal, topologyByLocation, incidentsRaw, alertsRaw] = await Promise.all([
    topologyPromise,
    topologyGlobalPromise,
    topologyByLocationPromise,
    safeApiGet(incidentsPath, []),
    safeApiGet(alertsPath, []),
  ]);

  const incidents = ensureArray(incidentsRaw);
  const alerts = ensureArray(alertsRaw);
  const hotspotRows = ensureArray(topology?.nodes).sort((a, b) => hotspotScore(b) - hotspotScore(a)).slice(0, 8);
  const rightIncidents = incidents.slice(0, 8);
  const leftAlerts = alerts.slice(0, 12);

  const rangeFactor = range === "15m" ? 0.35 : range === "24h" ? 2.4 : 1;
  const estImpactedUsers = Math.round((summary.open_alerts * 230 + summary.open_incidents * 900) * rangeFactor);
  const estRevenueRisk = Math.round((summary.open_incidents * 1200 + summary.open_alerts * 180) * rangeFactor);
  const slaRisk = Math.min(99, Math.round((summary.open_incidents * 8 + summary.open_alerts * 2.3) * (warMode ? 1.2 : 1)));
  const activeRegions = topologyByLocation.filter((item) =>
    ensureArray(item.data?.nodes).some(
      (n) => toSafeNumber(n?.open_alerts) > 0 || toSafeNumber(n?.open_incidents) > 0
    )
  ).length;

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

      <details className={styles.noticePanel} open>
        <summary className={styles.noticeSummary}>
          <span>Demo data notice</span>
          <span className={styles.noticePill}>Simulated</span>
        </summary>
        <div className={styles.noticeBody}>
          ⚠ SIMULATED / ESTIMATED DATA (demo mode) — không dùng để ra quyết định production.
        </div>
      </details>

      <div className={styles.controlStack}>
        <div className={styles.locationLinks}>
          <a
            href={`/?range=${encodeURIComponent(range)}&war=${warMode ? "1" : "0"}`}
            className={`${styles.locationLink} ${location === "all" ? styles.locationLinkActive : styles.locationLinkInactive}`}
          >
            Global
          </a>
          {normalizedLocations.map((l) => (
            <a
              key={l.code}
              href={`/?location=${encodeURIComponent(l.code)}&range=${encodeURIComponent(range)}&war=${warMode ? "1" : "0"}`}
              className={`${styles.locationLink} ${location === l.code ? styles.locationLinkActive : styles.locationLinkInactive}`}
            >
              {l.code}
            </a>
          ))}
        </div>

        <div className={styles.quickBar}>
          <strong className={styles.quickLabel}>Quick Mode</strong>
          <a
            className={`${styles.quickLink} ${warMode ? styles.quickLinkActive : ""}`}
            href={`/?location=${encodeURIComponent(location)}&range=${encodeURIComponent(range)}&war=${warMode ? "0" : "1"}`}
          >
            {warMode ? "Disable War Mode" : "Enable War Mode"}
          </a>
          <span className={styles.quickSep}>·</span>
          <span className={styles.quickLabel}>Time Rewind:</span>
          {[
            { k: "15m", t: "15m" },
            { k: "1h", t: "1h" },
            { k: "24h", t: "24h" },
          ].map((r) => (
            <a
              key={r.k}
              className={`${styles.quickLink} ${range === r.k ? styles.quickLinkActive : ""}`}
              href={`/?location=${encodeURIComponent(location)}&range=${r.k}&war=${warMode ? "1" : "0"}`}
            >
              {r.t}
            </a>
          ))}
        </div>

        <div className={styles.metricGrid}>
          <div className={styles.metricCard}>
            <div className={styles.metricLabel}>Estimated impacted users</div>
            <div className={styles.metricValue} style={{ color: "#dbeafe" }}>{estImpactedUsers.toLocaleString()}</div>
          </div>
          <div className={styles.metricCard}>
            <div className={styles.metricLabel}>Revenue risk (USD/hr)</div>
            <div className={styles.metricValue} style={{ color: "#fecaca" }}>${estRevenueRisk.toLocaleString()}</div>
          </div>
          <div className={styles.metricCard}>
            <div className={styles.metricLabel}>SLA breach risk</div>
            <div className={styles.metricValue} style={{ color: slaRisk > 50 ? "#fca5a5" : "#fde68a" }}>{slaRisk}%</div>
          </div>
          <div className={styles.metricCard}>
            <div className={styles.metricLabel}>Active regions</div>
            <div className={styles.metricValue} style={{ color: activeRegions > 0 ? "#93c5fd" : "#a7f3d0" }}>{activeRegions}</div>
          </div>
        </div>

        <details className={styles.foldPanel} open>
          <summary className={styles.foldSummary}>
            <span>Operational Notes</span>
            <span className={styles.foldPill}>Auto</span>
          </summary>
          <div className={styles.foldBody}>
            <div className={styles.foldRow}>
              <span>Active regions with alerts</span>
              <strong>{activeRegions}</strong>
            </div>
            <div className={styles.foldRow}>
              <span>Estimated blast radius</span>
              <strong>{estImpactedUsers.toLocaleString()} users</strong>
            </div>
            <div className={styles.foldRow}>
              <span>Revenue exposure</span>
              <strong>${estRevenueRisk.toLocaleString()}/hr</strong>
            </div>
          </div>
        </details>

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
