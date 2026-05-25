import json
import re
from datetime import date, timedelta
from typing import Dict, List, Optional

from pydantic import BaseModel

from models.user import User
from models.workout import ExerciseLog, WorkoutSession
from services.ollama.client import OllamaClient
from services.workout.exercise_library import (
    EXERCISE_LIBRARY,
    get_exercises_by_equipment,
    get_exercises_by_muscle,
)
from utils.logger import get_logger

logger = get_logger("fitai.workout.generator")


# ── Response schemas ──────────────────────────────────────────────────────────

class ExerciseInPlan(BaseModel):
    name: str
    sets: int
    reps: str           # e.g. "8-12" or "30 seconds"
    rest_seconds: int
    muscle_group: str
    equipment: str
    instructions: str
    estimated_calories: float


class WorkoutPlan(BaseModel):
    workout_name: str
    description: str
    target_muscles: List[str]
    difficulty: str
    estimated_duration_mins: int
    estimated_calories: float
    exercises: List[ExerciseInPlan]
    warmup: List[str]
    cooldown: List[str]


# ── JSON parsing ──────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON in LLM response (first 300 chars): {text[:300]!r}")


# ── Exercise selection helpers ────────────────────────────────────────────────

def _select_exercises_for_prompt(
    target_muscles: Optional[List[str]],
    equipment: List[str],
    max_count: int = 25,
) -> List[dict]:
    """Pick the most relevant exercises to include in the AI prompt."""
    available = get_exercises_by_equipment(equipment or [])

    if target_muscles:
        targeted: List[dict] = []
        for muscle in target_muscles:
            targeted.extend(get_exercises_by_muscle(muscle))
        # Intersect: must be in both available and targeted
        targeted_names = {e["name"] for e in targeted}
        primary = [e for e in available if e["name"] in targeted_names]
        # Pad with remaining available if needed
        secondary = [e for e in available if e["name"] not in targeted_names]
        combined = primary + secondary
    else:
        combined = available

    # Deduplicate preserving order
    seen: set = set()
    unique = []
    for ex in combined:
        if ex["name"] not in seen:
            seen.add(ex["name"])
            unique.append(ex)

    return unique[:max_count]


def _slim_exercise(ex: dict) -> dict:
    """Return a lightweight dict for the AI prompt (skip long instructions)."""
    return {
        "name": ex["name"],
        "muscle_groups": ex["muscle_groups"],
        "equipment": ex["equipment"],
        "difficulty": ex["difficulty"],
        "category": ex["category"],
    }


# ── Workout generation ────────────────────────────────────────────────────────

_WORKOUT_SCHEMA = (
    '{"workout_name":"string","description":"string","target_muscles":["string"],'
    '"difficulty":"beginner|intermediate|advanced","estimated_duration_mins":number,'
    '"estimated_calories":number,"exercises":[{"name":"string","sets":number,'
    '"reps":"string","rest_seconds":number,"muscle_group":"string","equipment":"string",'
    '"instructions":"string","estimated_calories":number}],'
    '"warmup":["string"],"cooldown":["string"]}'
)


