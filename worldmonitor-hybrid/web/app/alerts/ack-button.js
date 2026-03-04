"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function AckButton({ alertId, disabled }) {
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function onAck() {
    setBusy(true);
    try {
      const res = await fetch(`/api/alerts/${alertId}/ack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ack_note: "Acknowledged by NOC" }),
      });
      if (!res.ok) throw new Error("ACK failed");
      router.refresh();
    } catch (e) {
      alert(e.message || "ACK failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <button className="wm-button" onClick={onAck} disabled={disabled || busy}>
      {busy ? "Acking..." : "ACK"}
    </button>
  );
}
