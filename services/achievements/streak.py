"""
Streak tracking: maintain per-user, per-activity consecutive-day counters.
"""

from datetime import date, timedelta
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.achievement import UserStreak
from utils.logger import get_logger

logger = get_logger("fitai.achievements.streak")


async def update_streak(user_id: int, activity_type: str, db: AsyncSession) -> dict:
    """
    Increment (or reset) the streak for user_id + activity_type based on today's date.

    Rules:
      - last_activity == today    → no change (idempotent)
      - last_activity == yesterday → increment
      - gap > 1 day or no record  → reset to 1
    Longest streak is updated when current exceeds it.

    Returns: {activity_type, current_streak, longest_streak, updated: bool}
    """
    today = date.today()

    result = await db.execute(
        select(UserStreak)
        .where(UserStreak.user_id == user_id)
        .where(UserStreak.activity_type == activity_type)
    )
    streak = result.scalars().first()

    if streak is None:
        streak = UserStreak(
            user_id=user_id,
            activity_type=activity_type,
            current_streak=1,
            longest_streak=1,
            last_activity_date=today,
        )
        db.add(streak)
        await db.flush()
        await db.refresh(streak)
        return {
            "activity_type": activity_type,
            "current_streak": 1,
            "longest_streak": 1,
            "updated": True,
        }

    # Already recorded today — idempotent
    if streak.last_activity_date == today:
        return {
            "activity_type": activity_type,
            "current_streak": streak.current_streak,
            "longest_streak": streak.longest_streak,
            "updated": False,
        }

    yesterday = today - timedelta(days=1)
    if streak.last_activity_date == yesterday:
        streak.current_streak += 1
    else:
        streak.current_streak = 1  # gap: reset

    if streak.current_streak > streak.longest_streak:
        streak.longest_streak = streak.current_streak

    streak.last_activity_date = today
    db.add(streak)
    await db.flush()
    await db.refresh(streak)

    return {
        "activity_type": activity_type,
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak,
        "updated": True,
    }


async def get_streak_value(user_id: int, activity_type: str, db: AsyncSession) -> int:
    """Return the current streak value for a user+activity (0 if no record)."""
    result = await db.execute(
        select(UserStreak)
        .where(UserStreak.user_id == user_id)
        .where(UserStreak.activity_type == activity_type)
    )
    streak = result.scalars().first()
    return streak.current_streak if streak else 0


async def get_all_streaks(user_id: int, db: AsyncSession) -> Dict[str, dict]:
    """
    Return all streak records for a user, keyed by activity_type.
    """
    result = await db.execute(
        select(UserStreak).where(UserStreak.user_id == user_id)
    )
    streaks = result.scalars().all()

    return {
        s.activity_type: {
            "activity_type": s.activity_type,
            "current_streak": s.current_streak,
            "longest_streak": s.longest_streak,
            "last_activity_date": s.last_activity_date.isoformat() if s.last_activity_date else None,
        }
        for s in streaks
    }
