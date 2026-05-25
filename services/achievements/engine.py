"""
Achievement engine: level calculation, condition checking, and XP awarding.
"""

import json
from datetime import date, datetime, timedelta
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.achievement import UserAchievement, UserStreak
from models.chat import ChatSession
from models.game import JogSession, Territory
from models.nutrition import FoodLog, WaterLog
from models.user import User
from models.workout import ExerciseLog, WorkoutSession
from services.achievements.definitions import ACHIEVEMENTS
from services.achievements.streak import get_streak_value, update_streak
from services.game.geo import haversine_km
from utils.logger import get_logger

logger = get_logger("fitai.achievements.engine")

# ── Level system ──────────────────────────────────────────────────────────────

LEVEL_THRESHOLDS = [
    0, 100, 250, 500, 1000, 2000, 3500, 5500,
    8000, 11000, 15000, 20000, 26000, 33000, 41000, 50000,
]


def calculate_level(xp: int) -> int:
    """Return level 1–16 based on cumulative XP thresholds."""
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i + 1
    return level


def next_level_info(xp: int) -> dict:
    """Return XP needed to reach the next level."""
    level = calculate_level(xp)
    if level >= len(LEVEL_THRESHOLDS):
        return {"next_level": level, "next_level_xp": LEVEL_THRESHOLDS[-1], "xp_to_next": 0}
    next_threshold = LEVEL_THRESHOLDS[level]  # level is 1-based, thresholds are 0-based index
    return {
        "next_level": level + 1,
        "next_level_xp": next_threshold,
        "xp_to_next": max(0, next_threshold - xp),
    }


# ── Event → Achievement mapping ───────────────────────────────────────────────

_ACHIEVEMENTS_BY_EVENT: Dict[str, List[str]] = {
    "food_logged": [
        "first_meal", "photo_foodie", "clean_eater",
        "week_logger", "nutrition_month", "protein_king",
        "macro_master", "calorie_consistent",
    ],
    "workout_completed": [
        "first_sweat", "ten_sessions", "fifty_sessions",
        "iron_week", "early_bird", "night_owl",
        "century_calories", "heavy_lifter",
        "workout_streak_7", "workout_streak_30",
        "chest_day", "leg_day_hero", "full_body",
    ],
    "territory_created": [
        "first_territory", "five_territories", "twenty_territories",
        "big_land", "landlord",
    ],
    "jog_completed": [
        "marathon_man", "explorer", "speed_demon",
        "marathon_territory", "jog_streak",
    ],
    "water_logged": ["hydration_hero"],
    "app_opened": [
        "streak_3", "streak_7", "streak_30", "streak_100",
        "comeback_kid", "goal_setter", "profile_complete",
        "leaderboard_entry", "ai_chat_10",
    ],
}


# ── DB query helpers ──────────────────────────────────────────────────────────

async def _food_log_count(user_id: int, db: AsyncSession) -> int:
    r = await db.execute(
        select(func.count(FoodLog.id)).where(FoodLog.user_id == user_id)
    )
    return r.scalar_one() or 0


async def _workout_session_count(user_id: int, db: AsyncSession) -> int:
    r = await db.execute(
        select(func.count(WorkoutSession.id))
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.completed_at.isnot(None))
    )
    return r.scalar_one() or 0


async def _territory_count(user_id: int, db: AsyncSession) -> int:
    r = await db.execute(
        select(func.count(Territory.id)).where(Territory.user_id == user_id)
    )
    return r.scalar_one() or 0


async def _total_territory_area(user_id: int, db: AsyncSession) -> float:
    r = await db.execute(
        select(func.sum(Territory.area_km2)).where(Territory.user_id == user_id)
    )
    return float(r.scalar_one() or 0.0)


async def _total_jog_distance(user_id: int, db: AsyncSession) -> float:
    r = await db.execute(
        select(func.sum(JogSession.distance_km))
        .where(JogSession.user_id == user_id)
        .where(JogSession.end_time.isnot(None))
    )
    return float(r.scalar_one() or 0.0)


# ── Individual condition checkers ─────────────────────────────────────────────

