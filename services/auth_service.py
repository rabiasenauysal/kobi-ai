"""
KOBİ AI Platform — JWT Auth Servisi
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

from config.settings import get_settings
from services.db import query, execute_lastrowid


def _hash(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def _settings():
    return get_settings()


# ── Token ─────────────────────────────────────────────────────────────────────

def create_token(user_id: int, email: str, rol: str) -> str:
    if not JWT_AVAILABLE:
        return f"simple:{user_id}:{rol}"
    s = _settings()
    payload = {
        "sub": str(user_id),
        "email": email,
        "rol": rol,
        "exp": datetime.utcnow() + timedelta(hours=s.jwt_expire_h),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    if not JWT_AVAILABLE:
        if token.startswith("simple:"):
            parts = token.split(":")
            return {"sub": parts[1], "rol": parts[2]} if len(parts) == 3 else None
        return None
    try:
        s = _settings()
        payload = jwt.decode(token, s.jwt_secret, algorithms=["HS256"])
        return payload
    except Exception:
        return None


# ── Kullanıcı İşlemleri ───────────────────────────────────────────────────────

def login(email: str, password: str) -> Optional[Dict[str, Any]]:
    rows = query(
        "SELECT id, email, ad, rol, aktif FROM KULLANICILAR WHERE email=? AND sifre_hash=? AND aktif=1",
        (email.strip().lower(), _hash(password)),
    )
    if not rows:
        return None
    user = rows[0]
    token = create_token(user["id"], user["email"], user["rol"])
    return {"token": token, "user": dict(user)}


def register(email: str, password: str, ad: str, rol: str = "yonetici") -> Optional[int]:
    try:
        uid = execute_lastrowid(
            "INSERT INTO KULLANICILAR (email, sifre_hash, ad, rol) VALUES (?,?,?,?)",
            (email.strip().lower(), _hash(password), ad, rol),
        )
        return uid
    except Exception as e:
        print(f"[Auth] Kayıt hatası: {e}")
        return None


def get_user_by_token(token: str) -> Optional[Dict[str, Any]]:
    payload = verify_token(token)
    if not payload:
        return None
    rows = query(
        "SELECT id, email, ad, rol, aktif FROM KULLANICILAR WHERE id=? AND aktif=1",
        (int(payload["sub"]),),
    )
    return rows[0] if rows else None


# ── FastAPI Dependency ────────────────────────────────────────────────────────

from fastapi import Header, HTTPException, status


async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token gerekli")
    token = authorization[7:]
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz token")
    return user


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Giriş yapmamış kullanıcılar için (guest mode)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return get_user_by_token(token)
