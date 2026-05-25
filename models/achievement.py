from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class UserAchievement(SQLModel, table=True):
    __tablename__ = "user_achievements"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    achievement_id: str
    unlocked_at: datetime = Field(default_factory=datetime.utcnow)


class UserStreak(SQLModel, table=True):
    __tablename__ = "user_streaks"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    activity_type: str
    current_streak: int = Field(default=0)
    longest_streak: int = Field(default=0)
    last_activity_date: Optional[date] = None
