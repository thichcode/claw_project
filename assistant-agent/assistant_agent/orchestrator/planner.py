"""Planner module."""

from assistant_agent.orchestrator.models import Task, PlanStep, TaskStatus
import uuid


class Planner:
    """Simple in-memory planner for MVP."""

    async def create_plan(self, goal: str) -> Task:
        """Create a task with plan steps from a goal."""
        task = Task(
            id=str(uuid.uuid4()),
            goal=goal,
            status=TaskStatus.PLANNING,
        )
        # Simple rule-based planner for MVP
        task.steps = [
            PlanStep(
                id="step-1",
                title="Understand goal",
                description=f"Analyze the goal: {goal}",
                action_type="reason",
            ),
            PlanStep(
                id="step-2",
                title="Gather context",
                description="Collect relevant information and resources",
                action_type="tool_call",
                tool_name="mock_search",
            ),
            PlanStep(
                id="step-3",
                title="Execute task",
                description="Perform the main actions to accomplish the goal",
                action_type="tool_call",
                tool_name="note_writer",
            ),
            PlanStep(
                id="step-4",
                title="Summarize results",
                description="Compile final output and results",
                action_type="respond",
            ),
        ]
        task.success_criteria = ["All steps completed", "Output generated"]
        return task