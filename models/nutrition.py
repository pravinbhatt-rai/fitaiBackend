from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class FoodLog(SQLModel, table=True):
    __tablename__ = "food_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    date: date
    meal_type: str  # breakfast | lunch | dinner | snack
    food_name: str
    calories: float
    protein_g: float = Field(default=0.0)
    carbs_g: float = Field(default=0.0)
    fat_g: float = Field(default=0.0)
    fiber_g: float = Field(default=0.0)
    sugar_g: float = Field(default=0.0)
    weight_grams: float = Field(default=100.0)
    logged_at: datetime = Field(default_factory=datetime.utcnow)


class WaterLog(SQLModel, table=True):
    __tablename__ = "water_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    date: date
    amount_ml: float
    logged_at: datetime = Field(default_factory=datetime.utcnow)
