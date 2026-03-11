from .base import Tool
from .file_store import FileStoreTool
from .mock_search import MockSearchTool
from .note_writer import NoteWriterTool

TOOLS: dict[str, Tool] = {
    MockSearchTool.name: MockSearchTool(),
    NoteWriterTool.name: NoteWriterTool(),
    FileStoreTool.name: FileStoreTool(),
}


def get_tool(name: str) -> Tool:
    tool = TOOLS.get(name)
    if not tool:
        raise ValueError(f"Unknown tool: {name}")
    return tool
