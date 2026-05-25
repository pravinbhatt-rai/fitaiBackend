from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Territory(SQLModel, table=True):
    __tablename__ = "territories"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    polygon_geojson: str
    area_km2: float
    color_hex: str = Field(default="#3B82F6")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JogSession(SQLModel, table=True):
    __tablename__ = "jog_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    start_time: datetime
    end_time: Optional[datetime] = None
    gps_points_json: Optional[str] = None
    distance_km: float = Field(default=0.0)
    calories: float = Field(default=0.0)
    territory_id: Optional[int] = Field(default=None, foreign_key="territories.id")
