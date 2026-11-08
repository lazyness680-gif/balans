"""Работа с датами: «сегодня» по часовому поясу пользователя (п.3.2 ТЗ).

- даты хранятся как DATE, метки времени — в UTC;
- границы правил: создание задним числом ≤ 7 дней, редактирование ≤ 3 дней,
  запись на будущее невозможна (FR-7…FR-9).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BACKFILL_DAYS = 7   # глубина создания записи задним числом
EDIT_DAYS = 3       # окно редактирования существующей записи
STATS_WINDOW = 7    # окно «средних за 7 дней»


def get_zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo("UTC")


def today_in(tz_name: str) -> date:
    """«Сегодня» в часовом поясе пользователя (FR-4)."""
    return datetime.now(get_zone(tz_name)).date()


def utcnow() -> datetime:
    """Метки времени — всегда UTC (п.3.2 ТЗ)."""
    return datetime.now(timezone.utc)


def window_last_n(today: date, n: int) -> tuple[date, date]:
    """Период из n дней, заканчивающийся сегодня (включительно)."""
    return today - timedelta(days=n - 1), today


def can_create_on(record_date: date, today: date) -> bool:
    """Не будущая и не старше 7 дней (FR-7, FR-9)."""
    return today - timedelta(days=BACKFILL_DAYS) <= record_date <= today


def can_edit_on(record_date: date, today: date) -> bool:
    """Существующая запись редактируется, если ей не более 3 дней (FR-8)."""
    return today - timedelta(days=EDIT_DAYS) <= record_date <= today
