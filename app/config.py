"""Конфигурация приложения (переменные окружения BALANS_*)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # SQLAlchemy URL. По умолчанию SQLite; для PostgreSQL достаточно задать
    # postgresql+psycopg2://user:pass@host/db (см. раздел 3.1 ТЗ).
    database_url: str = "sqlite:///balans.db"
    secret_key: str = "dev-secret-change-me-please-set-BALANS_SECRET_KEY-32bytes+"
    access_token_ttl_minutes: int = 12 * 60
    cookie_name: str = "access_token"
    cookie_secure: bool = False
    # Ограничение попыток входа/регистрации (см. риски ТЗ: rate limiting).
    auth_rate_limit: int = 10
    auth_rate_window_seconds: int = 60


def load_config() -> Config:
    return Config(
        database_url=os.getenv("BALANS_DATABASE_URL", "sqlite:///balans.db"),
        secret_key=os.getenv("BALANS_SECRET_KEY", "dev-secret-change-me-please-set-BALANS_SECRET_KEY-32bytes+"),
        access_token_ttl_minutes=int(os.getenv("BALANS_TOKEN_TTL_MINUTES", str(12 * 60))),
        cookie_secure=os.getenv("BALANS_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
    )
