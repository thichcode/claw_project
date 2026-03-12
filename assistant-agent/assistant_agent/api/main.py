"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from assistant_agent.api.routes import health, tasks

app = FastAPI()

app.include_router(health)
app.include_router(tasks)
