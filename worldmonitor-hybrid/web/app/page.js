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
  const openIncidents = toSafeCount(n?.open_incidents);
  const openAlerts = toSafeCount(n?.open_alerts);
  return sev * 100 + openIncidents * 30 + openAlerts * 8;
}

function ensureArray(value) {
  return Array.isArray(value) ? value : [];
}

function toSafeNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function toSafeCount(value) {
  return Math.max(0, toSafeNumber(value));
}

function normalizeLocationCode(value) {
  return String(value || "").trim();
}

function normalizeLocationKey(value) {
  return normalizeLocationCode(value).toLowerCase();
}

function isOpenStatus(value) {
  return normalizeLocationKey(value) === "open";
}

function countOpenRecords(rows) {
  return ensureArray(rows).filter((row) => isOpenStatus(row?.status)).length;
}

export default async function DashboardPage({ searchParams }) {
  const locationParam = String(searchParams?.location || "all").trim();
  const warMode = String(searchParams?.war || "0") === "1";
  const tvMode = String(searchParams?.tv || "0") === "1";
  const rangeParam = String(searchParams?.range || "1h").trim();
  const range = ["15m", "1h", "24h"].includes(rangeParam) ? rangeParam : "1h";
  const summaryRaw = await safeApiGet("/summary", mockSummary);
  const summary = {
    ...mockSummary,
    ...(summaryRaw || {}),
    open_alerts: toSafeCount(summaryRaw?.open_alerts ?? mockSummary.open_alerts),
    open_incidents: toSafeCount(summaryRaw?.open_incidents ?? mockSummary.open_incidents),
  };
  const dataWindow = String(summaryRaw?.data_window || range).trim() || range;
  const isSimulated = !summaryRaw || summaryRaw?.simulated === true;
  const locationsRaw = await safeApiGet("/locations", []);
  const normalizedLocations = Array.from(
    new Map(
      ensureArray(locationsRaw)
        .map((item) => {
          const code = normalizeLocationCode(item?.code);
          const key = normalizeLocationKey(code);
          return key ? [key, { ...item, code }] : null;
        })
        .filter(Boolean)
    ).values()
  );
  const locationFromCatalog = normalizedLocations.find(
    (item) => normalizeLocationKey(item.code) === normalizeLocationKey(locationParam)
  )?.code;
  const location =
    locationParam.toLowerCase() === "all"
      ? "all"
      : locationFromCatalog || "all";

  const topologyPath = location === "all" ? "/topology" : `/topology?location_code=${encodeURIComponent(location)}`;
  const topologyPromise = safeApiGet(topologyPath, { nodes: [], edges: [] });
  const topologyGlobalPromise =
    location === "all" ? topologyPromise : safeApiGet("/topology", { nodes: [], edges: [] });

  const locCodes = Array.from(
    new Map(
      [...normalizedLocations.map((l) => l.code), ...(location !== "all" ? [location] : [])]
        .map((code) => {
          const normalizedCode = normalizeLocationCode(code);
          const key = normalizeLocationKey(normalizedCode);
          return key ? [key, normalizedCode] : null;
        })
        .filter(Boolean)
    ).values()
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

  const focusedOpenIncidents =
    location === "all" ? summary.open_incidents : countOpenRecords(incidents);
  const focusedOpenAlerts =
    location === "all" ? summary.open_alerts : countOpenRecords(alerts);

  const rangeFactor = range === "15m" ? 0.35 : range === "24h" ? 2.4 : 1;
  const estImpactedUsers = Math.round((focusedOpenAlerts * 230 + focusedOpenIncidents * 900) * rangeFactor);
  const estRevenueRisk = Math.round((focusedOpenIncidents * 1200 + focusedOpenAlerts * 180) * rangeFactor);
  const slaRisk = Math.min(99, Math.round((focusedOpenIncidents * 8 + focusedOpenAlerts * 2.3) * (warMode ? 1.2 : 1)));
  const activeRegionsFromLocationTopology = topologyByLocation.filter((item) =>
    ensureArray(item.data?.nodes).some(
      (n) => toSafeCount(n?.open_alerts) > 0 || toSafeCount(n?.open_incidents) > 0
    )
  ).length;

  const activeRegionsFromGlobalTopology = new Set(
    ensureArray(topologyGlobal?.nodes)
      .filter((n) => toSafeCount(n?.open_alerts) > 0 || toSafeCount(n?.open_incidents) > 0)
      .map((n) => normalizeLocationKey(n?.location_code))
      .filter(Boolean)
  ).size;

  const activeRegions =
    activeRegionsFromLocationTopology > 0
      ? activeRegionsFromLocationTopology
      : activeRegionsFromGlobalTopology;

  const isBackendWarming =
    !isSimulated && normalizedLocations.length === 0 && alerts.length === 0 && incidents.length === 0;

  return (
    <main className={`${styles.shell} ${tvMode ? styles.shellTv : ""}`}>
      <div className={styles.topbar}>
        <div className={styles.brand}>
          <span className={styles.brandDot} />
          <div>
            <div className={styles.title}>HORUS-STYLE GLOBAL MONITOR</div>
            <div className={styles.sub}>location → service health intelligence</div>
          </div>
        </div>
        <div className={styles.topbarStats}>
          <AutoRefresh seconds={8} />
          <span className={styles.windowPill}>Window {dataWindow}</span>
          <StatusBadge status={`critical ${focusedOpenAlerts || 0}`} />
          <StatusBadge status={`open incidents ${focusedOpenIncidents || 0}`} />
        </div>
        <div className={styles.topbarMeta}>
          <span className={styles.metaPill}>
            {location === "all" ? "Global" : location} · {dataWindow} window{warMode ? " · War" : ""}{tvMode ? " · TV" : ""}
          </span>
          <span className={styles.metaPillSecondary}>
            {isSimulated ? "Simulated feed" : "Live API feed"}
          </span>
          {isBackendWarming && (
            <span className={styles.metaPillWarn}>Backend warming up</span>
          )}
          <span className={styles.metaPillInfo}>
            {normalizedLocations.length} loc · {alerts.length} alerts · {incidents.length} incidents
          </span>
          <a
            className={`${styles.metaToggle} ${tvMode ? styles.metaToggleActive : ""}`}
            href={`/?location=${encodeURIComponent(location)}&range=${encodeURIComponent(range)}&war=${warMode ? "1" : "0"}&tv=${tvMode ? "0" : "1"}`}
          >
            {tvMode ? "Exit TV mode" : "TV mode"}
          </a>
        </div>
      </div>

      {!tvMode && (
      <>
      <details
        className={`${styles.noticePanel} ${!isSimulated ? styles.noticePanelLive : ""}`}
        open={isSimulated}
      >
        <summary className={styles.noticeSummary}>
          <span>{isSimulated ? "Demo data notice" : "Live feed status"}</span>
          <span className={styles.noticePill}>{isSimulated ? "Simulated" : "Live"}</span>
        </summary>
        <div className={styles.noticeBody}>
          {isSimulated
            ? "⚠ SIMULATED / ESTIMATED DATA (demo mode) — không dùng để ra quyết định production."
            : "Live API connected — chỉ số đang lấy từ backend rollout."}
          <div className={styles.noticeSub}>
            Feed coverage: {normalizedLocations.length} locations · {alerts.length} alerts · {incidents.length} incidents · Window {dataWindow}
          </div>
        </div>
      </details>

      <div className={styles.controlStack}>
        <div className={styles.sectionLabel}>Locations</div>
        <div className={styles.locationLinks}>
          <a
            href={`/?range=${encodeURIComponent(range)}&war=${warMode ? "1" : "0"}&tv=${tvMode ? "1" : "0"}`}
            className={`${styles.locationLink} ${location === "all" ? styles.locationLinkActive : styles.locationLinkInactive}`}
          >
            Global
          </a>
          {normalizedLocations.map((l) => (
            <a
              key={l.code}
              href={`/?location=${encodeURIComponent(l.code)}&range=${encodeURIComponent(range)}&war=${warMode ? "1" : "0"}&tv=${tvMode ? "1" : "0"}`}
              className={`${styles.locationLink} ${location === l.code ? styles.locationLinkActive : styles.locationLinkInactive}`}
            >
              {l.code}
            </a>
          ))}
        </div>
        {normalizedLocations.length === 0 && (
          <div className={styles.locationHint}>No location data yet — showing Global only.</div>
        )}

        <div className={styles.quickBar}>
          <strong className={styles.quickLabel}>Quick Mode</strong>
          <a
            className={`${styles.quickLink} ${warMode ? styles.quickLinkActive : ""}`}
            href={`/?location=${encodeURIComponent(location)}&range=${encodeURIComponent(range)}&war=${warMode ? "0" : "1"}&tv=${tvMode ? "1" : "0"}`}
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
              href={`/?location=${encodeURIComponent(location)}&range=${r.k}&war=${warMode ? "1" : "0"}&tv=${tvMode ? "1" : "0"}`}
            >
              {r.t}
            </a>
          ))}
        </div>

        <details className={styles.foldPanel} open>
          <summary className={styles.foldSummary}>
            <span>Key KPI Snapshot</span>
            <span className={styles.foldPill}>Live</span>
          </summary>
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
        </details>

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
      </>
      )}

      <div className={`${styles.content} ${tvMode ? styles.contentTv : ""}`}>
        <div className={`${styles.fullMapStage} ${tvMode ? styles.fullMapStageTv : ""}`}>
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
