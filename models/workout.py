from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


class WorkoutSession(SQLModel, table=True):
    __tablename__ = "workout_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_calories: Optional[float] = None
    total_duration_mins: Optional[float] = None
    notes: Optional[str] = None


class ExerciseLog(SQLModel, table=True):
    __tablename__ = "exercise_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="workout_sessions.id", index=True)
    exercise_name: str
    muscle_group: str
    sets_json: Optional[List[Dict]] = Field(default=None, sa_column=Column(JSON))
    calories_burned: Optional[float] = None
    completed_at: datetime = Field(default_factory=datetime.utcnow)
