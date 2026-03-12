"""Tool registry."""

from typing import Any
from assistant_agent.tools.base import BaseTool
from assistant_agent.tools.mock_search import MockSearchTool
from assistant_agent.tools.note_writer import NoteWriterTool


class ToolRegistry:
    """Registry for available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {
            "mock_search": MockSearchTool(),
            "note_writer": NoteWriterTool(),
        }

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """List all available tools."""
        return list(self._tools.values())