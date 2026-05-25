"""
Territory management: create, query, and stat territory polygons.
"""

import json
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.game import JogSession, Territory
from services.game.geo import (
    bbox_overlaps,
    convex_hull,
    geojson_to_polygon,
    point_in_polygon,
    point_near_polygon,
    polygon_area_km2,
    polygon_bbox,
    polygon_to_geojson,
    total_distance_km,
)
from utils.logger import get_logger

logger = get_logger("fitai.game.territory")


async def create_territory_from_session(
    jog: JogSession,
    db: AsyncSession,
    color_hex: str = "#3B82F6",
) -> Territory:
    """
    Build a Territory from a completed JogSession.
    Computes the convex hull of all GPS points, calculates area, and persists.
    Raises ValueError if there are fewer than 3 distinct GPS points.
    """
    raw = json.loads(jog.gps_points_json or "[]")
    points = [(p["lat"], p["lon"]) for p in raw]

    hull = convex_hull(points)
    area = polygon_area_km2(hull)
    geojson_str = polygon_to_geojson(hull)

    territory = Territory(
        user_id=jog.user_id,
        polygon_geojson=geojson_str,
        area_km2=round(area, 6),
        color_hex=color_hex,
    )
    db.add(territory)
    await db.flush()
    await db.refresh(territory)
    return territory


async def check_location(
    lat: float,
    lon: float,
    db: AsyncSession,
) -> Dict:
    """
    Check whether a (lat, lon) point is inside or near any territory.
    Returns info about the first matching territory (inside takes priority).
    """
    point = (lat, lon)
    result = await db.execute(select(Territory))
    territories = result.scalars().all()

    for t in territories:
        polygon = geojson_to_polygon(t.polygon_geojson)
        if point_in_polygon(point, polygon):
            return {
                "status": "inside",
                "territory_id": t.id,
                "user_id": t.user_id,
                "area_km2": t.area_km2,
                "color_hex": t.color_hex,
            }

    for t in territories:
        polygon = geojson_to_polygon(t.polygon_geojson)
        if point_near_polygon(point, polygon):
            return {
                "status": "near_boundary",
                "territory_id": t.id,
                "user_id": t.user_id,
                "area_km2": t.area_km2,
                "color_hex": t.color_hex,
            }

    return {"status": "unclaimed"}


async def get_territories_in_bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    db: AsyncSession,
) -> List[Dict]:
    """
    Return all territories whose bounding box overlaps the given bounding box.
    Each entry includes the GeoJSON polygon for map rendering.
    """
    query_bbox = (min_lat, min_lon, max_lat, max_lon)

    result = await db.execute(select(Territory))
    territories = result.scalars().all()

    out = []
    for t in territories:
        polygon = geojson_to_polygon(t.polygon_geojson)
        tbbox = polygon_bbox(polygon)
        if bbox_overlaps(query_bbox, tbbox):
            out.append({
                "territory_id": t.id,
                "user_id": t.user_id,
                "polygon_geojson": json.loads(t.polygon_geojson),
                "area_km2": t.area_km2,
                "color_hex": t.color_hex,
                "created_at": t.created_at.isoformat(),
            })

    return out


async def get_user_territory_stats(user_id: int, db: AsyncSession) -> Dict:
    """
    Return aggregate territory statistics for a user.
    """
    result = await db.execute(
        select(Territory).where(Territory.user_id == user_id)
    )
    territories = result.scalars().all()

    total_area = sum(t.area_km2 for t in territories)

    # Largest single territory
    largest = max(territories, key=lambda t: t.area_km2, default=None)

    return {
        "territory_count": len(territories),
        "total_area_km2": round(total_area, 6),
        "largest_territory_km2": round(largest.area_km2, 6) if largest else 0.0,
        "territories": [
            {
                "territory_id": t.id,
                "area_km2": t.area_km2,
                "color_hex": t.color_hex,
                "created_at": t.created_at.isoformat(),
            }
            for t in territories
        ],
    }
