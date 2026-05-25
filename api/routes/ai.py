from __future__ import annotations

import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Any, Literal

from api.dependencies.auth import get_current_user_id
from recommendation.engine import recommendation_engine
from nutrition.calculator import compute_macro_targets, ActivityLevel, FitnessGoal
from utils.logger import get_logger

router = APIRouter(prefix="/ai", tags=["ai"])
logger = get_logger(__name__)


class WorkoutPlanRequest(BaseModel):
    fitness_goal: FitnessGoal = "build_muscle"
    activity_level: ActivityLevel = "moderately_active"
    difficulty: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    target_muscles: list[str] = Field(default_factory=list)
    available_minutes: int = Field(45, ge=10, le=180)
    sessions_per_week: int = Field(3, ge=1, le=7)
    top_k: int = Field(5, ge=1, le=20)


class MealPlanRequest(BaseModel):
    weight_kg: float = Field(..., gt=0, le=300)
    height_cm: float = Field(..., gt=0, le=250)
    age_years: int = Field(..., ge=10, le=100)
    sex: Literal["male", "female"] = "male"
    activity_level: ActivityLevel = "moderately_active"
    fitness_goal: FitnessGoal = "maintain"
    days: int = Field(7, ge=1, le=14)


class FoodAnalysisRequest(BaseModel):
    name: str
    macros: dict[str, float] = Field(default_factory=dict)


@router.post("/workout-plan")
async def get_workout_plan(
    body: WorkoutPlanRequest,
    user_id: str = Depends(get_current_user_id),
):
    try:
        plan = await asyncio.wait_for(
            recommendation_engine.get_workout_plan(
                user_id=user_id,
                preferences=body.model_dump(),
                top_k=body.top_k,
            ),
            timeout=30,
        )
        return {"data": plan, "success": True, "message": "Workout plan generated"}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Inference timeout")
    except Exception as exc:
        logger.error("ai.workout_plan.error", error=str(exc))
        raise HTTPException(status_code=500, detail="Inference failed")


@router.post("/meal-plan")
async def get_meal_plan(
    body: MealPlanRequest,
    user_id: str = Depends(get_current_user_id),
):
    macro_targets = compute_macro_targets(
        weight_kg=body.weight_kg,
        height_cm=body.height_cm,
        age_years=body.age_years,
        sex=body.sex,
        activity_level=body.activity_level,
        goal=body.fitness_goal,
    )

    try:
        plan = await asyncio.wait_for(
            recommendation_engine.get_meal_plan(
                user_id=user_id,
                goals={
                    "calories": macro_targets.calories,
                    "protein": macro_targets.protein_g,
                    "carbs": macro_targets.carbs_g,
                    "fat": macro_targets.fat_g,
                    "meals_per_day": 3,
                },
                days=body.days,
            ),
            timeout=30,
        )
        return {
            "data": {"plan": plan, "targets": macro_targets.__dict__},
            "success": True,
            "message": "Meal plan generated",
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Inference timeout")


@router.post("/analyze-food")
async def analyze_food(
    body: FoodAnalysisRequest,
    user_id: str = Depends(get_current_user_id),
):
    result = await recommendation_engine.analyze_food(body.model_dump())
    return {"data": result, "success": True, "message": "Food analyzed"}


@router.post("/macro-targets")
async def get_macro_targets(
    body: MealPlanRequest,
    user_id: str = Depends(get_current_user_id),
):
    targets = compute_macro_targets(
        weight_kg=body.weight_kg,
        height_cm=body.height_cm,
        age_years=body.age_years,
        sex=body.sex,
        activity_level=body.activity_level,
        goal=body.fitness_goal,
    )
    return {"data": targets.__dict__, "success": True, "message": "Macro targets calculated"}
