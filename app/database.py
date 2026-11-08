"""Подключение к БД и базовый класс моделей.

Поддерживается SQLite (по умолчанию, для разработки и демо) и PostgreSQL —
достаточно задать BALANS_DATABASE_URL (см. app/config.py). Код не зависит
от конкретного диалекта.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    """Обёртка над engine + sessionmaker (одна на приложение/тест)."""

    def __init__(self, url: str) -> None:
        connect_args = {}
        if url.startswith("sqlite"):
            # SQLite по умолчанию запрещает доступ из других потоков.
            connect_args = {"check_same_thread": False}
        self.engine = create_engine(url, connect_args=connect_args, future=True)
        self.session_factory = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False, future=True
        )

    def session(self):
        return self.session_factory()

    def create_all(self) -> None:
        from . import models  # noqa: F401  (регистрация моделей в metadata)

        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)


_db: Database | None = None


def configure(url: str) -> Database:
    """Создать/пересоздать глобальное подключение (вызывается в create_app)."""
    global _db
    _db = Database(url)
    return _db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("БД не настроена: вызовите configure() в create_app()")
    return _db


def get_session():
    """Dependency: сессия SQLAlchemy с гарантированным закрытием."""
    session = get_db().session()
    try:
        yield session
    finally:
        session.close()
