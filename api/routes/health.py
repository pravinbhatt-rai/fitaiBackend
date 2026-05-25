from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.dependencies import get_ollama
from api.middleware.auth import get_current_user
from models.health import HealthLog, HealthScore
from models.nutrition import FoodLog, WaterLog
from models.user import User
from models.workout import WorkoutSession
from services.achievements.streak import get_all_streaks
from services.health.routine_generator import generate_daily_routine, generate_health_insights
from services.health.scorer import calculate_health_score, get_health_trend
from services.nutrition.analyzer import calculate_daily_goals
from services.ollama.client import OllamaClient
from utils.database import get_session
from utils.logger import get_logger

router = APIRouter(prefix="/api/health", tags=["health"])
logger = get_logger("fitai.routes.health")


# ── Request schemas ───────────────────────────────────────────────────────────

class HealthLogRequest(BaseModel):
    sleep_hours: float
    sleep_quality: int    # 1–5
    mood: int             # 1–5
    energy: int           # 1–5
    hydration_ml: int
    resting_hr: Optional[int] = None
    stress_level: int     # 1–5
    notes: Optional[str] = None


class WaterLogRequest(BaseModel):
    amount_ml: int


# ── Background helper ─────────────────────────────────────────────────────────

async def _recalculate_score_bg(user_id: int, date_obj: date) -> None:
    from utils.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            await calculate_health_score(user_id, date_obj, session)
            await session.commit()
    except Exception as exc:
        logger.warning(f"Background health score recalc failed for user {user_id}: {exc}")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/log", status_code=status.HTTP_201_CREATED)
