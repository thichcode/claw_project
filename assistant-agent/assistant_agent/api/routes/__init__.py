"""API routes package."""

from .health import router as health_router
from .tasks import router as tasks_router

health = health_router
tasks = tasks_router
__all__ = ["health", "tasks"]
