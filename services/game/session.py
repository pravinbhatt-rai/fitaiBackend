"""
Jog session lifecycle: start, add GPS points, end.
"""

import json
import math
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.game import JogSession, Territory
from services.game.geo import haversine_km, total_distance_km
from utils.logger import get_logger

logger = get_logger("fitai.game.session")

_MIN_POINT_DISTANCE_M = 5.0   # deduplicate GPS jitter under 5 m


def _calories_for_distance(distance_km: float, weight_kg: float) -> float:
    """Estimate calories burned jogging (MET ~8) over a given distance."""
    if distance_km <= 0:
        return 0.0
    speed_kmh = 8.0   # assumed average jogging pace
    duration_h = distance_km / speed_kmh
    met = 8.0
    return round(met * weight_kg * duration_h, 1)


async def start_jog_session(user_id: int, db: AsyncSession) -> JogSession:
    """Create and persist a new JogSession for user_id."""
    jog = JogSession(
        user_id=user_id,
        start_time=datetime.utcnow(),
        gps_points_json=json.dumps([]),
    )
    db.add(jog)
    await db.flush()
    await db.refresh(jog)
    logger.info(f"Started jog session {jog.id} for user {user_id}")
    return jog


async def add_gps_points(
    jog: JogSession,
    new_points: List[dict],   # [{"lat": float, "lon": float}]
    db: AsyncSession,
) -> JogSession:
    """
    Append new GPS points to a session, filtering out any that are within
    _MIN_POINT_DISTANCE_M of the previous accepted point to remove GPS jitter.
    """
    existing: List[dict] = json.loads(jog.gps_points_json or "[]")
    last: Optional[dict] = existing[-1] if existing else None

    for pt in new_points:
        if last is not None:
            dist_m = haversine_km(
                (last["lat"], last["lon"]),
                (pt["lat"], pt["lon"]),
            ) * 1000.0
            if dist_m < _MIN_POINT_DISTANCE_M:
                continue
        existing.append({"lat": pt["lat"], "lon": pt["lon"]})
        last = pt

    jog.gps_points_json = json.dumps(existing)
    db.add(jog)
    await db.flush()
    await db.refresh(jog)
    return jog


async def end_jog_session(
    jog: JogSession,
    user_weight_kg: float,
    db: AsyncSession,
    create_territory: bool = True,
) -> dict:
    """
    Finalise the session: compute distance, calories, XP; optionally create a
    Territory from the convex hull of the route.

    XP formula: int(distance_km × 100) + 50
    Returns a summary dict (does not modify the User object — caller handles XP).
    """
    points_raw: List[dict] = json.loads(jog.gps_points_json or "[]")
    points = [(p["lat"], p["lon"]) for p in points_raw]

    distance_km = round(total_distance_km(points), 3)
    calories = _calories_for_distance(distance_km, user_weight_kg)
    xp_gained = int(distance_km * 100) + 50

    jog.end_time = datetime.utcnow()
    jog.distance_km = distance_km
    jog.calories = calories
    db.add(jog)
    await db.flush()
    await db.refresh(jog)

    territory_data: Optional[dict] = None
    if create_territory and len(points) >= 3:
        try:
            from services.game.territory import create_territory_from_session
            territory = await create_territory_from_session(jog, db)
            jog.territory_id = territory.id
            db.add(jog)
            await db.flush()
            await db.refresh(jog)
            territory_data = {
                "territory_id": territory.id,
                "area_km2": territory.area_km2,
                "polygon_geojson": json.loads(territory.polygon_geojson),
            }
        except ValueError as exc:
            logger.warning(f"Could not create territory for session {jog.id}: {exc}")

    duration_mins = round(
        (jog.end_time - jog.start_time).total_seconds() / 60.0, 1
    )

    return {
        "session_id": jog.id,
        "start_time": jog.start_time.isoformat(),
        "end_time": jog.end_time.isoformat(),
        "distance_km": distance_km,
        "duration_mins": duration_mins,
        "calories": calories,
        "xp_gained": xp_gained,
        "point_count": len(points),
        "territory": territory_data,
    }
