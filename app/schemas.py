"""Pydantic-схемы API (раздел 3.3 ТЗ, валидация шкал и дат)."""
from __future__ import annotations

import re
from datetime import date as Date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import MOOD_TAGS, TASK_CATEGORIES, TASK_PRIORITIES

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------

class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Некорректный email")
        return v


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class ProfileOut(OrmModel):
    id: int
    email: str
    timezone: str
    comfort_limit: int | None
    theme: str


class ProfilePatch(BaseModel):
    comfort_limit: int | None = Field(default=None, ge=1, le=30)
    theme: Literal["light", "dark"] | None = None
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Неизвестный часовой пояс") from exc
        return v


# ---------- Mood entries ----------

class MoodEntryIn(BaseModel):
    date: Date
    mood: int = Field(ge=1, le=5)
    stress: int = Field(ge=1, le=10)
    note: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, v: list[str]) -> list[str]:
        unknown = [t for t in v if t not in MOOD_TAGS]
        if unknown:
            raise ValueError(f"Неизвестные теги: {', '.join(unknown)}")
        # порядок и уникальность по фиксированному набору
        return [t for t in MOOD_TAGS if t in set(v)]


class MoodEntryPatch(BaseModel):
    date: Date | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    stress: int | None = Field(default=None, ge=1, le=10)
    note: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        unknown = [t for t in v if t not in MOOD_TAGS]
        if unknown:
            raise ValueError(f"Неизвестные теги: {', '.join(unknown)}")
        return [t for t in MOOD_TAGS if t in set(v)]


class MoodEntryOut(OrmModel):
    id: int
    date: Date
    mood: int
    stress: int
    note: str | None
    tags: list[str]


# ---------- Tasks ----------

class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    planned_date: Date
    deadline: Date | None = None
    priority: Literal["низкий", "средний", "высокий"] = "средний"
    category: str = "другое"
    status: Literal["planned", "done", "cancelled"] = "planned"

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        if v not in TASK_CATEGORIES:
            raise ValueError(f"Категория должна быть из набора: {', '.join(TASK_CATEGORIES)}")
        return v

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Название задачи не может быть пустым")
        return v


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    planned_date: Date | None = None
    deadline: Date | None = None
    priority: Literal["низкий", "средний", "высокий"] | None = None
    category: str | None = None
    status: Literal["planned", "done", "cancelled"] | None = None

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str | None) -> str | None:
        if v is not None and v not in TASK_CATEGORIES:
            raise ValueError(f"Категория должна быть из набора: {', '.join(TASK_CATEGORIES)}")
        return v

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Название задачи не может быть пустым")
        return v


class TaskOut(OrmModel):
    id: int
    title: str
    planned_date: Date
    deadline: Date | None
    priority: str
    category: str
    status: str
    completed_at: datetime | None = None


class ApiError(BaseModel):
    detail: str
