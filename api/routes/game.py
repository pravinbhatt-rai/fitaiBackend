import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from api.middleware.auth import get_current_user
from models.game import JogSession, Territory
from models.user import User
from services.achievements.engine import calculate_level, check_and_award
from services.game.session import add_gps_points, end_jog_session, start_jog_session
from services.game.territory import (
    check_location,
    get_territories_in_bbox,
    get_user_territory_stats,
)
from utils.database import get_session
from utils.logger import get_logger

router = APIRouter(prefix="/api/game", tags=["game"])
logger = get_logger("fitai.routes.game")


# ── Request / Response schemas ────────────────────────────────────────────────

class GpsPoint(BaseModel):
    lat: float
    lon: float


class AddPointsRequest(BaseModel):
    points: List[GpsPoint]


class EndSessionRequest(BaseModel):
    create_territory: bool = True


# ── DB helper ─────────────────────────────────────────────────────────────────

async def _get_jog_for_user(
    session_id: int,
    user_id: int,
    db: AsyncSession,
) -> JogSession:
    result = await db.execute(
        select(JogSession)
        .where(JogSession.id == session_id)
        .where(JogSession.user_id == user_id)
    )
    jog = result.scalars().first()
    if jog is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Jog session not found",
        )
    return jog


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/session/start", status_code=status.HTTP_201_CREATED)
async def start_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Start a new jog session."""
    jog = await start_jog_session(current_user.id, db)
    return {
        "session_id": jog.id,
        "start_time": jog.start_time.isoformat(),
        "user_id": jog.user_id,
    }


@router.post("/session/{session_id}/points", status_code=status.HTTP_200_OK)
async def add_points(
    session_id: int,
    req: AddPointsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Append GPS points to an active jog session (min 5 m between accepted points)."""
    jog = await _get_jog_for_user(session_id, current_user.id, db)

    if jog.end_time is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Jog session is already completed",
        )

    raw = [{"lat": p.lat, "lon": p.lon} for p in req.points]
    jog = await add_gps_points(jog, raw, db)

    stored = json.loads(jog.gps_points_json or "[]")
    return {
        "session_id": jog.id,
        "accepted_points_total": len(stored),
        "submitted": len(req.points),
    }


