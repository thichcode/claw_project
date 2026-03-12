"""Base tool interface."""

from abc import ABC, abstractmethod
from typing import Any
from assistant_agent.orchestrator.models import ToolResult


class BaseTool(ABC):
    """Abstract base class for all tools."""

    name: str
    description: str
    sensitive: bool = False

    @abstractmethod
    async def run(self, payload: dict[str, Any]) -> ToolResult:
        """Execute the tool with the given payload."""
        ...