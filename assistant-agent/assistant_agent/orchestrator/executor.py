"""Executor module."""

from assistant_agent.orchestrator.models import Task, PlanStep, ToolResult, StepStatus, TaskStatus
from assistant_agent.orchestrator.state_machine import ensure_transition
from assistant_agent.tools.registry import ToolRegistry


class Executor:
    """Execute plan steps using tools."""

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry

    async def execute_step(self, task: Task, step: PlanStep) -> ToolResult:
        """Execute a single step."""
        if step.action_type == "reason":
            return ToolResult(ok=True, output={"note": step.description})

        if step.action_type == "respond":
            return ToolResult(ok=True, output={"response": step.expected_output})

        if step.action_type == "tool_call":
            tool = self.tool_registry.get(step.tool_name)
            if not tool:
                return ToolResult(ok=False, error=f"Tool not found: {step.tool_name}")
            return await tool.run({"goal": task.goal, "step": step.dict()})

        return ToolResult(ok=False, error=f"Unsupported action type: {step.action_type}")

    async def run_task(self, task: Task) -> Task:
        """Run all steps in a task."""
        ensure_transition(task.status, TaskStatus.RUNNING)
        task.status = TaskStatus.RUNNING

        for step in task.steps:
            step.status = StepStatus.RUNNING
            result = await self.execute_step(task, step)

            if result.ok:
                step.status = StepStatus.SUCCEEDED
                step.output = result.output
            else:
                step.status = StepStatus.FAILED
                step.error = result.error
                task.status = TaskStatus.FAILED
                return task

        task.status = TaskStatus.VERIFYING
        return task