from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from api.middleware.logging import RequestLoggingMiddleware
from api.routes import health, ai, workouts, nutrition, auth
from models import register_model
from inference.workout_model import WorkoutRecommender
from inference.nutrition_model import NutritionAnalyzer
from utils.config import get_settings
from utils.gpu import detect_device
from utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup.begin", env=settings.APP_ENV)

    device = detect_device(settings.DEVICE)

    workout_model = WorkoutRecommender(device)
    workout_weights = Path(settings.MODEL_PATH) / "workout_recommender.pt"
    workout_model.load(workout_weights if workout_weights.exists() else None)
    register_model("workout", workout_model)

    nutrition_model = NutritionAnalyzer(device)
    nutrition_weights = Path(settings.MODEL_PATH) / "nutrition_analyzer.pt"
    nutrition_model.load(nutrition_weights if nutrition_weights.exists() else None)
    register_model("nutrition", nutrition_model)

    logger.info("startup.complete", device=str(device))
    yield

    logger.info("shutdown.begin")


app = FastAPI(
    title="FitAI Backend",
    description="AI-powered fitness & nutrition API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
)

# ── Middleware ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

# ── Prometheus metrics ──────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(auth.router, prefix="/v1")
app.include_router(ai.router, prefix="/v1")
app.include_router(workouts.router, prefix="/v1")
app.include_router(nutrition.router, prefix="/v1")


# ── Global error handler ────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error"},
    )