async def generate_workout(
    user: User,
    target_muscles: Optional[List[str]],
    duration_mins: int,
    equipment: List[str],
    ollama: OllamaClient,
) -> WorkoutPlan:
    exercises = _select_exercises_for_prompt(target_muscles, equipment)
    slim_list = [_slim_exercise(e) for e in exercises]

    prompt = (
        "You are a certified personal trainer. Create a detailed workout plan.\n\n"
        f"User profile:\n"
        f"  Goal: {user.goal}\n"
        f"  Weight: {user.weight_kg} kg\n"
        f"  Activity level: {user.activity_level}\n\n"
        f"Workout parameters:\n"
        f"  Duration: {duration_mins} minutes\n"
        f"  Target muscles: {', '.join(target_muscles) if target_muscles else 'full body'}\n"
        f"  Available equipment: {', '.join(equipment) if equipment else 'bodyweight only'}\n\n"
        f"Available exercises to choose from:\n{json.dumps(slim_list, indent=2)}\n\n"
        "Rules:\n"
        "  - Only use exercises from the provided list\n"
        "  - Include 5–8 main exercises appropriate for the duration\n"
        "  - Add 3–5 warmup activities and 3–5 cooldown stretches\n"
        "  - Set reps as ranges (e.g. '8-12') or time (e.g. '30 seconds') as appropriate\n"
        "  - estimated_calories per exercise should be realistic\n\n"
        f"Respond ONLY with valid JSON matching this schema:\n{_WORKOUT_SCHEMA}\n"
        "No extra text, no markdown fences."
    )

    last_exc: Exception = RuntimeError("unreachable")
    for attempt in range(2):
        try:
            raw = await ollama.chat(
                model="llama3",
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            data = _extract_json(raw)
            return WorkoutPlan(**data)
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Workout generation attempt {attempt + 1} failed: {exc}")
            if attempt == 0:
                prompt = (
                    f"Output ONLY a JSON object matching this schema, no other text:\n"
                    f"{_WORKOUT_SCHEMA}\n\n"
                    f"Create a {duration_mins}-minute workout for {user.goal} goal, "
                    f"targeting {', '.join(target_muscles) if target_muscles else 'full body'}. "
                    f"Equipment: {', '.join(equipment) if equipment else 'bodyweight'}. "
                    f"Use exercises from this list: {json.dumps([e['name'] for e in slim_list])}"
                )

    from fastapi import HTTPException
    raise HTTPException(status_code=422, detail=f"Could not generate workout plan: {last_exc}")


# ── Daily plan generation ─────────────────────────────────────────────────────

def _count_consecutive_workout_days(sessions: List[WorkoutSession]) -> int:
    """Count consecutive days ending today (or yesterday) that had a completed session."""
    completed_dates = {
        s.started_at.date()
        for s in sessions
        if s.completed_at is not None
    }
    today = date.today()
    consecutive = 0
    check = today - timedelta(days=1)   # yesterday
    while check in completed_dates:
        consecutive += 1
        check -= timedelta(days=1)
    return consecutive


def _muscles_trained_recently(exercise_logs: List[ExerciseLog], days: int = 2) -> List[str]:
    cutoff = date.today() - timedelta(days=days)
    return list({
        log.muscle_group.lower()
        for log in exercise_logs
        if log.muscle_group and log.completed_at.date() >= cutoff
    })


_DAILY_SCHEMA = (
    '{"should_workout":bool,"reason":"string",'
    '"workout_plan":null_or_workout_object,'
    '"rest_activities":["string"]}'
)


async def generate_daily_plan(
    user: User,
    recent_sessions: List[WorkoutSession],
    ollama: OllamaClient,
    exercise_logs: Optional[List[ExerciseLog]] = None,
) -> dict:
    consecutive = _count_consecutive_workout_days(recent_sessions)
    sessions_last_7 = len([s for s in recent_sessions if s.completed_at])
    recently_trained = _muscles_trained_recently(exercise_logs or [], days=2)

    all_muscles = ["chest", "back", "shoulders", "biceps", "triceps", "quadriceps",
                   "hamstrings", "glutes", "core"]
    fresh_muscles = [m for m in all_muscles if m not in recently_trained]

    should_rest = consecutive >= 3

    prompt = (
        "You are a certified personal trainer. Recommend whether the user should "
        "work out today or rest, and provide a detailed plan.\n\n"
        f"User: goal={user.goal}, weight={user.weight_kg}kg, "
        f"activity_level={user.activity_level}\n"
        f"Sessions last 7 days: {sessions_last_7}\n"
        f"Consecutive workout days: {consecutive}\n"
        f"Muscles trained in last 48h: {', '.join(recently_trained) if recently_trained else 'none'}\n"
        f"Fresh muscles available: {', '.join(fresh_muscles) if fresh_muscles else 'all muscles need rest'}\n"
        f"Equipment user has: {', '.join(user.equipment or ['bodyweight'])}\n\n"
    )

    if should_rest:
        prompt += (
            "The user has worked out 3+ consecutive days. "
            "Recommend an active rest day with light activities.\n\n"
        )

    workout_schema = _WORKOUT_SCHEMA

    prompt += (
        f"Respond ONLY with valid JSON:\n"
        '{"should_workout":true_or_false,"reason":"string",'
        f'"workout_plan":{workout_schema}_or_null,'
        '"rest_activities":["string - light activity suggestion"]}\n'
        "No markdown, no extra text."
    )

    try:
        raw = await ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        data = _extract_json(raw)

        # Validate and coerce workout_plan if present
        wp = data.get("workout_plan")
        if wp and isinstance(wp, dict):
            try:
                data["workout_plan"] = WorkoutPlan(**wp).model_dump()
            except Exception:
                data["workout_plan"] = None

        return data

    except Exception as exc:
        logger.error(f"Daily plan generation failed: {exc}")
        # Deterministic fallback
        if should_rest:
            return {
                "should_workout": False,
                "reason": f"You've worked out {consecutive} days in a row. Rest and recover today.",
                "workout_plan": None,
                "rest_activities": ["20-minute walk", "Full-body stretching", "Foam rolling", "Yoga"],
            }
        target = fresh_muscles[:2] if fresh_muscles else ["full body"]
        return {
            "should_workout": True,
            "reason": f"You've had {sessions_last_7} sessions this week. Keep the momentum going!",
            "workout_plan": None,
            "rest_activities": ["5-minute walk warmup", "Light stretching"],
        }


# ── Progressive overload ──────────────────────────────────────────────────────

_OVERLOAD_SCHEMA = (
    '{"exercise_name":"string","current_avg_weight":number,'
    '"suggested_weight":number,"suggested_reps":"string","reasoning":"string"}'
)


async def suggest_progressive_overload(
    exercise_name: str,
    recent_logs: List[Dict],   # [{weight_kg, reps, date}]
    ollama: OllamaClient,
) -> dict:
    if not recent_logs:
        return {
            "exercise_name": exercise_name,
            "current_avg_weight": 0.0,
            "suggested_weight": 0.0,
            "suggested_reps": "8-12",
            "reasoning": "No previous logs found. Start with a comfortable weight and track progress.",
        }

    avg_weight = sum(r.get("weight_kg", 0) for r in recent_logs) / len(recent_logs)

    history_text = "\n".join(
        f"  {r.get('date', 'unknown')}: {r.get('weight_kg', 0)} kg × {r.get('reps', 0)} reps"
        for r in recent_logs
    )

    prompt = (
        f"You are a strength coach. Suggest progressive overload for {exercise_name}.\n\n"
        f"Recent performance:\n{history_text}\n\n"
        "Apply progressive overload principles: if the user has hit the top of their rep range "
        "for 2+ sessions, increase weight by 2.5–5 kg. If reps are inconsistent, maintain "
        "weight and aim for rep quality.\n\n"
        f"Respond ONLY with valid JSON:\n{_OVERLOAD_SCHEMA}\nNo extra text."
    )

    try:
        raw = await ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        data = _extract_json(raw)
        data.setdefault("exercise_name", exercise_name)
        data.setdefault("current_avg_weight", round(avg_weight, 1))
        return data
    except Exception as exc:
        logger.error(f"Progressive overload suggestion failed: {exc}")
        suggested = round(avg_weight * 1.025 / 2.5) * 2.5  # round to nearest 2.5 kg
        return {
            "exercise_name": exercise_name,
            "current_avg_weight": round(avg_weight, 1),
            "suggested_weight": max(suggested, avg_weight),
            "suggested_reps": "8-12",
            "reasoning": f"Based on average weight of {avg_weight:.1f} kg, a small 2.5 kg increase is recommended.",
        }
