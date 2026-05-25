from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.middleware.auth import get_current_user
from models.user import User
from utils.auth import create_access_token, hash_password, verify_password
from utils.database import get_session

router = APIRouter(prefix="/api/user", tags=["user"])


# ── Request / Response schemas ───────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    age: int
    weight_kg: float
    height_cm: float
    sex: str
    goal: str
    activity_level: str
    wake_time: str = "07:00"
    equipment: List[str] = []


class LoginRequest(BaseModel):
    email: str
    password: str


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    sex: Optional[str] = None
    goal: Optional[str] = None
    activity_level: Optional[str] = None
    wake_time: Optional[str] = None
    equipment: Optional[List[str]] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    age: int
    weight_kg: float
    height_cm: float
    sex: str
    goal: str
    activity_level: str
    wake_time: str
    equipment: List[str] = []
    xp: int
    level: int
    created_at: datetime

    @field_validator("equipment", mode="before")
    @classmethod
    def _normalize_equipment(cls, v: Any) -> List[str]:
        return v if v is not None else []


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.email == req.email))
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        name=req.name,
        age=req.age,
        weight_kg=req.weight_kg,
        height_cm=req.height_cm,
        sex=req.sex,
        goal=req.goal,
        activity_level=req.activity_level,
        wake_time=req.wake_time,
        equipment=req.equipment,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()

    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    updates = req.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(current_user, field, value)
    current_user.updated_at = datetime.utcnow()

    session.add(current_user)
    await session.flush()
    await session.refresh(current_user)

    return UserResponse.model_validate(current_user)
