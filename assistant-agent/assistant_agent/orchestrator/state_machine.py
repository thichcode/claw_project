"""Task state machine."""

from assistant_agent.orchestrator.models import TaskStatus


ALLOWED_TRANSITIONS = {
    TaskStatus.CREATED: {TaskStatus.PLANNING, TaskStatus.FAILED},
    TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.RUNNING: {
        TaskStatus.WAITING_PERMISSION,
        TaskStatus.VERIFYING,
        TaskStatus.FAILED,
    },
    TaskStatus.WAITING_PERMISSION: {TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.VERIFYING: {TaskStatus.COMPLETED, TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
}


def can_transition(current: TaskStatus, new: TaskStatus) -> bool:
    """Check if transition from current to new status is allowed."""
    return new in ALLOWED_TRANSITIONS.get(current, set())


def ensure_transition(current: TaskStatus, new: TaskStatus) -> None:
    """Raise ValueError if transition is not allowed."""
    if not can_transition(current, new):
        raise ValueError(f"Invalid transition: {current} -> {new}")