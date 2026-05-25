from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from api.dependencies.auth import get_current_user_id

router = APIRouter(prefix="/workouts", tags=["workouts"])


class WorkoutOut(BaseModel):
    id: str
    name: str
    difficulty: str
    estimated_duration: int
    exercises: list[dict]
    tags: list[str]


MOCK_WORKOUTS = [
    WorkoutOut(
        id="w1",
        name="Full Body Blast",
        difficulty="intermediate",
        estimated_duration=45,
        exercises=[{"name": "Squat", "sets": 4, "reps": 10}],
        tags=["strength", "full-body"],
    ),
    WorkoutOut(
        id="w2",
        name="Core Crusher",
        difficulty="beginner",
        estimated_duration=20,
        exercises=[{"name": "Plank", "sets": 3, "reps": 60}],
        tags=["core", "beginner"],
    ),
]


@router.get("")
async def list_workouts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
):
    return {
        "data": MOCK_WORKOUTS,
        "meta": {"total": len(MOCK_WORKOUTS), "page": page, "perPage": per_page},
        "success": True,
        "message": "Workouts fetched",
    }


@router.get("/history")
async def get_history(
    limit: int = Query(10, ge=1, le=50),
    user_id: str = Depends(get_current_user_id),
):
    return {"data": [], "success": True, "message": "History fetched"}


@router.get("/{workout_id}")
async def get_workout(workout_id: str, user_id: str = Depends(get_current_user_id)):
    workout = next((w for w in MOCK_WORKOUTS if w.id == workout_id), None)
    if not workout:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Workout not found")
    return {"data": workout, "success": True, "message": "Workout fetched"}
