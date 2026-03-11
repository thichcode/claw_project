from .base import Tool


class NoteWriterTool(Tool):
    name = "note_writer"

    async def execute(self, payload: dict) -> dict:
        ctx = payload.get("context", {})
        goal = payload.get("goal") or ctx.get("goal") or ""
        note = f"Summary for goal: {goal}\n- Collected sources\n- Drafted concise notes"
        return {"ok": True, "note": note, "message": "Summary notes created"}
