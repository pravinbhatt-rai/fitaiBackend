from __future__ import annotations

from typing import Any
from models import get_model
from inference.workout_model import WorkoutRecommender
from inference.nutrition_model import NutritionAnalyzer
from preprocessing.normalizer import build_food_embedding
from utils.cache import cached
from utils.logger import get_logger

logger = get_logger(__name__)


class RecommendationEngine:
    """High-level async facade over the ML models."""

    @cached(prefix="workout_plan", ttl=600)
    async def get_workout_plan(
        self,
        user_id: str,
        preferences: dict[str, Any],
        top_k: int = 5,
    ) -> list[dict]:
        recommender: WorkoutRecommender = get_model("workout")  # type: ignore[assignment]
        raw = await recommender.recommend(preferences, top_k=top_k)
        logger.info("recommendation.workout", user_id=user_id, count=len(raw))
        return raw

    @cached(prefix="meal_plan", ttl=3600)
    async def get_meal_plan(
        self,
        user_id: str,
        goals: dict[str, Any],
        days: int = 7,
    ) -> list[list[dict]]:
        analyzer: NutritionAnalyzer = get_model("nutrition")  # type: ignore[assignment]
        plan = await analyzer.estimate_meal_plan(goals, days=days)
        logger.info("recommendation.meal_plan", user_id=user_id, days=days)
        return plan

    async def analyze_food(self, food: dict[str, Any]) -> dict[str, float]:
        analyzer: NutritionAnalyzer = get_model("nutrition")  # type: ignore[assignment]
        embedding = build_food_embedding(food)
        return await analyzer.analyze(embedding)


recommendation_engine = RecommendationEngine()
