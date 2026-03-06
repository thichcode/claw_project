"use client";

import { useEffect, useState } from "react";

const KEY_SHOW_LEFT = "wm_widget_show_left";
const KEY_SHOW_RIGHT = "wm_widget_show_right";
const KEY_REFRESH = "wm_refresh_sec";

export default function WidgetControlsBar() {
  const [showLeft, setShowLeft] = useState(true);
  const [showRight, setShowRight] = useState(true);
  const [refreshSec, setRefreshSec] = useState(8);

  useEffect(() => {
    const sl = localStorage.getItem(KEY_SHOW_LEFT);
    const sr = localStorage.getItem(KEY_SHOW_RIGHT);
    const rf = localStorage.getItem(KEY_REFRESH);
    setShowLeft(sl == null ? true : sl === "1");
    setShowRight(sr == null ? true : sr === "1");
    setRefreshSec(rf == null ? 8 : Number(rf));
  }, []);

  function updateShow(nextLeft, nextRight) {
    setShowLeft(nextLeft);
    setShowRight(nextRight);
    localStorage.setItem(KEY_SHOW_LEFT, nextLeft ? "1" : "0");
    localStorage.setItem(KEY_SHOW_RIGHT, nextRight ? "1" : "0");
    window.dispatchEvent(new CustomEvent("wm-widget-visibility-change"));
  }

  function updateRefresh(v) {
    const n = Number(v);
    setRefreshSec(n);
    localStorage.setItem(KEY_REFRESH, String(n));
    window.dispatchEvent(new CustomEvent("wm-refresh-change", { detail: n }));
  }

  return (
    <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center", fontSize: 12, padding: "6px 10px", border: "1px solid #243049", borderRadius: 10, background: "rgba(10,16,30,.75)" }}>
      <strong style={{ color: "#9fb3cd" }}>Widgets</strong>
      <label><input type="checkbox" checked={showLeft} onChange={(e) => updateShow(e.target.checked, showRight)} /> Left</label>
      <label><input type="checkbox" checked={showRight} onChange={(e) => updateShow(showLeft, e.target.checked)} /> Right</label>
      <label>
        Auto F5:
        <select value={String(refreshSec)} onChange={(e) => updateRefresh(e.target.value)} style={{ marginLeft: 6 }}>
          <option value="0">Off</option>
          <option value="5">5s</option>
          <option value="8">8s</option>
          <option value="15">15s</option>
          <option value="30">30s</option>
          <option value="60">60s</option>
        </select>
      </label>
    </div>
  );
}
