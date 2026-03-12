"""Mock search tool for MVP."""

from typing import Any
from assistant_agent.tools.base import BaseTool
from assistant_agent.orchestrator.models import ToolResult


class MockSearchTool(BaseTool):
    """Mock search tool that returns sample results."""

    name = "mock_search"
    description = "Mock search tool for testing"
    sensitive = False

    async def run(self, payload: dict[str, Any]) -> ToolResult:
        goal = payload.get("goal", "")
        return ToolResult(
            ok=True,
            output={"results": [f"Result for: {goal}", "Sample result 2", "Sample result 3"]},
            metadata={"tool": self.name},
        )