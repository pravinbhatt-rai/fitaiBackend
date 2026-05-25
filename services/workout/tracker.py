from collections import Counter
from datetime import date, timedelta
from typing import Dict, List

from pydantic import BaseModel

from models.workout import ExerciseLog, WorkoutSession


class WeeklyAnalysis(BaseModel):
    total_sessions: int
    total_volume_kg: float
    total_calories_burned: float
    muscle_groups_trained: Dict[str, int]  # muscle → times trained
    consistency_score: float               # 0–100
    strongest_day: str
    suggestions: List[str]


_ALL_MAJOR_MUSCLES = [
    "chest", "back", "shoulders", "biceps", "triceps",
    "quadriceps", "hamstrings", "glutes", "core",
]

_IDEAL_SESSIONS_PER_WEEK = 5


def analyze_week(
    sessions: List[WorkoutSession],
    exercise_logs: List[ExerciseLog],
) -> WeeklyAnalysis:
    """Compute a full weekly analysis from raw session and exercise log records."""

    # ── Session metrics ───────────────────────────────────────────────────────
    completed = [s for s in sessions if s.completed_at is not None]
    total_sessions = len(completed)

    # ── Volume and calories ───────────────────────────────────────────────────
    total_volume: float = 0.0
    total_calories: float = 0.0

    for log in exercise_logs:
        total_calories += log.calories_burned or 0.0
        for s in log.sets_json or []:
            weight = float(s.get("weight_kg") or 0)
            reps   = int(s.get("reps") or 0)
            total_volume += weight * reps

    # ── Muscle groups ─────────────────────────────────────────────────────────
    muscle_counter: Counter = Counter()
    for log in exercise_logs:
        if log.muscle_group:
            muscle_counter[log.muscle_group.lower()] += 1

    # ── Consistency score ─────────────────────────────────────────────────────
    consistency = min(total_sessions / _IDEAL_SESSIONS_PER_WEEK * 100.0, 100.0)

    # ── Strongest day (most lifting volume) ───────────────────────────────────
    daily_volume: Dict[date, float] = {}
    for log in exercise_logs:
        d = log.completed_at.date()
        vol = sum(
            float(s.get("weight_kg") or 0) * int(s.get("reps") or 0)
            for s in (log.sets_json or [])
        )
        daily_volume[d] = daily_volume.get(d, 0.0) + vol

    if daily_volume:
        best_date = max(daily_volume, key=lambda d: daily_volume[d])
        strongest_day = best_date.strftime("%A, %b %d")
    else:
        strongest_day = "No lifting data this week"

    # ── Suggestions ───────────────────────────────────────────────────────────
    suggestions: List[str] = []

    undertrained = [
        m for m in _ALL_MAJOR_MUSCLES
        if muscle_counter.get(m, 0) < 1
    ]
    if undertrained:
        muscles_str = ", ".join(undertrained[:3])
        suggestions.append(
            f"These muscle groups got no direct work this week: {muscles_str}. "
            "Add a targeted session to keep your body balanced."
        )

    low_frequency = [
        m for m in _ALL_MAJOR_MUSCLES
        if 0 < muscle_counter.get(m, 0) < 2
    ]
    if low_frequency and len(suggestions) < 3:
        muscles_str = ", ".join(low_frequency[:2])
        suggestions.append(
            f"{muscles_str} were trained only once this week. "
            "Aim for 2× per week on major groups for better hypertrophy."
        )

    if total_sessions < 3:
        suggestions.append(
            f"You completed {total_sessions} sessions this week. "
            "Try to reach 3–5 workouts for optimal progress."
        )
    elif total_sessions >= _IDEAL_SESSIONS_PER_WEEK:
        suggestions.append(
            "Excellent training frequency this week! "
            "Ensure you're getting 7–9 hours of sleep for recovery."
        )

    if total_calories > 0 and total_volume == 0:
        suggestions.append(
            "You had cardio-only sessions this week. "
            "Consider adding 2 strength sessions to preserve muscle mass."
        )

    if not suggestions:
        suggestions.append(
            "Great balanced week! Maintain this consistency and gradually "
            "increase weights to drive continued progress."
        )

    # Trim to max 3 suggestions
    suggestions = suggestions[:3]

    return WeeklyAnalysis(
        total_sessions=total_sessions,
        total_volume_kg=round(total_volume, 1),
        total_calories_burned=round(total_calories, 1),
        muscle_groups_trained=dict(muscle_counter),
        consistency_score=round(consistency, 1),
        strongest_day=strongest_day,
        suggestions=suggestions,
    )
