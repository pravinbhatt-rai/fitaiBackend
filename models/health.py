from datetime import date, datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class HealthLog(SQLModel, table=True):
    __tablename__ = "health_logs"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_health_log_user_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    date: date
    sleep_hours: float
    sleep_quality: int  # 1–5
    mood: int  # 1–5
    energy: int  # 1–5
    hydration_ml: int
    resting_hr: Optional[int] = None
    stress_level: int  # 1–5
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HealthScore(SQLModel, table=True):
    __tablename__ = "health_scores"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_health_score_user_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    date: date
    nutrition_score: float = Field(default=0.0)
    workout_score: float = Field(default=0.0)
    sleep_score: float = Field(default=0.0)
    hydration_score: float = Field(default=0.0)
    mood_energy_score: float = Field(default=0.0)
    streak_bonus: float = Field(default=0.0)
    total: float = Field(default=0.0)
    grade: str = Field(default="F")
    insight: str = Field(default="")
    updated_at: datetime = Field(default_factory=datetime.utcnow)
