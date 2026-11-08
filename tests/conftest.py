"""Общие фикстуры: приложение на временном SQLite, клиенты, помощники."""
from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.deps import reset_rate_limits
from app.main import create_app

TZ = ZoneInfo("Europe/Moscow")


def today() -> date:
    return date.today()  # в тестах сверяемся с локальной датой; «сегодня» пользователя — Europe/Moscow


def moscow_today() -> date:
    import datetime as _dt

    return _dt.datetime.now(TZ).date()


@pytest.fixture()
def app(tmp_path):
    reset_rate_limits()
    config = Config(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    application = create_app(config)
    yield application
    reset_rate_limits()


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def make_client(app):
    """Фабрика клиентов — каждый со своими cookie (изоляция сессий)."""
    clients: list[TestClient] = []

    def factory() -> TestClient:
        test_client = TestClient(app)
        clients.append(test_client)
        return test_client

    yield factory
    for test_client in clients:
        test_client.close()


def register(client: TestClient, email: str = "user@example.com", password: str = "secret12") -> dict:
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def add_entry(client: TestClient, entry_date: date, mood: int = 4, stress: int = 3, **extra) -> dict:
    payload = {"date": entry_date.isoformat(), "mood": mood, "stress": stress, **extra}
    response = client.post("/api/mood-entries", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def add_task_raw(app, user_id: int, title: str, planned_date: date, status: str = "planned") -> None:
    """Вставка задачи напрямую в БД — для истории старше 7 дней (лимиты API)."""
    from app.models import Task

    with app.state.db.session() as session:
        session.add(
            Task(
                user_id=user_id,
                title=title,
                planned_date=planned_date,
                status=status,
                priority="средний",
                category="работа",
            )
        )
        session.commit()


def add_entry_raw(app, user_id: int, entry_date: date, mood: int, stress: int, tags: list | None = None) -> None:
    """Вставка записи напрямую в БД (для истории старше 7 дней)."""
    from app.models import MoodEntry

    with app.state.db.session() as session:
        session.add(
            MoodEntry(
                user_id=user_id,
                date=entry_date,
                mood=mood,
                stress=stress,
                tags=tags or [],
            )
        )
        session.commit()


def days_ago(n: int) -> date:
    return moscow_today() - timedelta(days=n)
