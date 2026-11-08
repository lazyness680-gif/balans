"""Фабрика приложения FastAPI («Баланс», ТЗ раздел 3).

Запуск:  python -m uvicorn app.main:app --reload  (см. README.md)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Config, load_config
from .database import configure
from .errors import register_error_handlers
from .routers import auth_api, insights, me, mood, pages, tasks

BASE_DIR = Path(__file__).resolve().parent

MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def ru_date(value) -> str:
    """«6 ноября 2026, четверг» для заголовков (UI на русском)."""
    if value is None:
        return ""
    parts = [str(value.day), MONTHS_GEN[value.month - 1], str(value.year)]
    result = " ".join(parts)
    weekday = getattr(value, "weekday", None)
    if callable(weekday):
        result += f", {WEEKDAYS[weekday()]}"
    return result


def build_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    templates.env.filters["ru_date"] = ru_date
    templates.env.globals["STATUS_LABELS"] = {"planned": "запланирована",
                                              "done": "выполнена",
                                              "cancelled": "отменена"}
    return templates


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    database = configure(config.database_url)
    database.create_all()

    app = FastAPI(title="Баланс — трекер состояния и нагрузки", version="1.0.0")
    app.state.config = config
    app.state.db = database
    app.state.templates = build_templates()

    app.include_router(auth_api.router)
    app.include_router(me.router)
    app.include_router(mood.router)
    app.include_router(tasks.router)
    app.include_router(insights.router)
    app.include_router(pages.pages)

    # Ошибки валидации/rate limit: API — JSON, страницы — редирект с сообщением
    register_error_handlers(app)

    @app.get("/health", include_in_schema=False)
    def health() -> dict:
        """Healthcheck для деплоя/reverse-proxy (раздел 12 ТЗ)."""
        return {"status": "ok"}

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    return app


def __getattr__(name: str):
    # Ленивый глобальный app: при импорте из тестов файл БД не создаётся,
    # uvicorn app.main:app получает приложение через getattr.
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