async def _check(ach_id: str, user_id: int, event_data: dict, db: AsyncSession) -> bool:
    """Dispatch to per-achievement condition check. Returns True if condition is met."""

    # ── Nutrition ──────────────────────────────────────────────────────────────
    if ach_id == "first_meal":
        return await _food_log_count(user_id, db) >= 1

    if ach_id == "clean_eater":
        return await _food_log_count(user_id, db) >= 50

    if ach_id == "photo_foodie":
        # FoodLog has no logged_via field; count total logs as proxy for photo logs.
        return await _food_log_count(user_id, db) >= 10

    if ach_id in ("week_logger", "protein_king"):
        return await get_streak_value(user_id, "nutrition", db) >= 7

    if ach_id == "nutrition_month":
        return await get_streak_value(user_id, "nutrition", db) >= 30

    if ach_id == "hydration_hero":
        r = await db.execute(
            select(func.sum(WaterLog.amount_ml))
            .where(WaterLog.user_id == user_id)
            .where(WaterLog.date == date.today())
        )
        return float(r.scalar_one() or 0.0) >= 2000.0

    if ach_id == "macro_master":
        # Check if today's calorie intake is within 10% of goal on all macros.
        r_user = await db.execute(select(User).where(User.id == user_id))
        user = r_user.scalars().first()
        if not user:
            return False
        from services.nutrition.analyzer import calculate_daily_goals
        goals = calculate_daily_goals(user)
        r_logs = await db.execute(
            select(FoodLog)
            .where(FoodLog.user_id == user_id)
            .where(FoodLog.date == date.today())
        )
        logs = r_logs.scalars().all()
        if not logs:
            return False
        cal = sum(l.calories for l in logs)
        prot = sum(l.protein_g for l in logs)
        carbs = sum(l.carbs_g for l in logs)
        fat = sum(l.fat_g for l in logs)
        def _within(actual, goal, pct=0.10):
            return goal > 0 and abs(actual - goal) / goal <= pct
        return _within(cal, goals.calories) and _within(prot, goals.protein_g) and \
               _within(carbs, goals.carbs_g) and _within(fat, goals.fat_g)

    if ach_id == "calorie_consistent":
        # Streak of 5 days within 100 cal of goal.
        r_user = await db.execute(select(User).where(User.id == user_id))
        user = r_user.scalars().first()
        if not user:
            return False
        from services.nutrition.analyzer import calculate_daily_goals
        goals = calculate_daily_goals(user)
        streak = 0
        for offset in range(5):
            d = date.today() - timedelta(days=offset)
            r = await db.execute(
                select(func.sum(FoodLog.calories))
                .where(FoodLog.user_id == user_id)
                .where(FoodLog.date == d)
            )
            day_cal = float(r.scalar_one() or 0.0)
            if day_cal > 0 and abs(day_cal - goals.calories) <= 100:
                streak += 1
            else:
                break
        return streak >= 5

    # ── Workout ────────────────────────────────────────────────────────────────
    if ach_id == "first_sweat":
        return await _workout_session_count(user_id, db) >= 1

    if ach_id == "ten_sessions":
        return await _workout_session_count(user_id, db) >= 10

    if ach_id == "fifty_sessions":
        return await _workout_session_count(user_id, db) >= 50

    if ach_id == "iron_week":
        cutoff = datetime.utcnow() - timedelta(days=7)
        r = await db.execute(
            select(func.count(WorkoutSession.id))
            .where(WorkoutSession.user_id == user_id)
            .where(WorkoutSession.completed_at >= cutoff)
        )
        return (r.scalar_one() or 0) >= 5

    if ach_id == "early_bird":
        started_at = event_data.get("started_at")
        if not started_at:
            return False
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        return started_at.hour < 8

    if ach_id == "night_owl":
        started_at = event_data.get("started_at")
        if not started_at:
            return False
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        return started_at.hour >= 21

    if ach_id == "century_calories":
        return float(event_data.get("calories", 0)) >= 500.0

    if ach_id == "heavy_lifter":
        r = await db.execute(
            select(ExerciseLog)
            .join(WorkoutSession, ExerciseLog.session_id == WorkoutSession.id)
            .where(WorkoutSession.user_id == user_id)
        )
        total_vol = sum(
            float(s.get("weight_kg") or 0) * int(s.get("reps") or 0)
            for log in r.scalars().all()
            for s in (log.sets_json or [])
        )
        return total_vol >= 10000.0

    if ach_id == "workout_streak_7":
        return await get_streak_value(user_id, "workout", db) >= 7

    if ach_id == "workout_streak_30":
        return await get_streak_value(user_id, "workout", db) >= 30

    if ach_id == "chest_day":
        r = await db.execute(
            select(ExerciseLog.session_id)
            .join(WorkoutSession, ExerciseLog.session_id == WorkoutSession.id)
            .where(WorkoutSession.user_id == user_id)
            .where(ExerciseLog.muscle_group.ilike("%chest%"))
            .distinct()
        )
        return len(r.scalars().all()) >= 10

    if ach_id == "leg_day_hero":
        leg_patterns = ["%quadricep%", "%hamstring%", "%glute%", "%leg%"]
        session_ids: set = set()
        for pat in leg_patterns:
            r = await db.execute(
                select(ExerciseLog.session_id)
                .join(WorkoutSession, ExerciseLog.session_id == WorkoutSession.id)
                .where(WorkoutSession.user_id == user_id)
                .where(ExerciseLog.muscle_group.ilike(pat))
                .distinct()
            )
            session_ids.update(r.scalars().all())
        return len(session_ids) >= 10

    if ach_id == "full_body":
        cutoff = datetime.utcnow() - timedelta(days=7)
        r = await db.execute(
            select(ExerciseLog.muscle_group)
            .join(WorkoutSession, ExerciseLog.session_id == WorkoutSession.id)
            .where(WorkoutSession.user_id == user_id)
            .where(WorkoutSession.completed_at >= cutoff)
            .distinct()
        )
        trained = {row[0].lower() for row in r.all() if row[0]}
        required = {"chest", "back", "shoulders", "biceps", "triceps",
                    "quadriceps", "hamstrings", "glutes", "core"}
        return required.issubset(trained)

    # ── Game / Territory ───────────────────────────────────────────────────────
    if ach_id == "first_territory":
        return await _territory_count(user_id, db) >= 1

    if ach_id == "five_territories":
        return await _territory_count(user_id, db) >= 5

    if ach_id == "twenty_territories":
        return await _territory_count(user_id, db) >= 20

    if ach_id == "big_land":
        return float(event_data.get("area_km2", 0)) >= 1.0

    if ach_id == "landlord":
        return await _total_territory_area(user_id, db) >= 10.0

    # ── Game / Jog ─────────────────────────────────────────────────────────────
    if ach_id == "marathon_man":
        return await _total_jog_distance(user_id, db) >= 42.0

    if ach_id == "speed_demon":
        dist = float(event_data.get("distance_km", 0))
        mins = float(event_data.get("duration_mins", 9999))
        return dist >= 5.0 and mins < 25.0

    if ach_id == "marathon_territory":
        return float(event_data.get("distance_km", 0)) >= 10.0

    if ach_id == "jog_streak":
        return await get_streak_value(user_id, "jog", db) >= 5

    if ach_id == "explorer":
        # Distinct geographic zones: 3+ jog session centroids >1 km apart.
        r = await db.execute(
            select(JogSession)
            .where(JogSession.user_id == user_id)
            .where(JogSession.end_time.isnot(None))
            .where(JogSession.gps_points_json.isnot(None))
        )
        sessions = r.scalars().all()
        centroids = []
        for s in sessions:
            pts = json.loads(s.gps_points_json or "[]")
            if not pts:
                continue
            avg_lat = sum(p["lat"] for p in pts) / len(pts)
            avg_lon = sum(p["lon"] for p in pts) / len(pts)
            centroids.append((avg_lat, avg_lon))
        distinct = []
        for c in centroids:
            if all(haversine_km(c, d) > 1.0 for d in distinct):
                distinct.append(c)
            if len(distinct) >= 3:
                return True
        return False

    # ── Consistency / App streaks ──────────────────────────────────────────────
    if ach_id == "streak_3":
        return await get_streak_value(user_id, "app_open", db) >= 3

    if ach_id == "streak_7":
        return await get_streak_value(user_id, "app_open", db) >= 7

    if ach_id == "streak_30":
        return await get_streak_value(user_id, "app_open", db) >= 30

    if ach_id == "streak_100":
        return await get_streak_value(user_id, "app_open", db) >= 100

    if ach_id == "comeback_kid":
        # True if last activity was >7 days ago (checked BEFORE today's streak update).
        last_date = event_data.get("_last_app_open_date")
        if not last_date:
            return False
        if isinstance(last_date, str):
            last_date = date.fromisoformat(last_date)
        return (date.today() - last_date).days > 7

    if ach_id == "goal_setter":
        r = await db.execute(select(User).where(User.id == user_id))
        user = r.scalars().first()
        return bool(user and user.goal)

    if ach_id == "profile_complete":
        r = await db.execute(select(User).where(User.id == user_id))
        user = r.scalars().first()
        return bool(
            user and user.name and user.age and user.weight_kg
            and user.height_cm and user.goal and user.activity_level
        )

    if ach_id == "leaderboard_entry":
        # User is on the leaderboard if they have at least 1 completed workout or jog.
        sessions = await _workout_session_count(user_id, db)
        jogs = await _territory_count(user_id, db)
        return (sessions + jogs) >= 1

    if ach_id == "ai_chat_10":
        r = await db.execute(
            select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
        )
        return (r.scalar_one() or 0) >= 10

    # Stub achievements (require complex cross-session analytics or manual triggers)
    # meal_planner, recovery_pro, first_encounter, week_complete, monthly_warrior,
    # top_100, top_10, territory_champ, perfectionist
    return False


