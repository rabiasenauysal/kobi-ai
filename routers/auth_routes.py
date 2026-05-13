"""
KOBİ AI Platform — Auth Route'ları
POST /api/auth/login, /api/auth/register, /api/auth/me
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from services.auth_service import login, register, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    ad: str
    rol: str = "yonetici"


@router.post("/login")
async def auth_login(body: LoginRequest):
    result = login(body.email, body.password)
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz e-posta veya şifre")
    return result


@router.post("/register")
async def auth_register(body: RegisterRequest):
    uid = register(body.email, body.password, body.ad, body.rol)
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kayıt başarısız (e-posta kullanılıyor olabilir)")
    return {"id": uid, "message": "Kayıt başarılı"}


@router.get("/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return user
