"""
Health score calculation and trend analysis.
"""

from datetime import date, datetime, timedelta
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.health import HealthLog, HealthScore
from models.nutrition import FoodLog, WaterLog
from models.user import User
from models.workout import WorkoutSession
from services.achievements.streak import get_streak_value
from services.nutrition.analyzer import calculate_daily_goals
from utils.logger import get_logger

logger = get_logger("fitai.health.scorer")


class HealthScoreBreakdown(BaseModel):
    nutrition_score: float    # 0–25
    workout_score: float      # 0–20
    sleep_score: float        # 0–20
    hydration_score: float    # 0–15
    mood_energy_score: float  # 0–10
    streak_bonus: float       # 0–10
    total: float              # 0–100
    grade: str                # A / B / C / D / F
    insight: str              # one-sentence takeaway


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _grade(total: float) -> str:
    if total >= 90:
        return "A"
    if total >= 80:
        return "B"
    if total >= 70:
        return "C"
    if total >= 60:
        return "D"
    return "F"


def _insight(
    nutrition: float,
    workout: float,
    sleep: float,
    hydration: float,
    mood_energy: float,
) -> str:
    """Return a one-sentence insight targeting the weakest component."""
    scores = {
        "nutrition": nutrition / 25,
        "workout": workout / 20,
        "sleep": sleep / 20,
        "hydration": hydration / 15,
        "mood_energy": mood_energy / 10,
    }
    weakest = min(scores, key=lambda k: scores[k])
    insights = {
        "nutrition": "Log your meals and try to hit your calorie and macro targets to fuel your progress.",
        "workout": "Adding a workout today would give your health score a big boost.",
        "sleep": "Aim for 7–9 hours of quality sleep — it's the single most powerful recovery tool.",
        "hydration": "You need to drink more water; try to hit your daily hydration goal.",
        "mood_energy": "Take time to manage stress and rest — your mood and energy drive long-term consistency.",
    }
    return insights[weakest]


# ── Main score calculator ──────────────────────────────────────────────────────

async def calculate_health_score(
    user_id: int,
    date_obj: date,
    db: AsyncSession,
) -> dict:
    """
    Calculate (and persist) the HealthScore for user_id on date_obj.
    Returns {score: HealthScoreBreakdown dict, date: str}.
    """
    # Fetch user
    r_user = await db.execute(select(User).where(User.id == user_id))
    user = r_user.scalars().first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    goals = calculate_daily_goals(user)

    # ── Nutrition score ────────────────────────────────────────────────────────
    r_food = await db.execute(
        select(FoodLog)
        .where(FoodLog.user_id == user_id)
        .where(FoodLog.date == date_obj)
    )
    food_logs = r_food.scalars().all()

    if food_logs:
        actual_cal = sum(l.calories for l in food_logs)
        actual_prot = sum(l.protein_g for l in food_logs)
        actual_carbs = sum(l.carbs_g for l in food_logs)
        actual_fat = sum(l.fat_g for l in food_logs)

        cal_adh = _clamp(1.0 - abs(actual_cal - goals.calories) / max(goals.calories, 1), 0, 1)

        def _macro_pct(actual, goal):
            return _clamp(actual / max(goal, 1), 0, 1)

        macro_adh = (
            _macro_pct(actual_prot, goals.protein_g)
            + _macro_pct(actual_carbs, goals.carbs_g)
            + _macro_pct(actual_fat, goals.fat_g)
        ) / 3.0

        nutrition_score = _clamp((cal_adh * 0.6 + macro_adh * 0.4) * 25, 0, 25)
    else:
        nutrition_score = 0.0

    # ── Workout score ──────────────────────────────────────────────────────────
    today_start = datetime.combine(date_obj, datetime.min.time())
    today_end = datetime.combine(date_obj, datetime.max.time())

    r_ws_today = await db.execute(
        select(func.count(WorkoutSession.id))
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.completed_at >= today_start)
        .where(WorkoutSession.completed_at <= today_end)
    )
    worked_out_today = (r_ws_today.scalar_one() or 0) > 0

    if worked_out_today:
        workout_score = 20.0
    else:
        week_start = datetime.combine(date_obj - timedelta(days=6), datetime.min.time())
        r_week = await db.execute(
            select(func.count(WorkoutSession.id))
            .where(WorkoutSession.user_id == user_id)
            .where(WorkoutSession.completed_at >= week_start)
            .where(WorkoutSession.completed_at.isnot(None))
        )
        sessions_this_week = r_week.scalar_one() or 0
        workout_score = _clamp((sessions_this_week / 4.0) * 20.0, 0, 20)

    # ── Sleep score ────────────────────────────────────────────────────────────
    r_hlog = await db.execute(
        select(HealthLog)
        .where(HealthLog.user_id == user_id)
        .where(HealthLog.date == date_obj)
    )
    health_log = r_hlog.scalars().first()

    if health_log:
        hours_score = _clamp(health_log.sleep_hours / 8.0, 0, 1) * 10.0
        quality_score = (health_log.sleep_quality / 5.0) * 10.0
        sleep_score = _clamp(hours_score + quality_score, 0, 20)
    else:
        sleep_score = 10.0  # neutral when no data

    # ── Hydration score ────────────────────────────────────────────────────────
    r_water = await db.execute(
        select(func.sum(WaterLog.amount_ml))
        .where(WaterLog.user_id == user_id)
        .where(WaterLog.date == date_obj)
    )
    total_water = float(r_water.scalar_one() or 0.0)

    if total_water > 0:
        hydration_score = _clamp((total_water / max(goals.water_ml, 1)) * 15.0, 0, 15)
    else:
        hydration_score = 7.0  # neutral when no data

    # ── Mood / Energy score ────────────────────────────────────────────────────
    if health_log:
        mood_energy_score = _clamp(((health_log.mood + health_log.energy) / 10.0) * 10.0, 0, 10)
    else:
        mood_energy_score = 5.0  # neutral when no data

    # ── Streak bonus ───────────────────────────────────────────────────────────
    app_streak = await get_streak_value(user_id, "app_open", db)
    streak_bonus = _clamp((app_streak / 30.0) * 10.0, 0, 10)

    # ── Totals ─────────────────────────────────────────────────────────────────
    total = round(
        nutrition_score + workout_score + sleep_score
        + hydration_score + mood_energy_score + streak_bonus,
        1,
    )
    grade = _grade(total)
    insight = _insight(nutrition_score, workout_score, sleep_score, hydration_score, mood_energy_score)

    breakdown = HealthScoreBreakdown(
        nutrition_score=round(nutrition_score, 1),
        workout_score=round(workout_score, 1),
        sleep_score=round(sleep_score, 1),
        hydration_score=round(hydration_score, 1),
        mood_energy_score=round(mood_energy_score, 1),
        streak_bonus=round(streak_bonus, 1),
        total=total,
        grade=grade,
        insight=insight,
    )

    # ── Upsert HealthScore ─────────────────────────────────────────────────────
    r_hs = await db.execute(
        select(HealthScore)
        .where(HealthScore.user_id == user_id)
        .where(HealthScore.date == date_obj)
    )
    score_record = r_hs.scalars().first()

    if score_record is None:
        score_record = HealthScore(user_id=user_id, date=date_obj)
        db.add(score_record)

    score_record.nutrition_score = breakdown.nutrition_score
    score_record.workout_score = breakdown.workout_score
    score_record.sleep_score = breakdown.sleep_score
    score_record.hydration_score = breakdown.hydration_score
    score_record.mood_energy_score = breakdown.mood_energy_score
    score_record.streak_bonus = breakdown.streak_bonus
    score_record.total = breakdown.total
    score_record.grade = breakdown.grade
    score_record.insight = breakdown.insight
    score_record.updated_at = datetime.utcnow()
    db.add(score_record)
    await db.flush()

    return {"score": breakdown.model_dump(), "date": date_obj.isoformat()}


