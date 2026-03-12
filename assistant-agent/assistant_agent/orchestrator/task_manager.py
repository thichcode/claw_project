"""Task manager - orchestrates the full agent loop."""

from assistant_agent.orchestrator.models import Task, TaskStatus
from assistant_agent.orchestrator.planner import Planner
from assistant_agent.orchestrator.executor import Executor
from assistant_agent.orchestrator.verifier import Verifier
from assistant_agent.orchestrator.state_machine import ensure_transition


class TaskManager:
    """Manages the full task lifecycle."""

    def __init__(self, planner: Planner, executor: Executor, verifier: Verifier):
        self.planner = planner
        self.executor = executor
        self.verifier = verifier

    async def create_task(self, goal: str) -> Task:
        """Create a new task with a plan."""
        task = await self.planner.create_plan(goal)
        ensure_transition(TaskStatus.CREATED, task.status)
        task.status = TaskStatus.CREATED
        return task

    async def run_task(self, task: Task) -> Task:
        """Execute and verify a task."""
        # Transition to PLANNING first
        ensure_transition(task.status, TaskStatus.PLANNING)
        task.status = TaskStatus.PLANNING
        
        # Run all steps
        task = await self.executor.run_task(task)

        # Verify completion
        if task.status == TaskStatus.VERIFYING:
            verification = await self.verifier.verify(task)
            if verification.is_complete:
                task.status = TaskStatus.COMPLETED
            else:
                task.status = TaskStatus.FAILED

        return task