"""Безопасность: хеши паролей, JWT в httpOnly-cookie (см. п.12.2 ТЗ)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import Config

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, config: Config) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=config.access_token_ttl_minutes),
        "typ": "access",
    }
    return jwt.encode(payload, config.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, config: Config) -> int | None:
    """Вернуть user_id или None, если токен невалиден/просрочен."""
    try:
        payload = jwt.decode(token, config.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "access":
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