@router.post("/session/{session_id}/end")
async def end_session(
    session_id: int,
    req: EndSessionRequest = EndSessionRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    End a jog session: compute distance/calories, grant XP, optionally create
    a territory from the convex hull of the route.
    """
    jog = await _get_jog_for_user(session_id, current_user.id, db)

    if jog.end_time is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Jog session is already completed",
        )

    summary = await end_jog_session(
        jog,
        user_weight_kg=current_user.weight_kg,
        db=db,
        create_territory=req.create_territory,
    )

    # Grant XP to user
    xp_gained = summary["xp_gained"]
    current_user.xp = (current_user.xp or 0) + xp_gained
    current_user.level = calculate_level(current_user.xp)
    db.add(current_user)
    await db.flush()

    # Award achievements for jog completion
    territory = summary.get("territory") or {}
    new_achievements = await check_and_award(
        current_user.id,
        "jog_completed",
        {
            "distance_km": summary["distance_km"],
            "duration_mins": summary["duration_mins"],
            "session_id": summary["session_id"],
        },
        db,
    )
    if territory:
        new_achievements += await check_and_award(
            current_user.id,
            "territory_created",
            {
                "area_km2": territory.get("area_km2", 0),
                "territory_id": territory.get("territory_id"),
            },
            db,
        )

    summary["new_total_xp"] = current_user.xp
    summary["new_level"] = current_user.level
    summary["new_achievements"] = new_achievements
    return summary


@router.get("/session/{session_id}")
async def get_session_detail(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return details for a specific jog session."""
    jog = await _get_jog_for_user(session_id, current_user.id, db)
    stored = json.loads(jog.gps_points_json or "[]")

    return {
        "session_id": jog.id,
        "user_id": jog.user_id,
        "start_time": jog.start_time.isoformat(),
        "end_time": jog.end_time.isoformat() if jog.end_time else None,
        "distance_km": jog.distance_km,
        "calories": jog.calories,
        "territory_id": jog.territory_id,
        "point_count": len(stored),
        "gps_points": stored,
    }


@router.get("/territory/{territory_id}")
async def get_territory(
    territory_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return a specific territory by ID (any user may view any territory)."""
    result = await db.execute(
        select(Territory).where(Territory.id == territory_id)
    )
    t = result.scalars().first()
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Territory not found")

    return {
        "territory_id": t.id,
        "user_id": t.user_id,
        "polygon_geojson": json.loads(t.polygon_geojson),
        "area_km2": t.area_km2,
        "color_hex": t.color_hex,
        "created_at": t.created_at.isoformat(),
    }


@router.delete("/territory/{territory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_territory(
    territory_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Delete a territory owned by the current user."""
    result = await db.execute(
        select(Territory)
        .where(Territory.id == territory_id)
        .where(Territory.user_id == current_user.id)
    )
    t = result.scalars().first()
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Territory not found")

    await db.delete(t)
    await db.flush()


@router.get("/map")
async def map_view(
    min_lat: float = Query(...),
    min_lon: float = Query(...),
    max_lat: float = Query(...),
    max_lon: float = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return all territories overlapping a given bounding box for map rendering."""
    territories = await get_territories_in_bbox(min_lat, min_lon, max_lat, max_lon, db)
    return {"territories": territories, "count": len(territories)}


@router.get("/location/check")
async def location_check(
    lat: float = Query(...),
    lon: float = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Check whether a GPS point is inside/near any territory."""
    return await check_location(lat, lon, db)


@router.get("/stats")
async def my_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return territory and session stats for the current user."""
    territory_stats = await get_user_territory_stats(current_user.id, db)

    sessions_result = await db.execute(
        select(JogSession)
        .where(JogSession.user_id == current_user.id)
        .where(JogSession.end_time.isnot(None))
    )
    sessions = sessions_result.scalars().all()

    total_distance = round(sum(s.distance_km for s in sessions), 3)
    total_calories = round(sum(s.calories for s in sessions), 1)
    total_sessions = len(sessions)

    return {
        "total_jog_sessions": total_sessions,
        "total_distance_km": total_distance,
        "total_calories": total_calories,
        **territory_stats,
        "xp": current_user.xp,
        "level": current_user.level,
    }


@router.get("/leaderboard")
async def leaderboard(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Return the top users ranked by total territory area claimed.
    """
    result = await db.execute(select(Territory))
    all_territories = result.scalars().all()

    area_by_user: dict = {}
    count_by_user: dict = {}
    for t in all_territories:
        area_by_user[t.user_id] = area_by_user.get(t.user_id, 0.0) + t.area_km2
        count_by_user[t.user_id] = count_by_user.get(t.user_id, 0) + 1

    ranked = sorted(area_by_user.items(), key=lambda kv: kv[1], reverse=True)[:limit]

    # Fetch user names in one query
    user_ids = [uid for uid, _ in ranked]
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users_map = {u.id: u for u in users_result.scalars().all()}
    else:
        users_map = {}

    entries = []
    for rank, (uid, area) in enumerate(ranked, start=1):
        u = users_map.get(uid)
        entries.append({
            "rank": rank,
            "user_id": uid,
            "name": u.name if u else "Unknown",
            "total_area_km2": round(area, 6),
            "territory_count": count_by_user.get(uid, 0),
            "xp": u.xp if u else 0,
            "level": u.level if u else 1,
        })

    # Find current user's position even if outside top-N
    my_rank = next((e["rank"] for e in entries if e["user_id"] == current_user.id), None)
    if my_rank is None:
        my_area = area_by_user.get(current_user.id, 0.0)
        my_rank = sum(1 for a in area_by_user.values() if a > my_area) + 1

    return {
        "leaderboard": entries,
        "my_rank": my_rank,
        "my_total_area_km2": round(area_by_user.get(current_user.id, 0.0), 6),
    }
