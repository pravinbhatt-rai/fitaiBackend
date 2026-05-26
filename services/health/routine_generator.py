"""
AI-powered daily routine and health insights generation.
"""

import json
import re
from datetime import date
from typing import List, Optional

from pydantic import BaseModel

from models.user import User
from services.groq.client import GroqClient as OllamaClient
from utils.logger import get_logger

logger = get_logger("fitai.health.routine")


# ── Models ─────────────────────────────────────────────────────────────────────

class RoutineActivity(BaseModel):
    time: str           # "06:30"
    activity: str
    duration_mins: int
    category: str       # exercise / nutrition / rest / work / mindfulness
    notes: str


class DailyRoutine(BaseModel):
    date: str
    wake_time: str
    sleep_time: str
    morning_routine: List[RoutineActivity]
    workout: Optional[dict] = None   # {time, workout_name, duration_mins} | null
    meals: List[dict]                # [{time, meal_type, name, target_calories}]
    evening_routine: List[RoutineActivity]
    motivational_message: str
    health_tip: str


# ── Internal helpers ───────────────────────────────────────────────────────────

def _add_minutes(time_str: str, mins: int) -> str:
    """Advance a HH:MM string by `mins` minutes, wrapping at 24 h."""
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + mins
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


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
            return json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON in LLM response: {text[:200]!r}")


def _fallback_routine(user: User, has_workout_today: bool) -> dict:
    """Deterministic fallback when AI call fails."""
    wake = user.wake_time or "07:00"
    today = date.today().isoformat()

    morning = [
        {"time": wake, "activity": "Wake up & drink water", "duration_mins": 5,
         "category": "rest", "notes": "Start hydrated"},
        {"time": _add_minutes(wake, 5), "activity": "Light stretching",
         "duration_mins": 10, "category": "exercise", "notes": "Loosen up before the day"},
        {"time": _add_minutes(wake, 30), "activity": "Breakfast",
         "duration_mins": 20, "category": "nutrition",
         "notes": "High-protein meal to fuel your morning"},
    ]

    workout = None
    if has_workout_today:
        workout = {
            "time": _add_minutes(wake, 60),
            "workout_name": "Today's AI-generated workout",
            "duration_mins": 45,
        }

    meals = [
        {"time": _add_minutes(wake, 30), "meal_type": "breakfast",
         "name": "High-protein breakfast", "target_calories": 450},
        {"time": _add_minutes(wake, 210), "meal_type": "snack",
         "name": "Morning snack", "target_calories": 200},
        {"time": _add_minutes(wake, 330), "meal_type": "lunch",
         "name": "Balanced lunch", "target_calories": 600},
        {"time": _add_minutes(wake, 510), "meal_type": "snack",
         "name": "Afternoon snack", "target_calories": 150},
        {"time": _add_minutes(wake, 660), "meal_type": "dinner",
         "name": "Nutritious dinner", "target_calories": 550},
    ]

    evening = [
        {"time": _add_minutes(wake, 780), "activity": "Evening walk",
         "duration_mins": 20, "category": "exercise", "notes": "Light movement to wind down"},
        {"time": _add_minutes(wake, 810), "activity": "Stretching / yoga",
         "duration_mins": 15, "category": "mindfulness", "notes": "Release tension from the day"},
        {"time": _add_minutes(wake, 840), "activity": "Reading",
         "duration_mins": 30, "category": "rest", "notes": "Screen-free wind-down"},
    ]

    goal_messages = {
        "lose_weight": "Every healthy choice today is one step closer to your goal. You've got this!",
        "build_muscle": "Consistency builds the physique you want — stay on plan and trust the process.",
        "stay_fit": "Staying active and fuelled keeps you at your best. Keep it up!",
        "improve_health": "Small daily habits compound into lasting health. You're doing great!",
    }

    return {
        "date": today,
        "wake_time": wake,
        "sleep_time": _add_minutes(wake, 870),
        "morning_routine": morning,
        "workout": workout,
        "meals": meals,
        "evening_routine": evening,
        "motivational_message": goal_messages.get(user.goal or "", "Keep showing up — every day counts!"),
        "health_tip": "Drink a glass of water first thing in the morning to kick-start your metabolism.",
    }


_ROUTINE_SCHEMA = (
    '{"date":"YYYY-MM-DD","wake_time":"HH:MM","sleep_time":"HH:MM",'
    '"morning_routine":[{"time":"HH:MM","activity":"string","duration_mins":number,'
    '"category":"exercise|nutrition|rest|work|mindfulness","notes":"string"}],'
    '"workout":{"time":"HH:MM","workout_name":"string","duration_mins":number},'
    '"meals":[{"time":"HH:MM","meal_type":"breakfast|lunch|dinner|snack",'
    '"name":"string","target_calories":number}],'
    '"evening_routine":[{"time":"HH:MM","activity":"string","duration_mins":number,'
    '"category":"exercise|nutrition|rest|work|mindfulness","notes":"string"}],'
    '"motivational_message":"string","health_tip":"string"}'
)