async def log_health(
    req: HealthLogRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Upsert today's health log, then trigger a score recalculation in the background."""
    today = date.today()

    result = await db.execute(
        select(HealthLog)
        .where(HealthLog.user_id == current_user.id)
        .where(HealthLog.date == today)
    )
    health_log = result.scalars().first()

    if health_log is None:
        health_log = HealthLog(user_id=current_user.id, date=today)
        db.add(health_log)

    health_log.sleep_hours = req.sleep_hours
    health_log.sleep_quality = req.sleep_quality
    health_log.mood = req.mood
    health_log.energy = req.energy
    health_log.hydration_ml = req.hydration_ml
    health_log.resting_hr = req.resting_hr
    health_log.stress_level = req.stress_level
    health_log.notes = req.notes
    db.add(health_log)
    await db.flush()
    await db.refresh(health_log)

    background_tasks.add_task(_recalculate_score_bg, current_user.id, today)

    return {
        "id": health_log.id,
        "date": health_log.date.isoformat(),
        "sleep_hours": health_log.sleep_hours,
        "sleep_quality": health_log.sleep_quality,
        "mood": health_log.mood,
        "energy": health_log.energy,
        "hydration_ml": health_log.hydration_ml,
        "resting_hr": health_log.resting_hr,
        "stress_level": health_log.stress_level,
        "notes": health_log.notes,
        "created_at": health_log.created_at.isoformat(),
    }


@router.get("/log/today")
async def get_today_log(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return today's health log or null."""
    today = date.today()
    result = await db.execute(
        select(HealthLog)
        .where(HealthLog.user_id == current_user.id)
        .where(HealthLog.date == today)
    )
    log = result.scalars().first()
    if not log:
        return None

    return {
        "id": log.id,
        "date": log.date.isoformat(),
        "sleep_hours": log.sleep_hours,
        "sleep_quality": log.sleep_quality,
        "mood": log.mood,
        "energy": log.energy,
        "hydration_ml": log.hydration_ml,
        "resting_hr": log.resting_hr,
        "stress_level": log.stress_level,
        "notes": log.notes,
        "created_at": log.created_at.isoformat(),
    }


@router.get("/log/history")
async def health_log_history(
    days: int = Query(14, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return the last N days of health log entries."""
    cutoff = date.today() - timedelta(days=days - 1)
    result = await db.execute(
        select(HealthLog)
        .where(HealthLog.user_id == current_user.id)
        .where(HealthLog.date >= cutoff)
        .order_by(HealthLog.date.desc())
    )
    logs = result.scalars().all()

    return [
        {
            "id": l.id,
            "date": l.date.isoformat(),
            "sleep_hours": l.sleep_hours,
            "sleep_quality": l.sleep_quality,
            "mood": l.mood,
            "energy": l.energy,
            "hydration_ml": l.hydration_ml,
            "resting_hr": l.resting_hr,
            "stress_level": l.stress_level,
            "notes": l.notes,
        }
        for l in logs
    ]


@router.get("/score/today")
async def health_score_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Calculate and return today's health score breakdown."""
    result = await calculate_health_score(current_user.id, date.today(), db)
    return result


@router.get("/score/trend")
async def health_score_trend(
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return health score trend data over the last N days."""
    return await get_health_trend(current_user.id, days, db)


@router.get("/routine/today")
async def get_today_routine(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    ollama: OllamaClient = Depends(get_ollama),
):
    """Generate a personalised daily routine using today's health score."""
    today = date.today()

    # Fetch today's health score if available
    r_score = await db.execute(
        select(HealthScore)
        .where(HealthScore.user_id == current_user.id)
        .where(HealthScore.date == today)
    )
    score_record = r_score.scalars().first()
    health_score = score_record.total if score_record else None

    # Check if any workout was completed today
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    r_ws = await db.execute(
        select(func.count(WorkoutSession.id))
        .where(WorkoutSession.user_id == current_user.id)
        .where(WorkoutSession.completed_at >= today_start)
        .where(WorkoutSession.completed_at <= today_end)
    )
    has_workout_today = (r_ws.scalar_one() or 0) > 0

    routine = await generate_daily_routine(
        user=current_user,
        health_score=health_score,
        has_workout_today=has_workout_today,
        ollama=ollama,
    )
    return routine.model_dump()


@router.post("/water", status_code=status.HTTP_201_CREATED)
async def log_water(
    req: WaterLogRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Log a water intake entry and return today's running total."""
    today = date.today()
    entry = WaterLog(user_id=current_user.id, date=today, amount_ml=float(req.amount_ml))
    db.add(entry)
    await db.flush()

    r = await db.execute(
        select(func.sum(WaterLog.amount_ml))
        .where(WaterLog.user_id == current_user.id)
        .where(WaterLog.date == today)
    )
    total_ml = float(r.scalar_one() or 0.0)
    goals = calculate_daily_goals(current_user)
    pct = round(min(total_ml / max(goals.water_ml, 1) * 100.0, 100.0), 1)

    return {
        "total_today_ml": int(total_ml),
        "goal_ml": int(goals.water_ml),
        "pct": pct,
    }


@router.get("/water/today")
async def get_water_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return today's water logs with totals and an hourly breakdown."""
    today = date.today()
    result = await db.execute(
        select(WaterLog)
        .where(WaterLog.user_id == current_user.id)
        .where(WaterLog.date == today)
        .order_by(WaterLog.logged_at)
    )
    logs = result.scalars().all()
    total_ml = sum(w.amount_ml for w in logs)
    goals = calculate_daily_goals(current_user)

    hourly: dict = {}
    for w in logs:
        key = f"{w.logged_at.hour:02d}:00"
        hourly[key] = hourly.get(key, 0.0) + w.amount_ml

    return {
        "total_ml": int(total_ml),
        "goal_ml": int(goals.water_ml),
        "logs": [
            {"amount_ml": int(w.amount_ml), "logged_at": w.logged_at.isoformat()}
            for w in logs
        ],
        "hourly_breakdown": {k: int(v) for k, v in sorted(hourly.items())},
    }


@router.get("/insights")
async def health_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    ollama: OllamaClient = Depends(get_ollama),
):
    """Generate 5 AI-powered health insights based on the last 7 days of data."""
    cutoff = date.today() - timedelta(days=6)

    # Health logs
    r_hl = await db.execute(
        select(HealthLog)
        .where(HealthLog.user_id == current_user.id)
        .where(HealthLog.date >= cutoff)
        .order_by(HealthLog.date)
    )
    health_logs = r_hl.scalars().all()

    # Nutrition summary
    r_food = await db.execute(
        select(FoodLog)
        .where(FoodLog.user_id == current_user.id)
        .where(FoodLog.date >= cutoff)
    )
    food_logs = r_food.scalars().all()
    goals = calculate_daily_goals(current_user)
    nutrition_data = {
        "daily_goal_calories": goals.calories,
        "days_logged": len({l.date for l in food_logs}),
        "avg_daily_calories": round(
            sum(l.calories for l in food_logs) / max(len({l.date for l in food_logs}), 1), 1
        ),
        "total_protein_g": round(sum(l.protein_g for l in food_logs), 1),
    }

    # Workout summary
    r_ws = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .where(WorkoutSession.completed_at >= datetime.combine(cutoff, datetime.min.time()))
        .where(WorkoutSession.completed_at.isnot(None))
    )
    wk_sessions = r_ws.scalars().all()
    workout_data = {
        "sessions_this_week": len(wk_sessions),
        "total_calories_burned": round(sum(w.total_calories or 0 for w in wk_sessions), 1),
        "avg_duration_mins": round(
            sum(w.total_duration_mins or 0 for w in wk_sessions) / max(len(wk_sessions), 1), 1
        ),
    }

    insights = await generate_health_insights(
        current_user.id, list(health_logs), nutrition_data, workout_data, ollama
    )
    return {"insights": insights, "generated_at": datetime.utcnow().isoformat()}


@router.get("/summary")
async def health_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Single dashboard endpoint: today's log, score, active streaks, and water."""
    today = date.today()

    # Today's health log
    r_log = await db.execute(
        select(HealthLog)
        .where(HealthLog.user_id == current_user.id)
        .where(HealthLog.date == today)
    )
    log = r_log.scalars().first()
    today_log = None
    if log:
        today_log = {
            "sleep_hours": log.sleep_hours,
            "sleep_quality": log.sleep_quality,
            "mood": log.mood,
            "energy": log.energy,
            "stress_level": log.stress_level,
        }

    # Today's health score
    r_score = await db.execute(
        select(HealthScore)
        .where(HealthScore.user_id == current_user.id)
        .where(HealthScore.date == today)
    )
    score_record = r_score.scalars().first()
    today_score = None
    if score_record:
        today_score = {
            "total": score_record.total,
            "grade": score_record.grade,
            "insight": score_record.insight,
        }

    # Active streaks
    streaks = await get_all_streaks(current_user.id, db)

    # Water today
    r_water = await db.execute(
        select(func.sum(WaterLog.amount_ml))
        .where(WaterLog.user_id == current_user.id)
        .where(WaterLog.date == today)
    )
    total_water = int(r_water.scalar_one() or 0)
    goals = calculate_daily_goals(current_user)

    return {
        "today_log": today_log,
        "today_score": today_score,
        "active_streaks": streaks,
        "water_today": {
            "total_ml": total_water,
            "goal_ml": int(goals.water_ml),
            "pct": round(min(total_water / max(goals.water_ml, 1) * 100, 100), 1),
        },
        "user": {
            "name": current_user.name,
            "level": current_user.level,
            "xp": current_user.xp,
        },
    }
