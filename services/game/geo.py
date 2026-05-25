"""
Pure-Python geometry utilities for the territory jogging game.
No external geo libraries — all math is implemented from scratch.
"""

import json
import math
from typing import List, Optional, Tuple

# Type aliases
Point = Tuple[float, float]   # (lat, lon) in decimal degrees


# ── Constants ─────────────────────────────────────────────────────────────────

_EARTH_RADIUS_KM = 6371.0
_NEAR_THRESHOLD_M = 50.0  # metres — used for "point near polygon boundary"


# ── Haversine distance ────────────────────────────────────────────────────────

def haversine_km(a: Point, b: Point) -> float:
    """Return the great-circle distance in kilometres between two (lat, lon) points."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def total_distance_km(points: List[Point]) -> float:
    """Sum haversine distances along an ordered list of GPS points."""
    if len(points) < 2:
        return 0.0
    return sum(haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))


# ── Local Cartesian projection ─────────────────────────────────────────────────

def _to_local_xy(origin: Point, p: Point) -> Tuple[float, float]:
    """
    Project (lat, lon) point p into a flat (x, y) coordinate system in metres,
    using equirectangular approximation centred on origin.
    """
    lat0 = math.radians(origin[0])
    dlat = math.radians(p[0] - origin[0])
    dlon = math.radians(p[1] - origin[1])
    x = dlon * math.cos(lat0) * _EARTH_RADIUS_KM * 1000.0
    y = dlat * _EARTH_RADIUS_KM * 1000.0
    return x, y


# ── Cross product / orientation ───────────────────────────────────────────────

def _cross(o: Tuple, a: Tuple, b: Tuple) -> float:
    """2-D cross product of vectors OA and OB."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


# ── Graham scan convex hull ───────────────────────────────────────────────────

def convex_hull(points: List[Point]) -> List[Point]:
    """
    Return the convex hull of a list of (lat, lon) points using the Graham scan
    algorithm.  The hull is returned in counter-clockwise order and the first
    point is repeated at the end to close the ring.

    Raises ValueError if fewer than 3 distinct points are provided.
    """
    unique = list({p for p in points})
    if len(unique) < 3:
        raise ValueError(f"Need at least 3 distinct GPS points for a hull, got {len(unique)}")

    # Work in local XY metres so the cross-product scale is consistent
    origin = unique[0]
    xy = [_to_local_xy(origin, p) for p in unique]
    src = list(zip(xy, unique))  # [(xy, latlon), ...]

    # Sort by x then y
    src.sort(key=lambda t: (t[0][0], t[0][1]))

    def build_half(pts):
        stack = []
        for item in pts:
            while len(stack) >= 2 and _cross(stack[-2][0], stack[-1][0], item[0]) <= 0:
                stack.pop()
            stack.append(item)
        return stack

    lower = build_half(src)
    upper = build_half(reversed(src))

    # Remove last point of each half because it repeats the first of the other
    hull_items = lower[:-1] + upper[:-1]
    hull_latlon = [item[1] for item in hull_items]

    # Close the ring
    hull_latlon.append(hull_latlon[0])
    return hull_latlon


# ── Polygon area (Shoelace on local projection) ───────────────────────────────

def polygon_area_km2(polygon: List[Point]) -> float:
    """
    Compute the area of a polygon given as an ordered list of (lat, lon) points.
    The ring may or may not be explicitly closed (first == last).
    Uses the Shoelace formula on a local equirectangular projection.
    Returns area in km².
    """
    pts = polygon[:-1] if polygon[0] == polygon[-1] else list(polygon)
    if len(pts) < 3:
        return 0.0

    origin = pts[0]
    xy = [_to_local_xy(origin, p) for p in pts]
    n = len(xy)
    area_m2 = abs(
        sum(
            xy[i][0] * xy[(i + 1) % n][1] - xy[(i + 1) % n][0] * xy[i][1]
            for i in range(n)
        )
    ) / 2.0
    return area_m2 / 1_000_000.0


# ── Point-in-polygon (ray casting) ───────────────────────────────────────────

def point_in_polygon(point: Point, polygon: List[Point]) -> bool:
    """
    Return True if point (lat, lon) is inside the polygon.
    Uses the ray-casting algorithm in raw lat/lon space (accurate enough for
    territory sizes of a few km²).
    """
    lat, lon = point
    pts = polygon[:-1] if polygon[0] == polygon[-1] else list(polygon)
    n = len(pts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i][1], pts[i][0]   # lon as x, lat as y
        xj, yj = pts[j][1], pts[j][0]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# ── Point near polygon boundary ──────────────────────────────────────────────

def _point_to_segment_dist_m(p: Point, a: Point, b: Point, origin: Point) -> float:
    """Return the distance in metres from point p to segment a–b."""
    px, py = _to_local_xy(origin, p)
    ax, ay = _to_local_xy(origin, a)
    bx, by = _to_local_xy(origin, b)

    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0.0:
        return math.hypot(px - ax, py - ay)

    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def point_near_polygon(point: Point, polygon: List[Point], threshold_m: float = _NEAR_THRESHOLD_M) -> bool:
    """
    Return True if point is within threshold_m metres of any edge of the polygon.
    """
    pts = polygon[:-1] if polygon[0] == polygon[-1] else list(polygon)
    n = len(pts)
    origin = pts[0]
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        if _point_to_segment_dist_m(point, a, b, origin) <= threshold_m:
            return True
    return False


# ── GeoJSON conversion ────────────────────────────────────────────────────────

def polygon_to_geojson(polygon: List[Point]) -> str:
    """
    Serialize a polygon (list of (lat, lon)) to a GeoJSON Feature string.
    GeoJSON coordinates are [lon, lat] per the spec.
    The ring is closed automatically if not already.
    """
    pts = list(polygon)
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    coordinates = [[p[1], p[0]] for p in pts]   # lon, lat
    geojson = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [coordinates],
        },
        "properties": {},
    }
    return json.dumps(geojson)


def geojson_to_polygon(geojson_str: str) -> List[Point]:
    """
    Deserialize a GeoJSON Feature/Geometry string back to a list of (lat, lon).
    """
    data = json.loads(geojson_str)
    if data.get("type") == "Feature":
        data = data["geometry"]
    coordinates = data["coordinates"][0]   # first ring
    # GeoJSON is [lon, lat] — flip to (lat, lon)
    return [(c[1], c[0]) for c in coordinates]


# ── Bounding-box helpers ──────────────────────────────────────────────────────

def polygon_bbox(polygon: List[Point]) -> Tuple[float, float, float, float]:
    """Return (min_lat, min_lon, max_lat, max_lon) for a polygon."""
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    return min(lats), min(lons), max(lats), max(lons)


def bbox_overlaps(
    bbox1: Tuple[float, float, float, float],
    bbox2: Tuple[float, float, float, float],
) -> bool:
    """Return True if two bounding boxes (min_lat, min_lon, max_lat, max_lon) overlap."""
    min_lat1, min_lon1, max_lat1, max_lon1 = bbox1
    min_lat2, min_lon2, max_lat2, max_lon2 = bbox2
    return not (
        max_lat1 < min_lat2 or max_lat2 < min_lat1
        or max_lon1 < min_lon2 or max_lon2 < min_lon1
    )
