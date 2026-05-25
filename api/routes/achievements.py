from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.middleware.auth import get_current_user
from models.achievement import UserAchievement
from models.user import User
from services.achievements.definitions import ACHIEVEMENTS
from services.achievements.engine import get_user_achievement_status
from services.achievements.streak import get_all_streaks
from utils.database import get_session

router = APIRouter(prefix="/api/achievements", tags=["achievements"])


@router.get("/me")
async def my_achievement_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Full achievement status: unlocked, locked, XP, level, and next-level info."""
    return await get_user_achievement_status(current_user.id, db)


@router.get("/recent")
async def recent_achievements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Last 10 achievements unlocked by the current user."""
    result = await db.execute(
        select(UserAchievement)
        .where(UserAchievement.user_id == current_user.id)
        .order_by(UserAchievement.unlocked_at.desc())
        .limit(10)
    )
    user_achievements = result.scalars().all()

    out = []
    for ua in user_achievements:
        ach = ACHIEVEMENTS.get(ua.achievement_id)
        if ach:
            out.append({**ach, "unlocked_at": ua.unlocked_at.isoformat()})

    return {"recent": out, "count": len(out)}


@router.get("/streaks")
async def my_streaks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """All active streak records for the current user."""
    streaks = await get_all_streaks(current_user.id, db)
    return {"streaks": streaks}
