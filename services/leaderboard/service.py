"""
Leaderboard service: XP management, global/weekly rankings, user rank queries.
"""

from datetime import datetime, timedelta
from typing import List

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.achievement import UserAchievement
from models.game import JogSession, Territory
from models.user import User
from models.workout import WorkoutSession
from services.achievements.definitions import ACHIEVEMENTS
from services.achievements.engine import calculate_level
from utils.logger import get_logger

logger = get_logger("fitai.leaderboard.service")


async def update_user_xp(user_id: int, xp_gained: int, db: AsyncSession) -> dict:
    """
    Add xp_gained to user.xp and recalculate level.
    Returns {new_xp, new_level, leveled_up}.
    """
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalars().first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    old_level = user.level or 1
    user.xp = (user.xp or 0) + xp_gained
    user.level = calculate_level(user.xp)
    db.add(user)
    await db.flush()

    return {
        "new_xp": user.xp,
        "new_level": user.level,
        "leveled_up": user.level > old_level,
    }


async def get_global_leaderboard(limit: int, db: AsyncSession) -> List[dict]:
    """
    Return top N users sorted by XP descending.
    Annotates each with total completed workouts and total territory area.
    """
    r_users = await db.execute(
        select(User).order_by(User.xp.desc()).limit(limit)
    )
    users = r_users.scalars().all()

    if not users:
        return []

    user_ids = [u.id for u in users]

    # Completed workout counts
    r_wk = await db.execute(
        select(WorkoutSession.user_id, func.count(WorkoutSession.id).label("cnt"))
        .where(WorkoutSession.user_id.in_(user_ids))
        .where(WorkoutSession.completed_at.isnot(None))
        .group_by(WorkoutSession.user_id)
    )
    workout_counts = {row[0]: row[1] for row in r_wk.all()}

    # Territory area sums
    r_terr = await db.execute(
        select(Territory.user_id, func.sum(Territory.area_km2).label("area"))
        .where(Territory.user_id.in_(user_ids))
        .group_by(Territory.user_id)
    )
    territory_areas = {row[0]: float(row[1]) for row in r_terr.all()}

    return [
        {
            "rank": i + 1,
            "user_id": u.id,
            "name": u.name,
            "xp": u.xp or 0,
            "level": u.level or 1,
            "total_workouts": workout_counts.get(u.id, 0),
            "territory_km2": round(territory_areas.get(u.id, 0.0), 3),
        }
        for i, u in enumerate(users)
    ]


async def get_weekly_leaderboard(limit: int, db: AsyncSession) -> List[dict]:
    """
    Return top N users by XP gained in the last 7 days.

    Weekly XP = achievement XP unlocked this week
              + workout session XP earned this week (max(50, calories*0.5))
              + jog session XP earned this week (int(distance_km*100)+50)
    """
    cutoff = datetime.utcnow() - timedelta(days=7)

    # Achievement XP this week
    r_ach = await db.execute(
        select(UserAchievement.user_id, UserAchievement.achievement_id)
        .where(UserAchievement.unlocked_at >= cutoff)
    )
    weekly_xp_map: dict = {}
    for user_id, ach_id in r_ach.all():
        ach = ACHIEVEMENTS.get(ach_id)
        xp = ach["xp_reward"] if ach else 0
        weekly_xp_map[user_id] = weekly_xp_map.get(user_id, 0) + xp

    # Workout XP this week
    r_wk = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.completed_at >= cutoff)
    )
    for ws in r_wk.scalars().all():
        xp = max(50, int((ws.total_calories or 0) * 0.5))
        weekly_xp_map[ws.user_id] = weekly_xp_map.get(ws.user_id, 0) + xp

    # Jog XP this week
    r_jog = await db.execute(
        select(JogSession)
        .where(JogSession.end_time >= cutoff)
        .where(JogSession.end_time.isnot(None))
    )
    for jog in r_jog.scalars().all():
        xp = int((jog.distance_km or 0) * 100) + 50
        weekly_xp_map[jog.user_id] = weekly_xp_map.get(jog.user_id, 0) + xp

    # Sort and take top N
    ranked = sorted(weekly_xp_map.items(), key=lambda kv: kv[1], reverse=True)[:limit]

    if not ranked:
        return []

    top_user_ids = [uid for uid, _ in ranked]
    r_users = await db.execute(
        select(User).where(User.id.in_(top_user_ids))
    )
    users_map = {u.id: u for u in r_users.scalars().all()}

    return [
        {
            "rank": i + 1,
            "user_id": uid,
            "name": users_map[uid].name if uid in users_map else "Unknown",
            "weekly_xp": xp,
            "total_xp": users_map[uid].xp if uid in users_map else 0,
            "level": users_map[uid].level if uid in users_map else 1,
        }
        for i, (uid, xp) in enumerate(ranked)
    ]


async def get_user_ranks(user_id: int, db: AsyncSession) -> dict:
    """
    Return the requesting user's global rank, weekly rank, XP, level, and
    top-N percentile.
    """
    r_user = await db.execute(select(User).where(User.id == user_id))
    user = r_user.scalars().first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    user_xp = user.xp or 0

    # Global rank = users with XP > this user + 1
    r_global = await db.execute(
        select(func.count(User.id)).where(User.xp > user_xp)
    )
    global_rank = (r_global.scalar_one() or 0) + 1

    # Total users for percentile
    r_total = await db.execute(select(func.count(User.id)))
    total_users = r_total.scalar_one() or 1

    percentile = round((total_users - global_rank) / total_users * 100.0, 1)

    # Weekly XP for this user
    cutoff = datetime.utcnow() - timedelta(days=7)
    r_ach = await db.execute(
        select(UserAchievement.achievement_id)
        .where(UserAchievement.user_id == user_id)
        .where(UserAchievement.unlocked_at >= cutoff)
    )
    weekly_xp = sum(
        (ACHIEVEMENTS[aid]["xp_reward"] for aid in r_ach.scalars().all() if aid in ACHIEVEMENTS),
        0,
    )
    r_wk = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.completed_at >= cutoff)
    )
    for ws in r_wk.scalars().all():
        weekly_xp += max(50, int((ws.total_calories or 0) * 0.5))
    r_jog = await db.execute(
        select(JogSession)
        .where(JogSession.user_id == user_id)
        .where(JogSession.end_time >= cutoff)
        .where(JogSession.end_time.isnot(None))
    )
    for jog in r_jog.scalars().all():
        weekly_xp += int((jog.distance_km or 0) * 100) + 50

    # Weekly rank
    weekly_board = await get_weekly_leaderboard(limit=10000, db=db)
    weekly_rank = next((e["rank"] for e in weekly_board if e["user_id"] == user_id), None)
    if weekly_rank is None:
        weekly_rank = len(weekly_board) + 1

    return {
        "user_id": user_id,
        "global_rank": global_rank,
        "weekly_rank": weekly_rank,
        "xp": user_xp,
        "level": user.level or 1,
        "weekly_xp": weekly_xp,
        "total_users": total_users,
        "percentile": percentile,
    }
