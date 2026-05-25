from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import get_current_user
from models.user import User
from services.leaderboard.service import (
    get_global_leaderboard,
    get_user_ranks,
    get_weekly_leaderboard,
)
from utils.database import get_session

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("/global")
async def global_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Top N users by all-time XP."""
    board = await get_global_leaderboard(limit, db)
    return {"leaderboard": board, "count": len(board)}


@router.get("/weekly")
async def weekly_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Top N users by XP earned in the last 7 days."""
    board = await get_weekly_leaderboard(limit, db)
    return {"leaderboard": board, "count": len(board)}


@router.get("/me/rank")
async def my_rank(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Global rank, weekly rank, percentile, and XP info for the current user."""
    return await get_user_ranks(current_user.id, db)
