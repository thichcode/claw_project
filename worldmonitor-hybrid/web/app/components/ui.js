import styles from "./ui.module.css";

export function PanelCard({ title, children, className = "" }) {
  return (
    <section className={`${styles.panel} ${className}`.trim()}>
      {title ? <h3 className={styles.panelTitle}>{title}</h3> : null}
      {children}
    </section>
  );
}

export function StatusBadge({ status }) {
  const key = String(status || "info").toLowerCase();
  const map = {
    critical: styles.critical,
    high: styles.critical,
    open: styles.critical,
    degraded: styles.warning,
    warning: styles.warning,
    medium: styles.warning,
    acked: styles.info,
    assigned: styles.info,
    healthy: styles.ok,
    resolved: styles.ok,
    low: styles.ok,
  };
  return <span className={`${styles.badge} ${map[key] || styles.info}`}>{status || "unknown"}</span>;
}

export function KPI({ value, label }) {
  return (
    <PanelCard>
      <div className={styles.kpiValue}>{value}</div>
      <div className={styles.kpiLabel}>{label}</div>
    </PanelCard>
  );
}

export function HotspotTable({ rows }) {
  return (
    <table className="wm-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Issue</th>
          <th>Trend (15m)</th>
          <th>Owner</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, idx) => (
          <tr key={row.issue + idx}>
            <td>{idx + 1}</td>
            <td>{row.issue}</td>
            <td className={String(row.trend || "").startsWith("↑") ? styles.hotspotTrendUp : styles.hotspotTrendDown}>{row.trend}</td>
            <td>{row.owner}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
