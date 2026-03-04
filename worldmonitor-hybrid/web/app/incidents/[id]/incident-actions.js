"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost } from "../../actions-client";

export default function IncidentActions({ incidentId, status }) {
  const [assignee, setAssignee] = useState("1");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function run(action) {
    setBusy(true);
    try {
      await action();
      setComment("");
      router.refresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 20, display: "grid", gap: 12 }}>
      <div>
        <input
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
          style={{ marginRight: 8 }}
          placeholder="Assignee user ID"
        />
        <button disabled={busy} onClick={() => run(() => apiPost(`/incidents/${incidentId}/assign`, { assignee_id: Number(assignee || 0) }))}>
          Assign
        </button>
      </div>

      <div>
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Add comment"
          style={{ marginRight: 8, minWidth: 260 }}
        />
        <button disabled={busy || !comment.trim()} onClick={() => run(() => apiPost(`/incidents/${incidentId}/comment`, { comment }))}>
          Comment
        </button>
      </div>

      <div>
        <button
          disabled={busy || status === "resolved"}
          onClick={() => run(() => apiPost(`/incidents/${incidentId}/resolve`, {}))}
        >
          Resolve
        </button>
      </div>
    </div>
  );
}
