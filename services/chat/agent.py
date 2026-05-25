"""
FitAI streaming chat agent — personal fitness coach with full user context.
"""

import json
import re
from datetime import date, datetime, timedelta
from typing import AsyncGenerator, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.health import HealthLog, HealthScore
from models.nutrition import FoodLog, WaterLog
from models.user import User
from models.workout import WorkoutSession
from services.achievements.streak import get_all_streaks
from services.nutrition.analyzer import calculate_daily_goals
from services.ollama.client import OllamaClient
from utils.logger import get_logger

logger = get_logger("fitai.chat.agent")


class FitAIAgent:
    def __init__(self, user: User, ollama: OllamaClient) -> None:
        self.user = user
        self.ollama = ollama

    # ── Context builder ────────────────────────────────────────────────────────

    async def build_context(self, db: AsyncSession) -> dict:
        """Fetch all real-time data needed to personalise the system prompt."""
        today = date.today()
        goals = calculate_daily_goals(self.user)

        # Today's food logs
        r_food = await db.execute(
            select(FoodLog)
            .where(FoodLog.user_id == self.user.id)
            .where(FoodLog.date == today)
        )
        food_logs = r_food.scalars().all()
        eaten_cal = round(sum(l.calories for l in food_logs), 1)
        eaten_prot = round(sum(l.protein_g for l in food_logs), 1)
        eaten_carbs = round(sum(l.carbs_g for l in food_logs), 1)
        eaten_fat = round(sum(l.fat_g for l in food_logs), 1)

        # Today's water
        r_water = await db.execute(
            select(func.sum(WaterLog.amount_ml))
            .where(WaterLog.user_id == self.user.id)
            .where(WaterLog.date == today)
        )
        water_ml = int(r_water.scalar_one() or 0)

        # Today's health log
        r_hl = await db.execute(
            select(HealthLog)
            .where(HealthLog.user_id == self.user.id)
            .where(HealthLog.date == today)
        )
        health_log = r_hl.scalars().first()

        # Today's health score
        r_hs = await db.execute(
            select(HealthScore)
            .where(HealthScore.user_id == self.user.id)
            .where(HealthScore.date == today)
        )
        health_score_rec = r_hs.scalars().first()

        # Workouts this week
        cutoff = datetime.utcnow() - timedelta(days=7)
        r_wk = await db.execute(
            select(WorkoutSession)
            .where(WorkoutSession.user_id == self.user.id)
            .where(WorkoutSession.completed_at >= cutoff)
            .where(WorkoutSession.completed_at.isnot(None))
            .order_by(WorkoutSession.completed_at.desc())
        )
        recent_workouts = r_wk.scalars().all()

        # Active streaks
        streaks = await get_all_streaks(self.user.id, db)

        return {
            "goals": {
                "calories": round(goals.calories),
                "protein_g": round(goals.protein_g),
                "carbs_g": round(goals.carbs_g),
                "fat_g": round(goals.fat_g),
                "water_ml": round(goals.water_ml),
            },
            "eaten": {
                "calories": eaten_cal,
                "protein_g": eaten_prot,
                "carbs_g": eaten_carbs,
                "fat_g": eaten_fat,
            },
            "remaining": {
                "calories": max(0, round(goals.calories - eaten_cal)),
                "protein_g": max(0, round(goals.protein_g - eaten_prot, 1)),
            },
            "water_ml": water_ml,
            "health_log": {
                "mood": health_log.mood,
                "energy": health_log.energy,
                "sleep_hours": health_log.sleep_hours,
                "stress_level": health_log.stress_level,
            } if health_log else None,
            "health_score": health_score_rec.total if health_score_rec else None,
            "workout_count_week": len(recent_workouts),
            "last_workout": recent_workouts[0].started_at.strftime("%A") if recent_workouts else None,
            "streaks": {k: v["current_streak"] for k, v in streaks.items()},
        }

    # ── System prompt builder ──────────────────────────────────────────────────

    def build_system_prompt(self, context: dict) -> str:
        u = self.user
        g = context["goals"]
        e = context["eaten"]
        r = context["remaining"]
        streaks = context["streaks"]
        hs = context.get("health_score")
        wc = context.get("workout_count_week", 0)

        streak_str = ", ".join(
            f"{k}: {v}d" for k, v in streaks.items() if v and v > 0
        ) or "none yet"

        mood_str = ""
        if context.get("health_log"):
            hl = context["health_log"]
            mood_str = (
                f"\n       - Mood: {hl['mood']}/5, Energy: {hl['energy']}/5, "
                f"Sleep: {hl['sleep_hours']}h, Stress: {hl['stress_level']}/5"
            )

        return (
            "You are FitAI, an expert personal AI fitness coach and nutritionist.\n"
            f"You are talking with {u.name}.\n\n"
            "Their profile:\n"
            f"  - Goal: {u.goal}\n"
            f"  - Age: {u.age}, Weight: {u.weight_kg} kg, Height: {u.height_cm} cm\n"
            f"  - Activity level: {u.activity_level}\n"
            f"  - Level: {u.level} ({u.xp} XP)\n\n"
            "Today's status:\n"
            f"  - Calories: {e['calories']}/{g['calories']} eaten "
            f"({r['calories']} remaining)\n"
            f"  - Protein: {e['protein_g']}/{g['protein_g']} g\n"
            f"  - Carbs: {e['carbs_g']}/{g['carbs_g']} g\n"
            f"  - Fat: {e['fat_g']}/{g['fat_g']} g\n"
            f"  - Water: {context['water_ml']}/{g['water_ml']} ml\n"
            f"  - Workouts this week: {wc}"
            f"{mood_str}\n"
            f"  - Health score: {hs if hs is not None else 'not calculated yet'}/100\n"
            f"  - Active streaks: {streak_str}\n\n"
            "Your personality:\n"
            f"  - Motivating, knowledgeable, and concise\n"
            f"  - Use {u.name}'s name occasionally\n"
            "  - Give specific, actionable advice based on their current data\n"
            "  - Celebrate their wins and gently push them toward their goals\n"
            "  - Keep responses under 200 words unless explaining something complex\n"
            "  - If they send a food photo, analyze it and offer to log it\n\n"
            "You can trigger app actions by ending your response with ONE action line:\n"
            "  ACTION:LOG_FOOD:{food_name}:{calories}\n"
            "  ACTION:START_WORKOUT\n"
            "  ACTION:LOG_WATER:{ml}\n"
            "Only include an action line if the user explicitly wants to log something."
        )

    # ── Streaming ──────────────────────────────────────────────────────────────

    async def stream_response(
        self,
        messages: List[dict],
        image_base64: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream an AI response as SSE events.

        messages must already include the system message as the first entry.
        Yields "data: {...}\\n\\n" strings. The final event has done=True and
        includes '_r' (full response text) for the route to save to DB.
        """
        model = "llava" if image_base64 else "llama3"

        # If image provided, inject analysis instruction into the last user message
        if image_base64:
            msgs = []
            for m in messages:
                msgs.append(dict(m))
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i].get("role") == "user":
                    msgs[i]["content"] = (
                        "The user sent a food image. Analyse what you see — "
                        "identify the food, estimate the calories and macros. "
                        "Offer to log it for them.\n\n"
                        + (msgs[i].get("content") or "")
                    )
                    break
        else:
            msgs = messages

        full_response = ""
        try:
            gen = await self.ollama.chat(
                model=model,
                messages=msgs,
                images=[image_base64] if image_base64 else None,
                stream=True,
            )
            async for token in gen:
                full_response += token
                yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
        except Exception as exc:
            logger.error(f"Ollama streaming error: {exc}")
            error_msg = "Sorry, I'm having trouble connecting to my AI engine right now. Please try again in a moment."
            full_response = error_msg
            yield f"data: {json.dumps({'token': error_msg, 'done': False})}\n\n"

        action = self.parse_action(full_response)
        # _r carries the full response back to the route for DB saving;
        # the route strips it before forwarding the event to the client.
        yield f"data: {json.dumps({'token': '', 'done': True, 'action': action, '_r': full_response})}\n\n"

    # ── Action parser ──────────────────────────────────────────────────────────

    def parse_action(self, full_response: str) -> Optional[dict]:
        """
        Detect an ACTION: directive at the end of the model's response.
        Returns a structured dict or None if no action found.
        """
        # Look for the last occurrence of ACTION: in the response
        m = re.search(
            r"ACTION:(LOG_FOOD:[^\n]+|START_WORKOUT|LOG_WATER:\d+)",
            full_response,
        )
        if not m:
            return None

        action_str = m.group(1)

        if action_str.startswith("LOG_FOOD:"):
            parts = action_str[9:].rsplit(":", 1)
            food_name = parts[0].strip() if len(parts) == 2 else action_str[9:].strip()
            try:
                calories = float(parts[1]) if len(parts) == 2 else 0.0
            except ValueError:
                calories = 0.0
            return {"type": "LOG_FOOD", "food_name": food_name, "calories": calories}

        if action_str == "START_WORKOUT":
            return {"type": "START_WORKOUT"}

        if action_str.startswith("LOG_WATER:"):
            try:
                ml = int(action_str[10:])
            except ValueError:
                ml = 0
            return {"type": "LOG_WATER", "ml": ml}

        return None