# ── Trend analysis ─────────────────────────────────────────────────────────────

async def get_health_trend(user_id: int, days: int, db: AsyncSession) -> dict:
    """
    Return health score trend data over the last N days.
    Pulls from the persisted HealthScore table.
    """
    cutoff = date.today() - timedelta(days=days - 1)

    r = await db.execute(
        select(HealthScore)
        .where(HealthScore.user_id == user_id)
        .where(HealthScore.date >= cutoff)
        .order_by(HealthScore.date)
    )
    scores = r.scalars().all()

    if not scores:
        return {
            "daily_scores": [],
            "weekly_averages": [],
            "trend": "stable",
            "best_day": None,
            "worst_day": None,
            "avg_score": 0.0,
        }

    daily = [
        {"date": s.date.isoformat(), "total": s.total, "grade": s.grade}
        for s in scores
    ]

    totals = [s.total for s in scores]
    avg_score = round(sum(totals) / len(totals), 1)
    best = max(scores, key=lambda s: s.total)
    worst = min(scores, key=lambda s: s.total)

    # ── Weekly averages ────────────────────────────────────────────────────────
    weekly: dict = {}
    for s in scores:
        iso_week = s.date.isocalendar()
        key = f"{iso_week[0]}-W{iso_week[1]:02d}"
        weekly.setdefault(key, []).append(s.total)

    weekly_averages = [
        {"week": wk, "avg_score": round(sum(vs) / len(vs), 1)}
        for wk, vs in sorted(weekly.items())
    ]

    # ── Trend direction ────────────────────────────────────────────────────────
    trend = "stable"
    if len(weekly_averages) >= 2:
        last_avg = weekly_averages[-1]["avg_score"]
        prev_avg = weekly_averages[-2]["avg_score"]
        if last_avg > prev_avg + 5:
            trend = "improving"
        elif last_avg < prev_avg - 5:
            trend = "declining"

    return {
        "daily_scores": daily,
        "weekly_averages": weekly_averages,
        "trend": trend,
        "best_day": {"date": best.date.isoformat(), "score": best.total},
        "worst_day": {"date": worst.date.isoformat(), "score": worst.total},
        "avg_score": avg_score,
    }
