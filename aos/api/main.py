"""AOS FastAPI application — main entry point.

The app factory pattern is used so that tests can create isolated instances
without starting the global engine or running migrations.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from aos.api.routers import approvals, events, runs, tasks, workers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: run startup checks, then yield, then teardown."""
    # Phase 1: migrations are run externally (``alembic upgrade head`` in
    # docker-compose or CI). The lifespan performs only a connectivity check.
    from aos.db.engine import engine
    async with engine.connect() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Construct and configure the AOS FastAPI application."""
    app = FastAPI(
        title="AOS — Autonomous Engineering System",
        version="0.1.0",
        description="Phase 1: FastAPI + PostgreSQL + Workflow Controller",
        lifespan=lifespan,
    )

    app.include_router(tasks.router)
    app.include_router(runs.router)
    app.include_router(events.router)
    app.include_router(approvals.router)
    app.include_router(workers.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
