import styles from "./ui.module.css";

export function PanelCard({ title, children, className = "" }) {
  return (
    <section className={`${styles.panel} ${className}`.trim()}>
      {title ? <h3 className={styles.panelTitle}>{title}</h3> : null}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, right, children }) {
  return (
    <header className={styles.pageHeader}>
      <div>
        <h1 className={styles.pageTitle}>{title}</h1>
        {subtitle ? <p className={styles.pageSubtitle}>{subtitle}</p> : null}
      </div>
      {right ? <div className={styles.pageHeaderRight}>{right}</div> : null}
      {children ? <div className={styles.pageHeaderBottom}>{children}</div> : null}
    </header>
  );
}

export function StatusBadge({ status }) {
  const raw = String(status || "info");
  const key = raw.toLowerCase().split(" ")[0].split(":")[0];
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
    info: styles.info,
  };
  return <span className={`${styles.badge} ${map[key] || styles.info}`}>{raw || "unknown"}</span>;
}

export function KPI({ value, label }) {
  return (
    <PanelCard className={styles.metricTile}>
      <div className={styles.kpiValue}>{value}</div>
      <div className={styles.kpiLabel}>{label}</div>
    </PanelCard>
  );
}

export function MetricTile({ value, label, trend, tone = "info" }) {
  const toneClass = {
    critical: styles.metricCritical,
    warning: styles.metricWarning,
    ok: styles.metricOk,
    info: styles.metricInfo,
  }[tone] || styles.metricInfo;

  return (
    <PanelCard className={`${styles.metricTile} ${toneClass}`}>
      <div className={styles.kpiValue}>{value}</div>
      <div className={styles.kpiLabel}>{label}</div>
      {trend ? <div className={styles.metricTrend}>{trend}</div> : null}
    </PanelCard>
  );
}

export function SectionTitle({ title, meta }) {
  return (
    <div className={styles.sectionTitle}>
      <h2>{title}</h2>
      {meta ? <span>{meta}</span> : null}
    </div>
  );
}

export function DataTable({ children, compact = false }) {
  return <div className={`${styles.tableWrap} ${compact ? styles.tableCompact : ""}`}>{children}</div>;
}

export function PillTabs({ items = [], active }) {
  return (
    <div className={styles.pillTabs}>
      {items.map((it) => (
        <a key={it.href} href={it.href} className={`${styles.pillTab} ${active === it.key ? styles.pillTabActive : ""}`}>
          {it.label}
        </a>
      ))}
    </div>
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
