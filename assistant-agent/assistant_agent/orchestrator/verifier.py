"""Verifier module."""

from assistant_agent.orchestrator.models import Task, VerificationResult, TaskStatus


class Verifier:
    """Verify task completion."""

    async def verify(self, task: Task) -> VerificationResult:
        """Check if task goal is achieved."""
        from assistant_agent.orchestrator.models import StepStatus
        all_steps_completed = all(
            step.status in (StepStatus.SUCCEEDED, StepStatus.SKIPPED) for step in task.steps
        )

        if not all_steps_completed:
            return VerificationResult(
                is_complete=False,
                confidence=0.0,
                reasoning="Not all steps completed",
                missing_items=["Incomplete steps remaining"],
                next_action="Continue execution",
            )

        # Simple verification: if all steps succeeded, mark complete
        outputs = [step.output for step in task.steps if step.output]
        task.final_output = outputs
        task.status = TaskStatus.COMPLETED

        return VerificationResult(
            is_complete=True,
            confidence=1.0,
            reasoning="All steps completed successfully",
            missing_items=[],
            next_action=None,
        )