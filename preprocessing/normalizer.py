from __future__ import annotations

import re


def normalize_food_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[^\w\s]", "", name)
    return name


def normalize_weight(value: float, unit: str) -> float:
    """Return weight in kilograms."""
    conversions = {
        "kg": 1.0,
        "g": 0.001,
        "lbs": 0.453592,
        "lb": 0.453592,
        "oz": 0.0283495,
    }
    return value * conversions.get(unit.lower(), 1.0)


def clip_macros(value: float, macro: str) -> float:
    limits = {
        "calories": (0, 5000),
        "protein": (0, 500),
        "carbs": (0, 800),
        "fat": (0, 400),
        "fiber": (0, 200),
    }
    lo, hi = limits.get(macro, (0, 9999))
    return max(lo, min(hi, value))


def build_food_embedding(food: dict) -> list[float]:
    """Encode a food dict into a 64-dim float vector for the model."""
    macros = food.get("macros", {})
    vec = [0.0] * 64
    vec[0] = clip_macros(macros.get("calories", 0), "calories") / 5000.0
    vec[1] = clip_macros(macros.get("protein", 0), "protein") / 500.0
    vec[2] = clip_macros(macros.get("carbs", 0), "carbs") / 800.0
    vec[3] = clip_macros(macros.get("fat", 0), "fat") / 400.0
    vec[4] = clip_macros(macros.get("fiber", 0), "fiber") / 200.0
    return vec
