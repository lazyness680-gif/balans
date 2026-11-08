"""Сервис рекомендации по нагрузке (раздел 6.1–6.2 ТЗ).

Рекомендация НЕ хранится, вычисляется на лету (раздел 7 ТЗ).
Вся арифметика вынесена в чистые функции — покрыта юнит-тестами (AC-9…AC-14).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dates import STATS_WINDOW, today_in, utcnow
from ..models import MoodEntry, Task, User

DISCLAIMER = "Это ориентир по нагрузке, а не медицинская рекомендация"

# ---- Чистые функции расчёта (по псевдокоду п.6.1) ----


def base_limit(mood_today: int, stress_today: int) -> int:
    """Базовое число задач по сегодняшнему состоянию."""
    if mood_today <= 2 or stress_today >= 7:
        return 3
    if mood_today == 3 or stress_today in (5, 6):
        return 5
    return 7


def apply_completion(base: int, completion_rate_7: float | None) -> int:
    """Штраф за низкий процент выполнения за 7 дней (< 50% → −2, минимум 1)."""
    if completion_rate_7 is not None and completion_rate_7 < 0.5:
        return max(1, base - 2)
    return max(1, base)


def apply_comfort_limit(base: int, comfort_limit: int | None) -> int:
    if comfort_limit is not None:
        return min(base, comfort_limit)
    return base


def compute_max_tasks(
    mood_today: int,
    stress_today: int,
    completion_rate_7: float | None,
    comfort_limit: int | None,
) -> int:
    base = base_limit(mood_today, stress_today)
    base = apply_completion(base, completion_rate_7)
    return apply_comfort_limit(base, comfort_limit)


def plural_tasks(n: int) -> str:
    """Склонение: 1 задачи, 2 задачи, 5 задач, 11 задач."""
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return "задач"
    if n % 10 == 1:
        return "задачи"
    if 2 <= n % 10 <= 4:
        return "задачи"
    return "задач"


def build_factors(
    mood_today: int,
    stress_today: int,
    completion_rate_7: float | None,
    comfort_limit: int | None,
) -> list[str]:
    """Приоритет факторов: сегодня → история 7 дней → личный лимит (п.6.1)."""
    factors: list[str] = []

    if stress_today >= 7:
        factors.append(f"высокий стресс ({stress_today}/10)")
    elif stress_today in (5, 6):
        factors.append(f"умеренный стресс ({stress_today}/10)")
    else:
        factors.append(f"низкий стресс ({stress_today}/10)")

    if mood_today <= 2:
        factors.append(f"низкое настроение ({mood_today}/5)")
    elif mood_today == 3:
        factors.append(f"среднее настроение ({mood_today}/5)")
    else:
        factors.append(f"хорошее настроение ({mood_today}/5)")

    if completion_rate_7 is not None and completion_rate_7 < 0.5:
        pct = round(completion_rate_7 * 100)
        factors.append(f"низкий процент выполнения за 7 дней ({pct}%)")

    if comfort_limit is not None:
        before_limit = apply_completion(
            base_limit(mood_today, stress_today), completion_rate_7
        )
        if comfort_limit < before_limit:
            factors.append(f"личный лимит ({comfort_limit} {plural_tasks(comfort_limit)})")

    return factors


# ---- Сбор данных из БД ----


def fetch_context(session: Session, user: User, today: date) -> dict:
    """Считает все входные данные рекомендации за 7 дней."""
    window_start = today - timedelta(days=STATS_WINDOW - 1)

    entry = session.scalar(
        select(MoodEntry).where(MoodEntry.user_id == user.id, MoodEntry.date == today)
    )

    tasks_7 = session.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.planned_date >= window_start,
            Task.planned_date <= today,
        )
    ).all()

    counted = [t for t in tasks_7 if t.status != "cancelled"]
    done = [t for t in counted if t.status == "done"]
    completion_rate = (len(done) / len(counted)) if counted else None

    planned_today = len(
        session.scalars(
            select(Task).where(
                Task.user_id == user.id,
                Task.planned_date == today,
                Task.status == "planned",
            )
        ).all()
    )

    # «обычно вы планируете ~K задач» — среднее число задач в день за 7 дней
    avg_planned = round(len(counted) / STATS_WINDOW) if counted else None

    # средние настроение/стресс за 7 дней (окно включает сегодняшнюю запись)
    mood_values = [
        e.mood
        for e in session.scalars(
            select(MoodEntry).where(
                MoodEntry.user_id == user.id,
                MoodEntry.date >= window_start,
                MoodEntry.date <= today,
            )
        ).all()
    ]

    return {
        "entry": entry,
        "mood_avg_7": (sum(mood_values) / len(mood_values)) if mood_values else None,
        "completion_rate_7": completion_rate,
        "planned_today": planned_today or 0,
        "avg_planned_7": avg_planned,
        "tasks_done_7": len(done),
        "tasks_total_7": len(counted),
    }


# ---- Итоговый ответ ----


def build_recommendation(session: Session, user: User, today: date | None = None) -> dict:
    """GET /api/recommendations/today (FR-20…FR-26)."""
    if today is None:
        today = today_in(user.timezone)

    ctx = fetch_context(session, user, today)
    entry: MoodEntry | None = ctx["entry"]
    planned_today: int = ctx["planned_today"]

    # п.6.2 ТЗ: нет отметки за сегодня → рекомендации нет, только факт планов
    if entry is None:
        hint = None
        avg = ctx["avg_planned_7"]
        if planned_today and avg is not None and planned_today > avg:
            hint = f"Обычно вы планируете ~{avg} {plural_tasks(avg)} в день"
        return {
            "date": today.isoformat(),
            "state_missing": True,
            "max_tasks": None,
            "planned_today": planned_today,
            "text": "Состояние не отмечено",
            "explanation": (
                "Отметьте настроение и стресс — тогда покажу рекомендацию по нагрузке."
            ),
            "hint": hint,
            "basis": {
                "planned_today": planned_today,
                "completion_rate_7": ctx["completion_rate_7"],
                "mood_avg_7": ctx["mood_avg_7"],
                "factors": [],
            },
            "disclaimer": DISCLAIMER,
        }

    completion = ctx["completion_rate_7"]
    comfort = user.comfort_limit
    max_tasks = compute_max_tasks(entry.mood, entry.stress, completion, comfort)
    factors = build_factors(entry.mood, entry.stress, completion, comfort)

    text = f"Сегодня стоит запланировать не больше {max_tasks} {plural_tasks(max_tasks)}"
    explanation_parts = [f"Почему столько: {', '.join(factors)}."]

    if planned_today > max_tasks:
        explanation_parts.append(
            f"У вас уже запланировано {planned_today} {plural_tasks(planned_today)} — это больше "
            "ориентира. Ничего менять не нужно, просто учитывайте нагрузку."
        )

    return {
        "date": today.isoformat(),
        "state_missing": False,
        "max_tasks": max_tasks,
        "planned_today": planned_today,
        "text": text,
        "explanation": " ".join(explanation_parts),
        "basis": {
            "mood_today": entry.mood,
            "stress_today": entry.stress,
            "mood_avg_7": round(ctx["mood_avg_7"], 2) if ctx["mood_avg_7"] is not None else None,
            "completion_rate_7": round(completion, 3) if completion is not None else None,
            "comfort_limit": comfort,
            "planned_today": planned_today,
            "factors": factors,
        },
        "disclaimer": DISCLAIMER,
    }
