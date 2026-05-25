from __future__ import annotations

from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from jose import jwt
from passlib.context import CryptContext
from utils.config import get_settings
from api.dependencies.auth import get_current_user_id

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


def create_token(user_id: str, expire_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = expire_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.utcnow() + timedelta(minutes=minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


MOCK_USERS: dict[str, dict] = {}


@router.post("/login")
async def login(body: LoginRequest):
    user = MOCK_USERS.get(body.email)
    if not user or not pwd_ctx.verify(body.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_token(user["id"])
    refresh = create_token(user["id"], expire_minutes=60 * 24 * 30)

    return {
        "data": {
            "user": {k: v for k, v in user.items() if k != "hashed_password"},
            "tokens": {"token": token, "refreshToken": refresh},
        },
        "success": True,
        "message": "Login successful",
    }


@router.post("/register")
async def register(body: RegisterRequest):
    if body.email in MOCK_USERS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user_id = f"user_{len(MOCK_USERS) + 1}"
    MOCK_USERS[body.email] = {
        "id": user_id,
        "name": body.name,
        "email": body.email,
        "hashed_password": pwd_ctx.hash(body.password),
        "createdAt": datetime.utcnow().isoformat(),
    }

    user = {k: v for k, v in MOCK_USERS[body.email].items() if k != "hashed_password"}
    token = create_token(user_id)
    refresh = create_token(user_id, expire_minutes=60 * 24 * 30)

    return {
        "data": {"user": user, "tokens": {"token": token, "refreshToken": refresh}},
        "success": True,
        "message": "Registration successful",
    }


@router.get("/me")
async def get_me(user_id: str = Depends(get_current_user_id)):
    user = next((u for u in MOCK_USERS.values() if u["id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"data": {k: v for k, v in user.items() if k != "hashed_password"}, "success": True}


@router.post("/logout")
async def logout(user_id: str = Depends(get_current_user_id)):
    return {"success": True, "message": "Logged out"}


@router.post("/refresh")
async def refresh_token(body: dict):
    settings = get_settings()
    try:
        payload = jwt.decode(body.get("refreshToken", ""), settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        new_token = create_token(payload["sub"])
        return {"data": {"token": new_token}, "success": True}
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
