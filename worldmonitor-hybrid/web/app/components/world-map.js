"use client";

import { useEffect, useMemo, useState } from "react";
import styles from "../home.module.css";

function healthColor(health) {
  const h = String(health || "").toLowerCase();
  if (h === "critical") return "#ef4444";
  if (h === "warning") return "#f59e0b";
  return "#22c55e";
}

const REGION_LAYOUT = {
  azure: { label: "AZURE", x: 8, y: 20, w: 24, h: 55 },
  aws: { label: "AWS", x: 36, y: 12, w: 24, h: 58 },
  hn: { label: "HN", x: 64, y: 18, w: 28, h: 24 },
  sgn: { label: "SGN", x: 64, y: 44, w: 28, h: 18 },
  dng: { label: "DNG", x: 64, y: 66, w: 28, h: 12 },
};

const LOCATION_TO_REGION = {
  "hcm-dc1": "sgn",
  "hn-edge": "hn",
  "sgp-az1": "aws",
  "dng-edge": "dng",
};

const LOCATION_POS = {
  "hcm-dc1": { x: 76, y: 52 },
  "hn-edge": { x: 74, y: 30 },
  "sgp-az1": { x: 48, y: 38 },
  "dng-edge": { x: 74, y: 72 },
};

function edgeMetrics(edge, fromNode, toNode, tick = 0, timeRange = "1h") {
  const criticality = String(edge.criticality || "medium").toLowerCase();
  const basePing = criticality === "critical" ? 42 : criticality === "high" ? 28 : criticality === "low" ? 12 : 20;
  const extra =
    (String(fromNode?.health || "").toLowerCase() === "critical" ? 18 : 0) +
    (String(toNode?.health || "").toLowerCase() === "critical" ? 18 : 0) +
    (String(fromNode?.health || "").toLowerCase() === "warning" ? 8 : 0) +
    (String(toNode?.health || "").toLowerCase() === "warning" ? 8 : 0);

  const wave = Math.round(Math.sin((tick + Number(edge.from_service_id || 1)) / 3) * 6);
  const rangeBoost = timeRange === "24h" ? 8 : timeRange === "15m" ? -4 : 0;
  const ping = Math.max(7, basePing + extra + wave + rangeBoost);
  const mbps = Math.max(65, Math.round(1800 / (1 + ping / 22)));
  return { ping, mbps };
}

function fakeServers(node, locationCode, tick = 0) {
  const sid = Number(node?.service_id || 1);
  const b = (sid * 13) % 250;
  const mk = (offset, role, suffix) => {
    const cpu = Math.max(8, Math.min(98, Math.round(42 + Math.sin((tick + sid + offset) / 2) * 34)));
    const ram = Math.max(18, Math.min(96, Math.round(48 + Math.cos((tick + sid + offset) / 3) * 26)));
    const loss = Math.max(0, Math.min(12, Number((Math.abs(Math.sin((tick + sid + offset) / 4)) * 4.2).toFixed(1))));
    return {
      host: `${node.name}-${suffix}`,
      ip: `10.${(sid % 200) + 1}.${(b % 250) + 1}.${offset}`,
      location: locationCode,
      role,
      cpu,
      ram,
      loss,
    };
  };

  return [
    mk(11, "app", "srv-01"),
    mk(12, "app", "srv-02"),
    mk(21, "db", "db-01"),
  ];
}

