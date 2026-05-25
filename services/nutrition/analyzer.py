import json
import re
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from models.user import User
from services.ollama.client import OllamaClient
from utils.logger import get_logger

logger = get_logger("fitai.nutrition.analyzer")

_ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

_JSON_SCHEMA = (
    '{"food_name": "string", "calories": number, "protein_g": number, '
    '"carbs_g": number, "fat_g": number, "fiber_g": number, "sugar_g": number, '
    '"serving_size_g": number, "confidence": number_between_0_and_1, "notes": "string"}'
)


class FoodAnalysis(BaseModel):
    food_name: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugar_g: float
    serving_size_g: float
    confidence: float
    notes: str


class DailyGoals(BaseModel):
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    water_ml: float


def _extract_json(text: str) -> dict:
    """Pull the first valid JSON object out of an LLM response."""
    text = text.strip()
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown code fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Find outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON object found in LLM response (first 300 chars): {text[:300]!r}")


async def analyze_food_image(
    image_base64: str,
    weight_grams: Optional[float],
    ollama: OllamaClient,
) -> FoodAnalysis:
    weight_note = (
        f"The food weighs exactly {weight_grams}g. Calculate macros for that precise weight."
        if weight_grams
        else "Estimate the serving size from what is visible in the image."
    )

    def _build_prompt(strict: bool = False) -> str:
        if strict:
            return (
                f"Analyze this food image. Output ONLY a JSON object — no text before or after, "
                f"no markdown fences. Required schema:\n{_JSON_SCHEMA}\n{weight_note}"
            )
        return (
            "You are an expert nutritionist AI. Analyze the food in the image.\n"
            f"{weight_note}\n"
            "Respond ONLY with valid JSON matching this schema exactly:\n"
            f"{_JSON_SCHEMA}\n"
            "No extra text, no markdown, just the JSON object."
        )

    last_exc: Exception = RuntimeError("unreachable")
    for attempt in range(2):
        prompt = _build_prompt(strict=attempt == 1)
        try:
            raw = await ollama.chat(
                model="llava",
                messages=[{"role": "user", "content": prompt}],
                images=[image_base64],
                stream=False,
            )
            return FoodAnalysis(**_extract_json(raw))
        except (ValueError, KeyError, TypeError, Exception) as exc:
            last_exc = exc
            logger.warning(f"Image analysis attempt {attempt + 1} failed: {exc}")

    raise HTTPException(
        status_code=422,
        detail=f"Could not extract nutritional data from image: {last_exc}",
    )


async def analyze_food_text(
    description: str,
    weight_grams: Optional[float],
    ollama: OllamaClient,
) -> FoodAnalysis:
    weight_note = (
        f"The serving weighs exactly {weight_grams}g. Calculate macros for that precise weight."
        if weight_grams
        else "Estimate the standard serving size."
    )

    def _build_prompt(strict: bool = False) -> str:
        if strict:
            return (
                f'Food: "{description}"\n{weight_note}\n'
                f"Output ONLY a JSON object matching this schema:\n{_JSON_SCHEMA}"
            )
        return (
            f'You are an expert nutritionist AI. Analyze this food: "{description}"\n'
            f"{weight_note}\n"
            "Respond ONLY with valid JSON matching this schema exactly:\n"
            f"{_JSON_SCHEMA}\n"
            "No extra text, no markdown, just the JSON object."
        )

    last_exc: Exception = RuntimeError("unreachable")
    for attempt in range(2):
        prompt = _build_prompt(strict=attempt == 1)
        try:
            raw = await ollama.chat(
                model="llama3",
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            return FoodAnalysis(**_extract_json(raw))
        except (ValueError, KeyError, TypeError, Exception) as exc:
            last_exc = exc
            logger.warning(f"Text analysis attempt {attempt + 1} failed for '{description}': {exc}")

    raise HTTPException(
        status_code=422,
        detail=f"Could not extract nutritional data for '{description}': {last_exc}",
    )


def calculate_daily_goals(user: User) -> DailyGoals:
    sex = (user.sex or "").strip().lower()
    if sex == "female":
        bmr = 447.593 + (9.247 * user.weight_kg) + (3.098 * user.height_cm) - (4.330 * user.age)
    else:
        bmr = 88.362 + (13.397 * user.weight_kg) + (4.799 * user.height_cm) - (5.677 * user.age)

    multiplier = _ACTIVITY_MULTIPLIERS.get(user.activity_level, 1.55)
    tdee = bmr * multiplier

    # (calories, protein_pct, carbs_pct, fat_pct)
    _macro_profiles = {
        "lose_weight":    (tdee - 500, 0.40, 0.30, 0.30),
        "build_muscle":   (tdee + 300, 0.35, 0.45, 0.20),
        "stay_fit":       (tdee,       0.30, 0.40, 0.30),
        "improve_health": (tdee,       0.25, 0.50, 0.25),
    }
    goal = user.goal or "stay_fit"
    calories, p_pct, c_pct, f_pct = _macro_profiles.get(goal, _macro_profiles["stay_fit"])

    protein_g = (calories * p_pct) / 4
    carbs_g   = (calories * c_pct) / 4
    fat_g     = (calories * f_pct) / 9
    fiber_g   = calories / 1000 * 14   # DRI guideline: 14 g per 1 000 kcal
    water_ml  = user.weight_kg * 35    # 35 ml / kg body weight

    return DailyGoals(
        calories=round(calories, 1),
        protein_g=round(protein_g, 1),
        carbs_g=round(carbs_g, 1),
        fat_g=round(fat_g, 1),
        fiber_g=round(fiber_g, 1),
        water_ml=round(water_ml, 1),
    )
