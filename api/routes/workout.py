from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.dependencies import get_ollama
from api.middleware.auth import get_current_user
from models.user import User
from models.workout import ExerciseLog, WorkoutSession
from services.achievements.engine import calculate_level, check_and_award
from services.groq.client import GroqClient as OllamaClient
from services.workout.exercise_library import (
    EXERCISE_LIBRARY,
    calculate_calories_burned,
    get_exercises_by_equipment,
    get_exercises_by_muscle,
)
from services.workout.generator import (
    WorkoutPlan,
    generate_daily_plan,
    generate_workout,
    suggest_progressive_overload,
)
from services.workout.tracker import WeeklyAnalysis, analyze_week
from utils.database import get_session
from utils.logger import get_logger

router = APIRouter(prefix="/api/workout", tags=["workout"])
logger = get_logger("fitai.routes.workout")




# ── Request / Response schemas ────────────────────────────────────────────────

class GenerateWorkoutRequest(BaseModel):
    target_muscles: Optional[List[str]] = None
    duration_mins: int = 45
    equipment: List[str] = []


class LogExerciseRequest(BaseModel):
    exercise_name: str
    muscle_group: str
    sets: List[Dict]          # [{weight_kg: float, reps: int}]
    duration_mins: Optional[float] = None


class StartSessionResponse(BaseModel):
    session_id: int
    started_at: str


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_session_for_user(
    session_id: int,
    user_id: int,
    db: AsyncSession,
) -> WorkoutSession:
    result = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == session_id)
        .where(WorkoutSession.user_id == user_id)
    )
    ws = result.scalars().first()
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout session not found",
        )
    return ws


async def _get_exercise_logs_for_session(
    session_id: int, db: AsyncSession
) -> List[ExerciseLog]:
    result = await db.execute(
        select(ExerciseLog).where(ExerciseLog.session_id == session_id)
    )
    return result.scalars().all()


async def _check_and_award_workout(user_id: int, db: AsyncSession) -> None:
    """Stub: achievement checks triggered after session completion."""
    pass


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/today")
async def get_today_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    ollama: OllamaClient = Depends(get_ollama),
):
    cutoff = datetime.utcnow() - timedelta(days=7)

    sessions_result = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .where(WorkoutSession.started_at >= cutoff)
        .order_by(WorkoutSession.started_at.desc())
    )
    recent_sessions = sessions_result.scalars().all()

    # Fetch exercise logs for those sessions for muscle analysis
    session_ids = [s.id for s in recent_sessions]
    logs: List[ExerciseLog] = []
    if session_ids:
        logs_result = await db.execute(
            select(ExerciseLog).where(ExerciseLog.session_id.in_(session_ids))
        )
        logs = logs_result.scalars().all()

    return await generate_daily_plan(
        user=current_user,
        recent_sessions=list(recent_sessions),
        ollama=ollama,
        exercise_logs=logs,
    )


@router.post("/generate", response_model=WorkoutPlan)
async def generate_workout_plan(
    req: GenerateWorkoutRequest,
    current_user: User = Depends(get_current_user),
    ollama: OllamaClient = Depends(get_ollama),
):
    # Merge user's stored equipment with the request's equipment list
    user_equip = list(current_user.equipment or [])
    request_equip = req.equipment or []
    effective_equip = list(set(user_equip + request_equip)) or ["bodyweight"]

    return await generate_workout(
        user=current_user,
        target_muscles=req.target_muscles,
        duration_mins=req.duration_mins,
        equipment=effective_equip,
        ollama=ollama,
    )


