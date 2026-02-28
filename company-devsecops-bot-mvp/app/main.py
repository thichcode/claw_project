from fastapi import FastAPI

from .api import router
from .db import init_db
from .teams import router as teams_router

app = FastAPI(title="Company DevSecOps Bot MVP", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    init_db()


app.include_router(router, prefix="/api")
app.include_router(teams_router, prefix="/teams")
