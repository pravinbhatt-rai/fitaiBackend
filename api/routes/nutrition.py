import base64
import io
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from PIL import Image as PILImage
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.dependencies import get_ollama
from api.middleware.auth import get_current_user
from models.nutrition import FoodLog, WaterLog
from models.user import User
from services.achievements.engine import check_and_award
from services.nutrition.analyzer import (
    DailyGoals,
    FoodAnalysis,
    analyze_food_image,
    analyze_food_text,
    calculate_daily_goals,
)
from services.nutrition.meal_planner import MealPlan, generate_meal_plan
from services.ollama.client import OllamaClient
from utils.database import get_session
from utils.logger import get_logger

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])
logger = get_logger("fitai.routes.nutrition")

_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_MIME = {"image/jpeg", "image/png"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _auto_meal_type() -> str:
    from datetime import datetime
    h = datetime.now().hour
    if 5 <= h < 11:
        return "breakfast"
    if 11 <= h < 15:
        return "lunch"
    if 15 <= h < 18:
        return "snack"
    if 18 <= h < 22:
        return "dinner"
    return "snack"




async def _read_and_validate_image(file: UploadFile) -> bytes:
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only JPEG and PNG images are accepted (got {file.content_type})",
        )
    data = await file.read()
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image must be smaller than 10 MB",
        )
    try:
        img = PILImage.open(io.BytesIO(data))
        img.verify()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid image",
        ) from exc
    return data


def _log_from_analysis(
    user_id: int,
    analysis: FoodAnalysis,
    meal_type: str,
) -> FoodLog:
    return FoodLog(
        user_id=user_id,
        date=date.today(),
        meal_type=meal_type,
        food_name=analysis.food_name,
        calories=analysis.calories,
        protein_g=analysis.protein_g,
        carbs_g=analysis.carbs_g,
        fat_g=analysis.fat_g,
        fiber_g=analysis.fiber_g,
        sugar_g=analysis.sugar_g,
        weight_grams=analysis.serving_size_g,
    )


# ── Request / Response schemas ────────────────────────────────────────────────

class LogTextRequest(BaseModel):
    description: str
    weight_grams: Optional[float] = None
    meal_type: Optional[str] = None


class LogImageResponse(BaseModel):
    analysis: FoodAnalysis
    log_id: int
    meal_type: str


class LogTextResponse(BaseModel):
    analysis: FoodAnalysis
    log_id: int
    meal_type: str


