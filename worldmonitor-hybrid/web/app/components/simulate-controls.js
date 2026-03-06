"use client";

import { useState } from "react";

export default function SimulateControls() {
  const [loading, setLoading] = useState("");
  const [msg, setMsg] = useState("");

  async function runPreset(preset) {
    try {
      setLoading(preset);
      setMsg("");
      const r = await fetch("/api/simulate/preset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset, reset: true }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data?.error || "simulate failed");
      const ra = data.resetAlerts === -1 ? "all" : (data.resetAlerts || 0);
      const ri = data.resetIncidents === -1 ? "all" : (data.resetIncidents || 0);
      setMsg(`Preset ${preset}: reset ${ra} alerts, ${ri} incidents; bơm +${data.events || 0} alerts, +${data.incidents || 0} incidents`);
      setTimeout(() => window.location.reload(), 800);
    } catch (e) {
      setMsg(`Lỗi: ${String(e.message || e)}`);
    } finally {
      setLoading("");
    }
  }

  const btn = (preset, label, color) => (
    <button
      onClick={() => runPreset(preset)}
      disabled={!!loading}
      style={{
        border: "1px solid #334155",
        background: color,
        color: "#e2e8f0",
        borderRadius: 8,
        padding: "6px 10px",
        fontSize: 12,
        fontWeight: 700,
        cursor: loading ? "not-allowed" : "pointer",
        opacity: loading && loading !== preset ? 0.6 : 1,
      }}
    >
      {loading === preset ? "Running..." : label}
    </button>
  );

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {btn("normal", "Preset Normal", "#0f766e")}
        {btn("degraded", "Preset Degraded", "#92400e")}
        {btn("incident-storm", "Preset Incident Storm", "#7f1d1d")}
      </div>
      {msg ? <div style={{ color: "#93c5fd", fontSize: 12 }}>{msg}</div> : null}
    </div>
  );
}