export default function WorldMap({ topologyByLocation = [], topologyGlobal = { nodes: [], edges: [] }, warMode = false, timeRange = "1h" }) {
  const [zoom, setZoom] = useState("global");
  const [showHealthy, setShowHealthy] = useState(!warMode);
  const [selected, setSelected] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (warMode) setShowHealthy(false);
  }, [warMode]);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 2000);
    return () => clearInterval(id);
  }, []);

  const transform = useMemo(() => {
    if (zoom === "azure") return "scale(1.42) translate(16%, -8%)";
    if (zoom === "aws") return "scale(1.42) translate(2%, -8%)";
    if (zoom === "hn") return "scale(1.55) translate(-17%, -20%)";
    if (zoom === "sgn") return "scale(1.55) translate(-17%, -6%)";
    if (zoom === "dng") return "scale(1.55) translate(-17%, 8%)";
    return "scale(1) translate(0,0)";
  }, [zoom]);

  const regionStats = useMemo(() => {
    const stats = {};
    Object.keys(REGION_LAYOUT).forEach((k) => {
      stats[k] = { services: 0, servers: 0 };
    });

    for (const row of topologyByLocation) {
      const region = LOCATION_TO_REGION[row.code] || "apac";
      if (!stats[region]) continue;
      const services = (row.data?.nodes || []).length;
      stats[region].services += services;
      stats[region].servers += services * 3; // demo ratio: 1 service ~ 3 servers
    }
    return stats;
  }, [topologyByLocation]);

  const visibleRows = topologyByLocation.filter((row) => {
    const region = LOCATION_TO_REGION[row.code] || "apac";
    return zoom === "global" || zoom === region;
  });

  const servicePoints = useMemo(() => {
    const map = new Map();
    for (const row of visibleRows) {
      const center = LOCATION_POS[row.code] || { x: 50, y: 50 };
      const nodes = (row.data?.nodes || []);
      const count = Math.max(nodes.length, 1);
      const radius = Math.min(8, 3.6 + Math.min(count, 16) * 0.18);

      nodes.forEach((n, idx) => {
        const angle = (Math.PI * 2 * idx) / count;
        const px = center.x + Math.cos(angle) * radius;
        const py = center.y + Math.sin(angle) * radius;
        map.set(Number(n.service_id), { x: px, y: py, node: n, locationCode: row.code });
      });
    }
    return map;
  }, [visibleRows, showHealthy]);

  const nodeByServiceId = useMemo(() => {
    const m = new Map();
    for (const n of topologyGlobal?.nodes || []) m.set(Number(n.service_id), n);
    return m;
  }, [topologyGlobal]);

  const edgeLines = useMemo(() => {
    const lines = [];
    for (const e of topologyGlobal?.edges || []) {
      const fromId = Number(e.from_service_id);
      const toId = Number(e.to_service_id);
      const p1 = servicePoints.get(fromId);
      const p2 = servicePoints.get(toId);
      if (!p1 || !p2) continue;

      const n1 = nodeByServiceId.get(fromId);
      const n2 = nodeByServiceId.get(toId);
      const critical = String(e.criticality || "").toLowerCase() === "critical" || String(n1?.health || "") === "critical" || String(n2?.health || "") === "critical";
      lines.push({ e, p1, p2, critical, metrics: edgeMetrics(e, n1, n2, tick, timeRange) });
    }
    return lines;
  }, [topologyGlobal, servicePoints, nodeByServiceId, tick]);

  const selectedServers = selected ? fakeServers(selected.node, selected.locationCode, tick) : [];

  return (
    <section className={styles.mapWrap}>
      <div className={styles.gridOverlay} />

      <div className={styles.mapToolbar}>
        <button className={styles.toolbarBtn} onClick={() => setZoom("global")}>Global</button>
        <button className={styles.toolbarBtn} onClick={() => setZoom("azure")}>Azure</button>
        <button className={styles.toolbarBtn} onClick={() => setZoom("aws")}>AWS</button>
        <button className={styles.toolbarBtn} onClick={() => setZoom("hn")}>HN</button>
        <button className={styles.toolbarBtn} onClick={() => setZoom("sgn")}>SGN</button>
        <button className={styles.toolbarBtn} onClick={() => setZoom("dng")}>DNG</button>
        <button className={styles.toolbarBtn} onClick={() => setShowHealthy((v) => !v)}>
          {showHealthy ? "Hide Healthy" : "Show Healthy"}
        </button>
      </div>

      <div className={styles.mapScene} style={{ transform }}>
        <svg className={styles.linkLayer} viewBox="0 0 100 100" preserveAspectRatio="none">
          {edgeLines.map((l, idx) => {
            const mx = (l.p1.x + l.p2.x) / 2;
            const my = (l.p1.y + l.p2.y) / 2 - 2.2;
            return (
              <g key={`${l.e.from_service_id}-${l.e.to_service_id}-${idx}`}>
                <path
                  d={`M ${l.p1.x} ${l.p1.y} Q ${mx} ${my} ${l.p2.x} ${l.p2.y}`}
                  className={`${styles.mapLink} ${l.critical ? styles.linkCritical : ""}`}
                  style={{ strokeWidth: warMode ? (l.critical ? 2.1 : 1.35) : undefined, opacity: warMode ? (l.critical ? 0.95 : 0.72) : undefined }}
                />
                <text x={mx} y={my - 0.6} textAnchor="middle" className={styles.linkMetric}>
                  {`${l.metrics.ping}ms · ${l.metrics.mbps}Mbps`}
                </text>
              </g>
            );
          })}
        </svg>

        {Object.entries(REGION_LAYOUT).map(([key, r]) => {
          const s = regionStats[key] || { services: 0, servers: 0 };
          const scale = Math.min(1.45, 1 + Math.sqrt(Math.max(s.services, 0)) * 0.08);
          const w = Math.min(34, r.w * scale);
          const h = Math.min(62, r.h * scale);
          return (
            <div
              key={key}
              className={styles.region}
              style={{ left: `${r.x}%`, top: `${r.y}%`, width: `${w}%`, height: `${h}%` }}
              title={`${r.label}: ${s.services} services · ${s.servers} servers`}
            >
              <span className={styles.regionLabel}>{r.label} · {s.services} svc / {s.servers} srv</span>
            </div>
          );
        })}

        {visibleRows.map((row) => {
          const pos = LOCATION_POS[row.code] || { x: 50, y: 50 };
          return (
            <div key={row.code} className={styles.locationNode} style={{ left: `${pos.x}%`, top: `${pos.y}%` }}>
              <div className={styles.locationLabel}>{row.code}</div>
            </div>
          );
        })}

        {Array.from(servicePoints.values())
          .filter((p) => showHealthy || String(p.node.health || "").toLowerCase() !== "healthy")
          .map((p) => {
          const hc = String(p.node.health || "").toLowerCase();
          const isSelected = selected?.node?.service_id === p.node.service_id;
          return (
            <button
              key={`svc-dot-${p.node.service_id}`}
              type="button"
              className={`${styles.dot} ${styles.serviceDotAbsolute} ${hc === "critical" ? styles.pulse : ""}`}
              title={`${p.node.name} · ${p.node.health} · click để xem server/IP`}
              onClick={() => setSelected(p)}
              style={{
                left: `${p.x}%`,
                top: `${p.y}%`,
                background: healthColor(p.node.health),
                boxShadow: `0 0 10px ${healthColor(p.node.health)}88`,
                outline: isSelected ? "2px solid #93c5fd" : "none",
                cursor: "pointer",
              }}
            />
          );
        })}
      </div>

      {selected ? (
        <div className={styles.mapDetails}>
          <div className={styles.mapDetailsTitle}>{selected.node.name} · {selected.node.health} · {selected.locationCode}</div>
          {selectedServers.map((s) => (
            <div key={`${s.host}-${s.ip}`} className={styles.mapDetailsRow}>
              <span>{s.host}</span>
              <span>{s.ip}</span>
              <span>{s.role}</span>
              <span>CPU {s.cpu}%</span>
              <span>RAM {s.ram}%</span>
              <span>loss {s.loss}%</span>
            </div>
          ))}
        </div>
      ) : null}

      <div className={styles.legend}>
        <span className={styles.legendItem}><span className={styles.smallDot} style={{ background: "#22c55e" }} /> healthy</span>
        <span className={styles.legendItem}><span className={styles.smallDot} style={{ background: "#f59e0b" }} /> warning</span>
        <span className={styles.legendItem}><span className={styles.smallDot} style={{ background: "#ef4444" }} /> critical</span>
      </div>
    </section>
  );
}