class WaterLogRequest(BaseModel):
    amount_ml: int


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/log/image", response_model=LogImageResponse, status_code=status.HTTP_201_CREATED)
async def log_food_image(
    file: UploadFile = File(...),
    weight_grams: Optional[float] = Form(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ollama: OllamaClient = Depends(get_ollama),
):
    data = await _read_and_validate_image(file)
    image_b64 = base64.b64encode(data).decode("utf-8")

    analysis = await analyze_food_image(image_b64, weight_grams, ollama)

    meal_type = _auto_meal_type()
    log = _log_from_analysis(current_user.id, analysis, meal_type)
    session.add(log)
    await session.flush()
    await session.refresh(log)

    new_achievements = await check_and_award(
        current_user.id, "food_logged", {"is_photo": True}, session
    )

    return LogImageResponse(analysis=analysis, log_id=log.id, meal_type=meal_type)


@router.post("/log/text", response_model=LogTextResponse, status_code=status.HTTP_201_CREATED)
async def log_food_text(
    req: LogTextRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ollama: OllamaClient = Depends(get_ollama),
):
    analysis = await analyze_food_text(req.description, req.weight_grams, ollama)

    meal_type = req.meal_type or _auto_meal_type()
    log = _log_from_analysis(current_user.id, analysis, meal_type)
    session.add(log)
    await session.flush()
    await session.refresh(log)

    new_achievements = await check_and_award(
        current_user.id, "food_logged", {"is_photo": False}, session
    )

    return LogTextResponse(analysis=analysis, log_id=log.id, meal_type=meal_type)


@router.get("/today")
async def get_today(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    today = date.today()

    food_result = await session.execute(
        select(FoodLog)
        .where(FoodLog.user_id == current_user.id)
        .where(FoodLog.date == today)
        .order_by(FoodLog.logged_at)
    )
    logs = food_result.scalars().all()

    goals = calculate_daily_goals(current_user)

    grouped: dict = {"breakfast": [], "lunch": [], "dinner": [], "snacks": []}
    totals = {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "fiber_g": 0.0}

    for log in logs:
        entry = {
            "id": log.id,
            "food_name": log.food_name,
            "meal_type": log.meal_type,
            "calories": log.calories,
            "protein_g": log.protein_g,
            "carbs_g": log.carbs_g,
            "fat_g": log.fat_g,
            "fiber_g": log.fiber_g,
            "sugar_g": log.sugar_g,
            "weight_grams": log.weight_grams,
            "logged_at": log.logged_at.isoformat(),
        }
        bucket = log.meal_type if log.meal_type in ("breakfast", "lunch", "dinner") else "snacks"
        grouped[bucket].append(entry)

        totals["calories"] += log.calories
        totals["protein_g"] += log.protein_g
        totals["carbs_g"] += log.carbs_g
        totals["fat_g"] += log.fat_g
        totals["fiber_g"] += log.fiber_g

    water_result = await session.execute(
        select(WaterLog)
        .where(WaterLog.user_id == current_user.id)
        .where(WaterLog.date == today)
    )
    water_today = sum(w.amount_ml for w in water_result.scalars().all())

    remaining = {
        "calories": max(0.0, goals.calories - totals["calories"]),
        "protein_g": max(0.0, goals.protein_g - totals["protein_g"]),
        "carbs_g": max(0.0, goals.carbs_g - totals["carbs_g"]),
        "fat_g": max(0.0, goals.fat_g - totals["fat_g"]),
    }

    def _pct(actual: float, goal: float) -> float:
        return round(min(actual / goal * 100.0, 100.0), 1) if goal > 0 else 0.0

    return {
        "date": today.isoformat(),
        "goals": goals.model_dump(),
        "logs": grouped,
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "remaining": {k: round(v, 1) for k, v in remaining.items()},
        "progress_pct": {
            "calories": _pct(totals["calories"], goals.calories),
            "protein":  _pct(totals["protein_g"], goals.protein_g),
            "carbs":    _pct(totals["carbs_g"], goals.carbs_g),
            "fat":      _pct(totals["fat_g"], goals.fat_g),
        },
        "water_ml_today": round(water_today, 1),
        "water_goal_ml": goals.water_ml,
    }


@router.get("/history")
async def nutrition_history(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from_date = date.today() - timedelta(days=days - 1)

    result = await session.execute(
        select(FoodLog)
        .where(FoodLog.user_id == current_user.id)
        .where(FoodLog.date >= from_date)
        .order_by(FoodLog.date)
    )
    logs = result.scalars().all()

    goals = calculate_daily_goals(current_user)
    daily: dict[str, dict] = {}

    for log in logs:
        d = str(log.date)
        if d not in daily:
            daily[d] = {"date": d, "calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
        daily[d]["calories"]  += log.calories
        daily[d]["protein_g"] += log.protein_g
        daily[d]["carbs_g"]   += log.carbs_g
        daily[d]["fat_g"]     += log.fat_g

    history = []
    for d_str, t in sorted(daily.items()):
        adherence = (t["calories"] / goals.calories * 100.0) if goals.calories > 0 else 0.0
        history.append({
            "date":         d_str,
            "calories":     round(t["calories"],  1),
            "protein_g":    round(t["protein_g"], 1),
            "carbs_g":      round(t["carbs_g"],   1),
            "fat_g":        round(t["fat_g"],      1),
            "adherence_pct": round(min(adherence, 100.0), 1),
        })

    return history


@router.get("/meal-plan", response_model=MealPlan)
async def get_meal_plan(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ollama: OllamaClient = Depends(get_ollama),
):
    today = date.today()
    goals = calculate_daily_goals(current_user)

    result = await session.execute(
        select(FoodLog)
        .where(FoodLog.user_id == current_user.id)
        .where(FoodLog.date == today)
    )
    already_eaten = result.scalars().all()

    return await generate_meal_plan(current_user, goals, list(already_eaten), ollama)


@router.delete("/log/{log_id}")
async def delete_food_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(FoodLog)
        .where(FoodLog.id == log_id)
        .where(FoodLog.user_id == current_user.id)
    )
    log = result.scalars().first()
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Food log entry not found",
        )
    await session.delete(log)
    return {"deleted": True}


@router.get("/goals")
async def get_goals(current_user: User = Depends(get_current_user)):
    return calculate_daily_goals(current_user).model_dump()


@router.post("/water", status_code=status.HTTP_201_CREATED)
async def log_water(
    req: WaterLogRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    today = date.today()

    entry = WaterLog(user_id=current_user.id, date=today, amount_ml=float(req.amount_ml))
    session.add(entry)
    await session.flush()

    await check_and_award(current_user.id, "water_logged", {}, session)

    result = await session.execute(
        select(WaterLog)
        .where(WaterLog.user_id == current_user.id)
        .where(WaterLog.date == today)
    )
    total_today = sum(w.amount_ml for w in result.scalars().all())

    goals = calculate_daily_goals(current_user)
    progress = round(min(total_today / goals.water_ml * 100.0, 100.0), 1) if goals.water_ml else 0.0

    return {
        "total_today_ml": int(total_today),
        "goal_ml": int(goals.water_ml),
        "progress_pct": progress,
    }


@router.get("/water/today")
async def get_water_today(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    today = date.today()

    result = await session.execute(
        select(WaterLog)
        .where(WaterLog.user_id == current_user.id)
        .where(WaterLog.date == today)
        .order_by(WaterLog.logged_at)
    )
    logs = result.scalars().all()
    total_ml = sum(w.amount_ml for w in logs)

    goals = calculate_daily_goals(current_user)

    return {
        "total_ml": int(total_ml),
        "goal_ml": int(goals.water_ml),
        "logs": [
            {"amount_ml": int(w.amount_ml), "logged_at": w.logged_at.isoformat()}
            for w in logs
        ],
    }