# ── Core public functions ─────────────────────────────────────────────────────

async def check_and_award(
    user_id: int,
    event_type: str,
    event_data: dict,
    db: AsyncSession,
) -> List[dict]:
    """
    Check all achievements relevant to event_type, award any that are newly met,
    and add their XP to the user.

    For 'app_opened': also updates the app_open streak and injects comeback_kid context.
    For 'food_logged', 'workout_completed', 'jog_completed': updates the relevant streak.

    Returns a list of newly awarded achievement dicts (empty if none).
    """
    # Fetch already-unlocked IDs once to avoid repeated queries in the loop.
    r = await db.execute(
        select(UserAchievement.achievement_id)
        .where(UserAchievement.user_id == user_id)
    )
    already_unlocked: set = set(r.scalars().all())

    # Update streaks and inject relevant context into event_data copy.
    data = dict(event_data)

    if event_type == "app_opened":
        # Capture last activity date BEFORE updating the streak (for comeback_kid).
        r2 = await db.execute(
            select(UserStreak)
            .where(UserStreak.user_id == user_id)
            .where(UserStreak.activity_type == "app_open")
        )
        existing = r2.scalars().first()
        if existing and existing.last_activity_date:
            data["_last_app_open_date"] = existing.last_activity_date.isoformat()
        await update_streak(user_id, "app_open", db)

    elif event_type == "food_logged":
        await update_streak(user_id, "nutrition", db)

    elif event_type == "workout_completed":
        await update_streak(user_id, "workout", db)

    elif event_type == "jog_completed":
        await update_streak(user_id, "jog", db)

    ach_ids_to_check = _ACHIEVEMENTS_BY_EVENT.get(event_type, [])
    newly_awarded: List[dict] = []

    for ach_id in ach_ids_to_check:
        if ach_id in already_unlocked:
            continue
        ach = ACHIEVEMENTS.get(ach_id)
        if not ach:
            continue

        try:
            met = await _check(ach_id, user_id, data, db)
        except Exception as exc:
            logger.warning(f"Achievement check failed for {ach_id}: {exc}")
            met = False

        if not met:
            continue

        # Award the achievement
        ua = UserAchievement(user_id=user_id, achievement_id=ach_id)
        db.add(ua)

        # Add XP and recalculate level using identity-map User object
        r_user = await db.execute(select(User).where(User.id == user_id))
        user = r_user.scalars().first()
        if user:
            user.xp = (user.xp or 0) + ach["xp_reward"]
            user.level = calculate_level(user.xp)
            db.add(user)

        await db.flush()
        await db.refresh(ua)

        already_unlocked.add(ach_id)  # prevent double-award in same call
        newly_awarded.append({
            **ach,
            "unlocked_at": ua.unlocked_at.isoformat(),
        })
        logger.info(f"User {user_id} unlocked achievement '{ach_id}' (+{ach['xp_reward']} XP)")

    return newly_awarded


