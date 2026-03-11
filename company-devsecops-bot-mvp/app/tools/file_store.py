from pathlib import Path

from .base import Tool


class FileStoreTool(Tool):
    name = "file_store"

    async def execute(self, payload: dict) -> dict:
        ctx = payload.get("context", {})
        task_id = ctx.get("task_id", "unknown-task")
        filename = payload.get("filename", "output.txt")
        out_dir = Path("./data/task_outputs")
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{task_id}_{filename}"
        output_path.write_text(f"Draft artifact for task {task_id}\n", encoding="utf-8")
        return {"ok": True, "path": str(output_path), "message": "Artifact saved"}
