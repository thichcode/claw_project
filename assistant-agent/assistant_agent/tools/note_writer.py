"""Note writer tool for MVP."""

from typing import Any
from assistant_agent.tools.base import BaseTool
from assistant_agent.orchestrator.models import ToolResult


class NoteWriterTool(BaseTool):
    """Mock note writer tool that generates output."""

    name = "note_writer"
    description = "Writes notes and summaries"
    sensitive = False

    async def run(self, payload: dict[str, Any]) -> ToolResult:
        goal = payload.get("goal", "")
        note = f"Summary for goal: {goal}\n\nGenerated notes based on research."
        return ToolResult(
            ok=True,
            output={"note": note},
            metadata={"tool": self.name},
        )