"use client";

import { useEffect, useState } from "react";

const KEY_REFRESH = "wm_refresh_sec";

export default function AutoRefresh({ seconds = 8 }) {
  const [sec, setSec] = useState(seconds);

  useEffect(() => {
    const saved = localStorage.getItem(KEY_REFRESH);
    if (saved != null) setSec(Number(saved));

    const onChanged = (e) => {
      const v = Number(e?.detail ?? localStorage.getItem(KEY_REFRESH) ?? seconds);
      setSec(v);
    };

    window.addEventListener("wm-refresh-change", onChanged);
    window.addEventListener("storage", onChanged);
    return () => {
      window.removeEventListener("wm-refresh-change", onChanged);
      window.removeEventListener("storage", onChanged);
    };
  }, [seconds]);

  useEffect(() => {
    if (!sec || sec <= 0) return;

    let pauseUntil = 0;
    const pause = () => {
      pauseUntil = Date.now() + 12000; // pause 12s while user is interacting
    };

    const onInteract = (e) => {
      const tag = (e?.target?.tagName || "").toLowerCase();
      if (["button", "a", "input", "select", "textarea"].includes(tag)) pause();
    };

    window.addEventListener("pointerdown", onInteract, true);
    window.addEventListener("keydown", pause, true);

    const id = setInterval(() => {
      if (Date.now() < pauseUntil) return;
      window.location.reload();
    }, Math.max(3, sec) * 1000);

    return () => {
      clearInterval(id);
      window.removeEventListener("pointerdown", onInteract, true);
      window.removeEventListener("keydown", pause, true);
    };
  }, [sec]);

  return <span style={{ color: "#64748b", fontSize: 12 }}>auto-refresh {sec > 0 ? `${sec}s` : "off"}</span>;
}
