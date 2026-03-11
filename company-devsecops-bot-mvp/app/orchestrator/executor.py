from .models import TaskStep
from ..tools.registry import get_tool


async def execute_step(step: TaskStep, context: dict) -> TaskStep:
    tool = get_tool(step.tool_name)
    payload = dict(step.tool_input)
    payload["context"] = context
    res = await tool.execute(payload)
    if res.get("ok", True):
        step.status = "completed"
        step.output = res
        return step

    step.status = "failed"
    step.error = res.get("message", "Step execution failed")
    step.output = res
    return step
