"use client";

import { useEffect, useRef, useState } from "react";
import { StatusBadge } from "./ui";
import styles from "../home.module.css";

const KEY_LEFT = "wm_widget_left";
const KEY_RIGHT = "wm_widget_right";
const KEY_SHOW_LEFT = "wm_widget_show_left";
const KEY_SHOW_RIGHT = "wm_widget_show_right";

function loadJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function useWidgetState(key, fallback) {
  const [state, setState] = useState(fallback);

  useEffect(() => {
    setState(loadJson(key, fallback));
  }, [key]);

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch {}
  }, [key, state]);

  return [state, setState];
}

function useWidgetDrag(setPos) {
  const drag = useRef(null);

  function onMouseDown(e) {
    const widget = e.currentTarget.parentElement;
    const stage = widget?.parentElement;
    if (!widget || !stage) return;

    const wRect = widget.getBoundingClientRect();
    const sRect = stage.getBoundingClientRect();

    drag.current = {
      ox: e.clientX - wRect.left,
      oy: e.clientY - wRect.top,
      sx: sRect.left,
      sy: sRect.top,
      sw: sRect.width,
      sh: sRect.height,
      ww: wRect.width,
      wh: wRect.height,
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  function onMouseMove(e) {
    if (!drag.current) return;
    const d = drag.current;

    let left = e.clientX - d.sx - d.ox;
    let top = e.clientY - d.sy - d.oy;

    left = Math.max(6, Math.min(left, d.sw - d.ww - 6));
    top = Math.max(6, Math.min(top, d.sh - d.wh - 6));

    setPos((p) => ({ ...p, left, top }));
  }

  function onMouseUp() {
    drag.current = null;
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
  }

  return { onMouseDown };
}

function Widget({ title, pos, setPos, children }) {
  const ref = useRef(null);
  const drag = useWidgetDrag(setPos);

  useEffect(() => {
    const el = ref.current;
    if (!el || !window.ResizeObserver) return;

    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setPos((p) => ({ ...p, width: Math.round(r.width), height: Math.round(r.height) }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [setPos]);

  return (
    <div
      ref={ref}
      className={styles.floatingWidget}
      style={{ left: pos.left, top: pos.top, width: pos.width, height: pos.height }}
    >
      <div className={styles.widgetHeader} onMouseDown={drag.onMouseDown}>{title}</div>
      <div className={styles.widgetBody}>{children}</div>
    </div>
  );
}

export default function FloatingWidgets({ leftAlerts = [], rightIncidents = [], hotspotRows = [] }) {
  const dedupAlerts = Object.values(
    leftAlerts.reduce((acc, a) => {
      const key = `${a.service_name || "unknown"}::${a.severity || "info"}`;
      if (!acc[key]) acc[key] = a;
      return acc;
    }, {})
  ).slice(0, 5);

  const topHotspots = (hotspotRows || []).slice(0, 5);
  const [leftPos, setLeftPos] = useWidgetState(KEY_LEFT, { left: 10, top: 10, width: 330, height: 420 });
  const [rightPos, setRightPos] = useWidgetState(KEY_RIGHT, { left: 980, top: 10, width: 330, height: 420 });
  const [showLeft, setShowLeft] = useState(true);
  const [showRight, setShowRight] = useState(true);

  useEffect(() => {
    const sync = () => {
      const sl = localStorage.getItem(KEY_SHOW_LEFT);
      const sr = localStorage.getItem(KEY_SHOW_RIGHT);
      setShowLeft(sl == null ? true : sl === "1");
      setShowRight(sr == null ? true : sr === "1");
    };

    sync();
    window.addEventListener("storage", sync);
    window.addEventListener("wm-widget-visibility-change", sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("wm-widget-visibility-change", sync);
    };
  }, []);

  return (
    <>
      {showLeft ? (
        <Widget title="Live Signal Feed" pos={leftPos} setPos={setLeftPos}>
          {dedupAlerts.map((a) => (
            <div key={a.id} className={styles.feedItem}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <strong style={{ fontSize: 12 }}>{a.service_name || "unknown-service"}</strong>
                <StatusBadge status={a.severity || "info"} />
              </div>
              <div style={{ color: "#c8d3e2", fontSize: 12, marginTop: 4 }}>{a.title}</div>
              <div className={styles.feedMeta}>{a.location_code || "global"} · {a.source || "-"}</div>
            </div>
          ))}
        </Widget>
      ) : null}

      {showRight ? (
        <Widget title="Incidents & Hotspots" pos={rightPos} setPos={setRightPos}>
          {rightIncidents.map((i) => (
            <div key={`inc-${i.id}`} className={styles.feedItem}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <strong style={{ fontSize: 12 }}>INC #{i.id}</strong>
                <StatusBadge status={i.severity || "high"} />
              </div>
              <div style={{ color: "#c8d3e2", fontSize: 12, marginTop: 4 }}>{i.title}</div>
              <div className={styles.feedMeta}>{i.location_code || "global"} · {i.service_name || "-"}</div>
              <div className={styles.feedMeta}>owner: {(i.assignee_id ? `oncall-${i.assignee_id}` : "unassigned")}</div>
              <div className={styles.feedMeta}>next: Investigating dependencies · ETA: ~{(i.severity || "").toLowerCase() === "critical" ? "15m" : "30m"}</div>
            </div>
          ))}

          {topHotspots.map((h) => (
            <div key={`hot-${h.service_id}`} className={styles.feedItem}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <strong style={{ fontSize: 12 }}>{h.name}</strong>
                <StatusBadge status={h.health} />
              </div>
              <div className={styles.feedMeta}>alerts {h.open_alerts || 0} · incidents {h.open_incidents || 0}</div>
            </div>
          ))}
        </Widget>
      ) : null}
    </>
  );
}
