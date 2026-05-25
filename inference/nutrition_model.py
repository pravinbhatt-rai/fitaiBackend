from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from utils.logger import get_logger

logger = get_logger(__name__)

MACRO_FIELDS = ["calories", "protein", "carbs", "fat", "fiber"]


class MacroEstimatorNet(nn.Module):
    """Predicts macro-nutrient content from food embedding."""

    def __init__(self, input_dim: int = 64, hidden_dim: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.15),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Linear(hidden_dim // 2, len(MACRO_FIELDS)),
            nn.ReLU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class NutritionAnalyzer:
    """Wraps MacroEstimatorNet with async predict API."""

    def __init__(self, device: torch.device):
        self.device = device
        self.model: MacroEstimatorNet | None = None
        self._lock = asyncio.Lock()

    def load(self, weights_path: Path | None = None) -> None:
        self.model = MacroEstimatorNet().to(self.device)

        if weights_path and weights_path.exists():
            state = torch.load(weights_path, map_location=self.device)
            self.model.load_state_dict(state)
            logger.info("nutrition_model.loaded", path=str(weights_path))
        else:
            logger.warning("nutrition_model.no_weights", note="Using randomly initialised weights")

        self.model.eval()

    async def analyze(self, food_embedding: list[float]) -> dict[str, float]:
        if self.model is None:
            raise RuntimeError("NutritionAnalyzer not loaded.")

        async with self._lock:
            start = time.perf_counter()
            x = torch.tensor(food_embedding, dtype=torch.float32).unsqueeze(0).to(self.device)

            with torch.no_grad():
                preds = self.model(x).squeeze().cpu().tolist()

            latency_ms = (time.perf_counter() - start) * 1000
            logger.info("nutrition_model.inferred", latency_ms=round(latency_ms, 2))

        return {field: round(float(v), 2) for field, v in zip(MACRO_FIELDS, preds)}

    async def estimate_meal_plan(
        self,
        goals: dict[str, Any],
        days: int = 7,
    ) -> list[list[dict]]:
        """Return a simple template meal plan based on calorie/macro targets."""
        calories_target = goals.get("calories", 2000)
        meals_per_day = goals.get("meals_per_day", 3)

        cal_per_meal = calories_target / meals_per_day
        plan: list[list[dict]] = []

        for _ in range(days):
            day_meals = [
                {
                    "name": f"Meal {m + 1}",
                    "calories": round(cal_per_meal),
                    "protein": round(goals.get("protein", 150) / meals_per_day),
                    "carbs": round(goals.get("carbs", 200) / meals_per_day),
                    "fat": round(goals.get("fat", 65) / meals_per_day),
                }
                for m in range(meals_per_day)
            ]
            plan.append(day_meals)

        return plan