async def get_user_achievement_status(user_id: int, db: AsyncSession) -> dict:
    """
    Return full achievement status: unlocked list, locked list with progress,
    total XP from achievements, level, and next-level info.
    """
    r = await db.execute(
        select(UserAchievement)
        .where(UserAchievement.user_id == user_id)
        .order_by(UserAchievement.unlocked_at.desc())
    )
    user_achievements = r.scalars().all()
    unlocked_map = {ua.achievement_id: ua for ua in user_achievements}

    # Fetch user for XP/level
    r_user = await db.execute(select(User).where(User.id == user_id))
    user = r_user.scalars().first()
    total_xp = user.xp if user else 0
    level = user.level if user else 1

    # Build unlocked list
    unlocked = []
    for ach_id, ua in unlocked_map.items():
        ach = ACHIEVEMENTS.get(ach_id)
        if ach:
            unlocked.append({**ach, "unlocked_at": ua.unlocked_at.isoformat()})

    # Build locked list with simple progress estimates
    locked = []
    for ach_id, ach in ACHIEVEMENTS.items():
        if ach_id in unlocked_map:
            continue
        locked.append({
            **ach,
            "unlocked_at": None,
        })

    lvl_info = next_level_info(total_xp)
    return {
        "unlocked": unlocked,
        "locked": locked,
        "unlocked_count": len(unlocked),
        "total_achievements": len(ACHIEVEMENTS),
        "total_xp": total_xp,
        "level": level,
        "next_level": lvl_info["next_level"],
        "next_level_xp": lvl_info["next_level_xp"],
        "xp_to_next_level": lvl_info["xp_to_next"],
    }
