from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    name: str
    age: int
    weight_kg: float
    height_cm: float
    sex: str
    goal: str  # lose_weight | build_muscle | stay_fit | improve_health
    activity_level: str  # sedentary | light | moderate | active | very_active
    wake_time: str = Field(default="07:00")
    equipment: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    xp: int = Field(default=0)
    level: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
