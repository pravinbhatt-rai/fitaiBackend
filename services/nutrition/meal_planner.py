import json
import re
from datetime import date, datetime
from typing import List

from pydantic import BaseModel

from models.nutrition import FoodLog
from models.user import User
from services.nutrition.analyzer import DailyGoals
from services.ollama.client import OllamaClient
from utils.logger import get_logger

logger = get_logger("fitai.nutrition.meal_planner")


class MealItem(BaseModel):
    meal_type: str  # breakfast | lunch | dinner | snack1 | snack2
    name: str
    description: str
    target_calories: float
    target_protein_g: float
    target_carbs_g: float
    target_fat_g: float
    prep_time_mins: int
    ingredients: List[str]


class MealPlan(BaseModel):
    date: str
    total_calories: float
    meals: List[MealItem]
    notes: str


_MEAL_SCHEMA = (
    '{"date": "YYYY-MM-DD", "total_calories": number, "meals": ['
    '{"meal_type": "string", "name": "string", "description": "string", '
    '"target_calories": number, "target_protein_g": number, "target_carbs_g": number, '
    '"target_fat_g": number, "prep_time_mins": number, '
    '"ingredients": ["string", ...]}], "notes": "string"}'
)


def _meals_still_needed(eaten_types: set) -> List[str]:
    hour = datetime.now().hour
    if hour < 10:
        candidates = ["breakfast", "lunch", "dinner", "snack1"]
    elif hour < 13:
        candidates = ["lunch", "dinner", "snack1"]
    elif hour < 17:
        candidates = ["dinner", "snack1", "snack2"]
    elif hour < 20:
        candidates = ["dinner", "snack2"]
    else:
        candidates = ["snack2"]
    return [m for m in candidates if m not in eaten_types]


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
    raise ValueError("No valid JSON object in LLM response")


def _fallback_plan(
    meals_needed: List[str],
    remaining_calories: float,
    remaining_protein: float,
    remaining_carbs: float,
    remaining_fat: float,
) -> MealPlan:
    n = max(len(meals_needed), 1)
    return MealPlan(
        date=date.today().isoformat(),
        total_calories=round(remaining_calories, 1),
        meals=[
            MealItem(
                meal_type=m,
                name=m.replace("snack1", "snack").replace("snack2", "snack").capitalize(),
                description="A balanced meal to help meet your remaining daily targets.",
                target_calories=round(remaining_calories / n, 1),
                target_protein_g=round(remaining_protein / n, 1),
                target_carbs_g=round(remaining_carbs / n, 1),
                target_fat_g=round(remaining_fat / n, 1),
                prep_time_mins=20,
                ingredients=["Choose whole foods that fit your macro targets"],
            )
            for m in meals_needed
        ],
        notes="AI could not generate a detailed plan — showing equal-split fallback. Try again shortly.",
    )


async def generate_meal_plan(
    user: User,
    goals: DailyGoals,
    already_eaten: List[FoodLog],
    ollama: OllamaClient,
) -> MealPlan:
    eaten_cal  = sum(f.calories  for f in already_eaten)
    eaten_prot = sum(f.protein_g for f in already_eaten)
    eaten_carb = sum(f.carbs_g   for f in already_eaten)
    eaten_fat  = sum(f.fat_g     for f in already_eaten)

    rem_cal  = max(0.0, goals.calories  - eaten_cal)
    rem_prot = max(0.0, goals.protein_g - eaten_prot)
    rem_carb = max(0.0, goals.carbs_g   - eaten_carb)
    rem_fat  = max(0.0, goals.fat_g     - eaten_fat)

    eaten_types = {f.meal_type for f in already_eaten}
    meals_needed = _meals_still_needed(eaten_types)

    today = date.today().isoformat()

    if not meals_needed:
        return MealPlan(
            date=today,
            total_calories=round(eaten_cal, 1),
            meals=[],
            notes="All meals for today have already been logged — great work!",
        )

    prompt = (
        "You are a nutritionist. Create a meal plan for the rest of today.\n\n"
        f"User profile:\n"
        f"  Goal: {user.goal}\n"
        f"  Weight: {user.weight_kg} kg\n"
        f"  Activity level: {user.activity_level}\n\n"
        f"Remaining targets for today:\n"
        f"  Calories: {rem_cal:.0f} kcal\n"
        f"  Protein:  {rem_prot:.1f} g\n"
        f"  Carbs:    {rem_carb:.1f} g\n"
        f"  Fat:      {rem_fat:.1f} g\n\n"
        f"Meals still needed: {', '.join(meals_needed)}\n\n"
        "Make meals practical, healthy, and realistic. "
        "Indian cuisine preferred where it fits the macros.\n\n"
        f"Respond ONLY with valid JSON matching this schema:\n{_MEAL_SCHEMA}\n"
        "No extra text, no markdown, just the JSON object."
    )

    try:
        raw = await ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        data = _extract_json(raw)
        return MealPlan(**data)
    except Exception as exc:
        logger.error(f"Meal plan generation failed: {exc}")
        return _fallback_plan(meals_needed, rem_cal, rem_prot, rem_carb, rem_fat)
