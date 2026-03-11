from .base import Tool


class MockSearchTool(Tool):
    name = "mock_search"

    async def execute(self, payload: dict) -> dict:
        query = payload.get("query", "")
        limit = int(payload.get("limit", 5))
        items = [
            {"title": f"Source {idx} for {query}", "url": f"https://example.com/{idx}"}
            for idx in range(1, limit + 1)
        ]
        return {"ok": True, "items": items, "message": f"Collected {len(items)} sources"}
