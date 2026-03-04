"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function IncidentActions({ incidentId }) {
  const router = useRouter();
  const [assignee, setAssignee] = useState("2");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  async function act(action, payload = {}) {
    setBusy(true);
    try {
      const res = await fetch(`/api/incidents/${incidentId}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Action failed: ${action}`);
      setComment("");
      router.refresh();
    } catch (e) {
      alert(e.message || "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
        <button className="wm-button alt" disabled={busy} onClick={() => act("assign", { assignee_id: Number(assignee) || 2 })}>Assign</button>
        <button className="wm-button warn" disabled={busy} onClick={() => act("comment", { comment: comment || "Investigating" })}>Comment</button>
        <button className="wm-button good" disabled={busy} onClick={() => act("resolve")}>Resolve</button>
      </div>
      <div style={{ display: "grid", gap: 8 }}>
        <input className="wm-input" value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="Assignee ID" />
        <input className="wm-input" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment" />
      </div>
    </div>
  );
}
