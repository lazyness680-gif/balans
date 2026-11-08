"""Модели данных (раздел 7 ТЗ)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# Предустановленные теги состояния (FR-11): фиксированный набор, кастомные — пост-MVP.
MOOD_TAGS = ["сон", "работа", "здоровье", "спорт"]

# Предустановленные категории задач (решение по п.12.5 ТЗ): плоский список.
TASK_CATEGORIES = ["работа", "учёба", "дом", "здоровье", "другое"]

TASK_PRIORITIES = ["низкий", "средний", "высокий"]
TASK_STATUSES = ["planned", "done", "cancelled"]

THEMES = ["light", "dark"]

DEFAULT_TIMEZONE = "Europe/Moscow"

# Часовые пояса для выпадающего списка в настройках (FR-40).
TIMEZONES = [
    "Europe/Kaliningrad",
    "Europe/Moscow",
    "Europe/Samara",
    "Europe/Yekaterinburg",
    "Asia/Omsk",
    "Asia/Novosibirsk",
    "Asia/Krasnoyarsk",
    "Asia/Irkutsk",
    "Asia/Yakutsk",
    "Asia/Vladivostok",
    "Asia/Sakhalin",
    "Europe/Minsk",
    "Europe/Kyiv",
    "Europe/Belgrade",
    "Europe/Istanbul",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Paris",
    "Europe/Madrid",
    "Europe/Rome",
    "Europe/Helsinki",
    "Europe/Riga",
    "Europe/Tallinn",
    "Europe/Vilnius",
    "Asia/Tbilisi",
    "Asia/Yerevan",
    "Asia/Baku",
    "Asia/Almaty",
    "Asia/Tashkent",
    "Asia/Bishkek",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Australia/Sydney",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Sao_Paulo",
    "UTC",
]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default=DEFAULT_TIMEZONE)
    comfort_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    theme: Mapped[str] = mapped_column(String(16), nullable=False, default="light")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MoodEntry(Base):
    """Одна запись настроения/стресса на дату (уникальна в паре с user_id)."""

    __tablename__ = "mood_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_mood_entries_user_date"),
        Index("ix_mood_entries_user_date", "user_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    mood: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–5
    stress: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–10
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # ≤ 500 символов
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_user_planned_date", "user_id", "planned_date"),
        Index("ix_tasks_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="средний")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="другое")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
