import asyncio
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import models  # noqa: F401 — registers all SQLModel table metadata
from api.routes import (
    achievements,
    chat,
    game,
    health,
    leaderboard,
    nutrition,
    user,
    workout,
)

from services.achievements.engine import check_and_award
from services.ollama.client import ollama_client
from utils.auth import verify_token
from utils.database import AsyncSessionLocal, init_db
from utils.logger import logger

scheduler = AsyncIOScheduler()


async def _daily_health_score_job() -> None:
    """APScheduler job: recalculate health scores at 23:59 for all users who logged today."""
    from datetime import date as _date
    from models.health import HealthLog
    from services.health.scorer import calculate_health_score
    from sqlmodel import select as _select

    today = _date.today()
    try:
        async with AsyncSessionLocal() as session:
            r = await session.execute(
                _select(HealthLog.user_id)
                .where(HealthLog.date == today)
                .distinct()
            )
            user_ids = r.scalars().all()
            for uid in user_ids:
                try:
                    await calculate_health_score(uid, today, session)
                except Exception as exc:
                    logger.warning(f"Health score job failed for user {uid}: {exc}")
            await session.commit()
        logger.info(f"Daily health score job completed for {len(user_ids)} users")
    except Exception as exc:
        logger.error(f"Daily health score job error: {exc}")


async def _record_app_open(user_id: int) -> None:
    """Fire app_opened achievement checks in a fresh DB session (background task)."""
    try:
        async with AsyncSessionLocal() as session:
            await check_and_award(user_id, "app_opened", {}, session)
            await session.commit()
    except Exception as exc:
        logger.warning(f"app_opened achievement check failed for user {user_id}: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FitAI backend starting up")
    await init_db()
    await ollama_client.ensure_models_pulled()
    app.state.ollama = ollama_client  # available via get_ollama dependency
    scheduler.add_job(
        _daily_health_score_job,
        CronTrigger(hour=23, minute=59),
        id="daily_health_score",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("FitAI backend ready")
    yield
    scheduler.shutdown(wait=False)
    await ollama_client.close()
    logger.info("FitAI backend shut down")


app = FastAPI(
    title="FitAI Backend",
    description="AI-powered fitness app — local Ollama edition",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def app_open_streak_middleware(request: Request, call_next):
    """
    For every authenticated request, fire a background task to update the
    app_open streak and check consistency achievements.
    """
    response = await call_next(request)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            payload = verify_token(token)
            user_id = int(payload.get("sub", 0))
            if user_id:
                asyncio.create_task(_record_app_open(user_id))
        except Exception:
            pass
    return response

app.include_router(user.router)
app.include_router(nutrition.router)
app.include_router(workout.router)
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(game.router)
app.include_router(achievements.router)
app.include_router(leaderboard.router)


@app.get("/")
async def root():
    return {"status": "ok", "version": "1.0.0", "ai": "ollama-local"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
