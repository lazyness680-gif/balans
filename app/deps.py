"""Зависимости: текущий пользователь, изоляция данных (FR-3), rate limiting."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import Config, load_config
from .database import get_session
from .models import User
from .security import decode_access_token


def get_config() -> Config:
    return load_config()


def _token_from_request(request: Request, config: Config) -> str | None:
    token = request.cookies.get(config.cookie_name)
    if token:
        return token
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def current_user_optional(
    request: Request,
    session: Session = Depends(get_session),
    config: Config = Depends(get_config),
) -> User | None:
    """Пользователь из JWT-cookie/заголовка или None (гость — см. раздел 4 ТЗ)."""
    token = _token_from_request(request, config)
    if not token:
        return None
    user_id = decode_access_token(token, config)
    if user_id is None:
        return None
    return session.get(User, user_id)


def require_user(user: User | None = Depends(current_user_optional)) -> User:
    """Для API: 401, если не авторизован."""
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user


# ---- Ограничение числа попыток (rate limiting, см. раздел 11 ТЗ) ----

_attempts: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(key: str, config: Config) -> None:
    now = time.monotonic()
    window = config.auth_rate_window_seconds
    bucket = _attempts[key]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= config.auth_rate_limit:
        raise HTTPException(
            status_code=429,
            detail="Слишком много попыток. Попробуйте чуть позже.",
        )
    bucket.append(now)


def reset_rate_limits() -> None:
    """Для тестов."""
    _attempts.clear()
