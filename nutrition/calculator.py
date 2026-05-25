from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ActivityLevel = Literal[
    "sedentary", "lightly_active", "moderately_active", "very_active", "extremely_active"
]
FitnessGoal = Literal["lose_weight", "build_muscle", "maintain", "improve_endurance"]

ACTIVITY_MULTIPLIERS: dict[ActivityLevel, float] = {
    "sedentary": 1.2,
    "lightly_active": 1.375,
    "moderately_active": 1.55,
    "very_active": 1.725,
    "extremely_active": 1.9,
}

GOAL_ADJUSTMENTS: dict[FitnessGoal, float] = {
    "lose_weight": -500,
    "build_muscle": +300,
    "maintain": 0,
    "improve_endurance": +100,
}


@dataclass
class MacroTargets:
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


def mifflin_st_jeor(
    weight_kg: float,
    height_cm: float,
    age_years: int,
    sex: Literal["male", "female"],
) -> float:
    """Basal Metabolic Rate via Mifflin-St Jeor equation."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age_years
    return base + 5 if sex == "male" else base - 161


def compute_tdee(
    weight_kg: float,
    height_cm: float,
    age_years: int,
    sex: Literal["male", "female"],
    activity_level: ActivityLevel,
) -> float:
    bmr = mifflin_st_jeor(weight_kg, height_cm, age_years, sex)
    return bmr * ACTIVITY_MULTIPLIERS[activity_level]


def compute_macro_targets(
    weight_kg: float,
    height_cm: float,
    age_years: int,
    sex: Literal["male", "female"],
    activity_level: ActivityLevel,
    goal: FitnessGoal,
) -> MacroTargets:
    tdee = compute_tdee(weight_kg, height_cm, age_years, sex, activity_level)
    target_calories = max(1200, tdee + GOAL_ADJUSTMENTS[goal])

    protein_g = weight_kg * (2.2 if goal == "build_muscle" else 1.8)
    fat_g = target_calories * 0.25 / 9
    carbs_g = (target_calories - protein_g * 4 - fat_g * 9) / 4

    return MacroTargets(
        calories=round(target_calories),
        protein_g=round(protein_g, 1),
        carbs_g=round(max(carbs_g, 0), 1),
        fat_g=round(fat_g, 1),
    )