# ── Public functions ───────────────────────────────────────────────────────────

async def generate_daily_routine(
    user: User,
    health_score: Optional[float],
    has_workout_today: bool,
    ollama: OllamaClient,
) -> DailyRoutine:
    """Call llama3 to produce a personalised DailyRoutine for today."""
    today = date.today().isoformat()

    prompt = (
        "You are a certified personal trainer and nutritionist. "
        "Create a complete daily routine for today.\n\n"
        f"User profile:\n"
        f"  Name: {user.name}, Goal: {user.goal}\n"
        f"  Wake time preference: {user.wake_time or '07:00'}\n"
        f"  Activity level: {user.activity_level}\n"
        f"  Today's health score: {health_score if health_score is not None else 'unknown'}/100\n"
        f"  Workout scheduled today: {has_workout_today}\n\n"
        "Requirements:\n"
        f"  - Date is {today}\n"
        "  - Schedule realistic timings starting from wake time\n"
        "  - Include pre/post workout nutrition if workout today\n"
        "  - 3 main meals + 2 snacks with target calories\n"
        "  - 3–4 morning routine activities and 3–4 evening activities\n"
        "  - Evening wind-down routine\n"
        "  - Motivational message tailored to their goal\n"
        "  - One practical health tip\n"
        f"  - If no workout today, set workout field to null\n\n"
        f"Respond ONLY with valid JSON matching this exact schema:\n{_ROUTINE_SCHEMA}\n"
        "No extra text, no markdown fences."
    )

    try:
        raw = await ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        data = _extract_json(raw)

        # Coerce nested lists
        morning = [RoutineActivity(**a) for a in (data.get("morning_routine") or [])]
        evening = [RoutineActivity(**a) for a in (data.get("evening_routine") or [])]
        workout = data.get("workout") if isinstance(data.get("workout"), dict) else None

        return DailyRoutine(
            date=data.get("date", today),
            wake_time=data.get("wake_time", user.wake_time or "07:00"),
            sleep_time=data.get("sleep_time", "22:30"),
            morning_routine=morning,
            workout=workout,
            meals=data.get("meals", []),
            evening_routine=evening,
            motivational_message=data.get("motivational_message", ""),
            health_tip=data.get("health_tip", ""),
        )

    except Exception as exc:
        logger.warning(f"Daily routine generation failed: {exc}; using fallback")
        return DailyRoutine(**_fallback_routine(user, has_workout_today))


_INSIGHTS_SCHEMA = '{"insights":["string","string","string","string","string"]}'


async def generate_health_insights(
    user_id: int,
    health_logs: list,
    nutrition_data: dict,
    workout_data: dict,
    ollama: OllamaClient,
) -> List[str]:
    """
    Ask llama3 for 5 personalised health insights based on 7 days of data.
    Returns a list of insight strings (falls back to static tips on failure).
    """
    log_summary = [
        {
            "date": str(h.date),
            "sleep_hours": h.sleep_hours,
            "sleep_quality": h.sleep_quality,
            "mood": h.mood,
            "energy": h.energy,
            "stress_level": h.stress_level,
        }
        for h in health_logs
    ] if health_logs else []

    prompt = (
        "You are a health and fitness AI. Analyse the following 7-day data and "
        "return exactly 5 short, personalised, actionable health insights.\n\n"
        f"Health logs (last 7 days): {json.dumps(log_summary)}\n"
        f"Nutrition summary: {json.dumps(nutrition_data)}\n"
        f"Workout summary: {json.dumps(workout_data)}\n\n"
        f"Respond ONLY with valid JSON: {_INSIGHTS_SCHEMA}\n"
        "Each insight must be 1–2 sentences. No markdown, no extra text."
    )

    try:
        raw = await ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start: end + 1])
        insights = data.get("insights", [])
        if isinstance(insights, list) and insights:
            return [str(i) for i in insights[:5]]
    except Exception as exc:
        logger.warning(f"Health insights generation failed: {exc}")

    # Static fallback
    return [
        "Log your meals consistently — nutrition data is the foundation of all progress tracking.",
        "Aim for 7–9 hours of sleep; it's when your body repairs muscle and consolidates memory.",
        "Staying hydrated improves energy levels, focus, and workout performance.",
        "Tracking your mood and energy helps reveal which habits actually move the needle for you.",
        "Consistency over perfection — showing up every day matters more than any single session.",
    ]
