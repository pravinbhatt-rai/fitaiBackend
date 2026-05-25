from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from utils.logger import get_logger
from utils.config import get_settings

logger = get_logger(__name__)

MUSCLE_GROUPS = ["chest", "back", "shoulders", "biceps", "triceps", "legs", "core"]
DIFFICULTY_LEVELS = ["beginner", "intermediate", "advanced"]


class WorkoutEmbeddingNet(nn.Module):
    """Lightweight embedding network for workout recommendation."""

    def __init__(self, input_dim: int = 32, hidden_dim: int = 128, output_dim: int = 64):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.encoder(x)


class WorkoutRecommender:
    """Wraps WorkoutEmbeddingNet and exposes async prediction API."""

    def __init__(self, device: torch.device):
        self.device = device
        self.model: WorkoutEmbeddingNet | None = None
        self._lock = asyncio.Lock()

    def load(self, weights_path: Path | None = None) -> None:
        settings = get_settings()
        self.model = WorkoutEmbeddingNet().to(self.device)

        if weights_path and weights_path.exists():
            state = torch.load(weights_path, map_location=self.device)
            self.model.load_state_dict(state)
            logger.info("workout_model.loaded", path=str(weights_path))
        else:
            logger.warning("workout_model.no_weights", note="Using randomly initialised weights")

        self.model.eval()

    def _build_feature_vector(self, preferences: dict[str, Any]) -> torch.Tensor:
        """Encode user preferences into a fixed-size float tensor."""
        vec = torch.zeros(32, dtype=torch.float32)

        goal_map = {"lose_weight": 0, "build_muscle": 1, "maintain": 2, "improve_endurance": 3}
        goal_idx = goal_map.get(preferences.get("fitness_goal", ""), -1)
        if goal_idx >= 0:
            vec[goal_idx] = 1.0

        activity_map = {"sedentary": 0, "lightly_active": 1, "moderately_active": 2, "very_active": 3}
        activity_idx = activity_map.get(preferences.get("activity_level", ""), -1)
        if activity_idx >= 0:
            vec[4 + activity_idx] = 1.0

        for i, mg in enumerate(MUSCLE_GROUPS):
            if mg in preferences.get("target_muscles", []):
                vec[8 + i] = 1.0

        diff_idx = DIFFICULTY_LEVELS.index(preferences.get("difficulty", "beginner"))
        vec[15 + diff_idx] = 1.0

        vec[18] = float(preferences.get("available_minutes", 45)) / 120.0
        vec[19] = float(preferences.get("sessions_per_week", 3)) / 7.0

        return vec.unsqueeze(0).to(self.device)

    async def recommend(self, preferences: dict[str, Any], top_k: int = 5) -> list[dict]:
        if self.model is None:
            raise RuntimeError("WorkoutRecommender not loaded. Call load() first.")

        async with self._lock:
            start = time.perf_counter()
            feature_vec = self._build_feature_vector(preferences)

            with torch.no_grad():
                embedding = self.model(feature_vec)

            latency_ms = (time.perf_counter() - start) * 1000
            logger.info("workout_model.inferred", latency_ms=round(latency_ms, 2))

            scores = torch.sigmoid(embedding).squeeze().cpu().tolist()
            if isinstance(scores, float):
                scores = [scores]

        return [
            {
                "workout_id": f"workout_{i}",
                "score": round(float(s), 4),
                "difficulty": DIFFICULTY_LEVELS[i % 3],
            }
            for i, s in enumerate(sorted(scores, reverse=True)[:top_k])
        ]