@router.post("/session/start", response_model=StartSessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    ws = WorkoutSession(user_id=current_user.id, started_at=datetime.utcnow())
    db.add(ws)
    await db.flush()
    await db.refresh(ws)
    return StartSessionResponse(session_id=ws.id, started_at=ws.started_at.isoformat())


@router.post("/session/{session_id}/exercise", status_code=status.HTTP_201_CREATED)
async def log_exercise(
    session_id: int,
    req: LogExerciseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    # Verify ownership
    await _get_session_for_user(session_id, current_user.id, db)

    duration = req.duration_mins or 5.0
    calories = calculate_calories_burned(
        req.exercise_name, duration, current_user.weight_kg
    )

    log = ExerciseLog(
        session_id=session_id,
        exercise_name=req.exercise_name,
        muscle_group=req.muscle_group,
        sets_json=req.sets,
        calories_burned=round(calories, 1),
        completed_at=datetime.utcnow(),
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)

    return {
        "id": log.id,
        "session_id": log.session_id,
        "exercise_name": log.exercise_name,
        "muscle_group": log.muscle_group,
        "sets_json": log.sets_json,
        "calories_burned": log.calories_burned,
        "completed_at": log.completed_at.isoformat(),
    }


@router.post("/session/{session_id}/complete")
async def complete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    ws = await _get_session_for_user(session_id, current_user.id, db)

    if ws.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session has already been completed",
        )

    logs = await _get_exercise_logs_for_session(session_id, db)

    total_calories = round(sum(log.calories_burned or 0 for log in logs), 1)
    duration_mins = round(
        (datetime.utcnow() - ws.started_at).total_seconds() / 60.0, 1
    )

    ws.completed_at = datetime.utcnow()
    ws.total_calories = total_calories
    ws.total_duration_mins = duration_mins
    db.add(ws)

    # Grant XP to user
    xp_gained = max(50, int(total_calories * 0.5))
    current_user.xp = (current_user.xp or 0) + xp_gained
    current_user.level = calculate_level(current_user.xp)
    db.add(current_user)

    await db.flush()
    await db.refresh(ws)

    new_achievements = await check_and_award(
        current_user.id,
        "workout_completed",
        {
            "calories": ws.total_calories or 0,
            "duration_mins": ws.total_duration_mins or 0,
            "started_at": ws.started_at,
            "session_id": ws.id,
        },
        db,
    )

    return {
        "session_id": ws.id,
        "started_at": ws.started_at.isoformat(),
        "completed_at": ws.completed_at.isoformat(),
        "total_calories": ws.total_calories,
        "total_duration_mins": ws.total_duration_mins,
        "xp_gained": xp_gained,
        "new_total_xp": current_user.xp,
        "new_level": current_user.level,
        "new_achievements": new_achievements,
        "exercises": [
            {
                "id": log.id,
                "exercise_name": log.exercise_name,
                "muscle_group": log.muscle_group,
                "sets_json": log.sets_json,
                "calories_burned": log.calories_burned,
                "completed_at": log.completed_at.isoformat(),
            }
            for log in logs
        ],
    }


@router.get("/history")
async def workout_history(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    cutoff = datetime.utcnow() - timedelta(days=days)

    sessions_result = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .where(WorkoutSession.started_at >= cutoff)
        .order_by(WorkoutSession.started_at.desc())
    )
    sessions = sessions_result.scalars().all()

    if not sessions:
        return []

    session_ids = [s.id for s in sessions]
    logs_result = await db.execute(
        select(ExerciseLog).where(ExerciseLog.session_id.in_(session_ids))
    )
    all_logs = logs_result.scalars().all()
    logs_by_session: Dict[int, List] = {}
    for log in all_logs:
        logs_by_session.setdefault(log.session_id, []).append(log)

    return [
        {
            "session_id": s.id,
            "started_at": s.started_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "total_calories": s.total_calories,
            "total_duration_mins": s.total_duration_mins,
            "notes": s.notes,
            "exercises": [
                {
                    "id": log.id,
                    "exercise_name": log.exercise_name,
                    "muscle_group": log.muscle_group,
                    "sets_json": log.sets_json,
                    "calories_burned": log.calories_burned,
                }
                for log in logs_by_session.get(s.id, [])
            ],
        }
        for s in sessions
    ]


@router.get("/analysis/week", response_model=WeeklyAnalysis)
async def weekly_analysis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    cutoff = datetime.utcnow() - timedelta(days=7)

    sessions_result = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .where(WorkoutSession.started_at >= cutoff)
    )
    sessions = sessions_result.scalars().all()

    session_ids = [s.id for s in sessions]
    logs: List[ExerciseLog] = []
    if session_ids:
        logs_result = await db.execute(
            select(ExerciseLog).where(ExerciseLog.session_id.in_(session_ids))
        )
        logs = logs_result.scalars().all()

    return analyze_week(list(sessions), list(logs))


@router.get("/exercises")
async def list_exercises(
    muscle: Optional[str] = Query(None, description="Filter by muscle group"),
    equipment: Optional[str] = Query(None, description="Filter by equipment type"),
    current_user: User = Depends(get_current_user),
):
    exercises = list(EXERCISE_LIBRARY.values())

    if muscle:
        ml = muscle.lower()
        exercises = [
            e for e in exercises
            if any(ml in mg.lower() for mg in e["muscle_groups"])
        ]

    if equipment:
        el = equipment.lower()
        exercises = [
            e for e in exercises
            if any(el in eq.lower() for eq in e["equipment"])
        ]

    return exercises


@router.get("/session/{session_id}/suggest/{exercise_name}")
async def suggest_overload(
    session_id: int,
    exercise_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    ollama: OllamaClient = Depends(get_ollama),
):
    # Verify the referenced session belongs to this user
    await _get_session_for_user(session_id, current_user.id, db)

    # Fetch last 5 logs for this exercise across all of the user's sessions
    result = await db.execute(
        select(ExerciseLog)
        .join(WorkoutSession, ExerciseLog.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == current_user.id)
        .where(ExerciseLog.exercise_name == exercise_name)
        .order_by(ExerciseLog.completed_at.desc())
        .limit(5)
    )
    logs = result.scalars().all()

    # Build the historical data the AI needs
    recent_data: List[Dict] = []
    for log in logs:
        sets = log.sets_json or []
        if sets:
            max_weight = max((float(s.get("weight_kg") or 0) for s in sets), default=0.0)
            max_reps   = max((int(s.get("reps") or 0) for s in sets), default=0)
        else:
            max_weight, max_reps = 0.0, 0
        recent_data.append({
            "weight_kg": max_weight,
            "reps": max_reps,
            "date": log.completed_at.date().isoformat(),
        })

    return await suggest_progressive_overload(exercise_name, recent_data, ollama)
