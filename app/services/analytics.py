"""Аналитика: два графика, периоды 7/30/90, фильтр по тегам, дайджест (раздел 5.6, 6.3)."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dates import STATS_WINDOW, today_in
from ..models import MoodEntry, Task, User

VALID_PERIODS = (7, 30, 90)


def _entry_by_date(session: Session, user: User, start: date, end: date) -> dict[date, MoodEntry]:
    rows = session.scalars(
        select(MoodEntry).where(
            MoodEntry.user_id == user.id,
            MoodEntry.date >= start,
            MoodEntry.date <= end,
        )
    ).all()
    return {row.date: row for row in rows}


def _tasks_by_date(session: Session, user: User, start: date, end: date) -> dict[date, dict]:
    rows = session.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.planned_date >= start,
            Task.planned_date <= end,
        )
    ).all()
    result: dict[date, dict] = {}
    for row in rows:
        bucket = result.setdefault(
            row.planned_date, {"completed": 0, "planned": 0, "cancelled": 0}
        )
        if row.status == "done":
            bucket["completed"] += 1
        elif row.status == "cancelled":
            bucket["cancelled"] += 1
        else:
            bucket["planned"] += 1
    return result


def build_analytics(
    session: Session,
    user: User,
    period: int,
    tags: list[str] | None = None,
    today: date | None = None,
) -> dict:
    """Данные для двух графиков (FR-30…FR-35, AC-16…AC-20)."""
    if period not in VALID_PERIODS:
        period = 7
    if today is None:
        today = today_in(user.timezone)
    start = today - timedelta(days=period - 1)
    tags = tags or []

    entries = _entry_by_date(session, user, start, today)
    tasks = _tasks_by_date(session, user, start, today)

    days = []
    days_with_data = 0
    cursor = start
    while cursor <= today:
        entry = entries.get(cursor)
        # фильтр по тегам: остаются только записи с выбранными тегами (AC-19)
        if tags and (entry is None or not (set(entry.tags) & set(tags))):
            entry = None
        counts = tasks.get(cursor, {"completed": 0, "planned": 0, "cancelled": 0})
        if entry is not None:
            days_with_data += 1
        days.append(
            {
                "date": cursor.isoformat(),
                "mood": entry.mood if entry else None,
                "stress": entry.stress if entry else None,
                "tags": entry.tags if entry else [],
                "completed": counts["completed"],
                "planned": counts["planned"],
            }
        )
        cursor += timedelta(days=1)

    return {
        "period": period,
        "tags": tags,
        "days": days,
        "days_with_data": days_with_data,
        # пустое состояние при менее чем 3 днях данных (FR-35, AC-20)
        "empty": days_with_data < 3,
    }


def _completion_rate(session: Session, user: User, start: date, end: date) -> float | None:
    rows = _tasks_by_date(session, user, start, end)
    done = sum(v["completed"] for v in rows.values())
    counted = done + sum(v["planned"] for v in rows.values())
    return (done / counted) if counted else None


def build_digest(
    session: Session,
    user: User,
    period: str = "week",
    today: date | None = None,
) -> dict:
    """Дайджест и тренд (FR-36, п.6.3, AC-21)."""
    length = STATS_WINDOW if period == "week" else 30
    if today is None:
        today = today_in(user.timezone)

    cur_start = today - timedelta(days=length - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)

    def metrics(start: date, end: date) -> dict:
        entries = _entry_by_date(session, user, start, end)
        moods = [e.mood for e in entries.values()]
        stresses = [e.stress for e in entries.values()]
        return {
            "avg_mood": round(sum(moods) / len(moods), 2) if moods else None,
            "avg_stress": round(sum(stresses) / len(stresses), 2) if stresses else None,
            "completion_rate": _completion_rate(session, user, start, end),
            "days_with_entries": len(entries),
        }

    current = metrics(cur_start, today)
    previous = metrics(prev_start, prev_end)

    def fmt_pct(value: float | None) -> str | None:
        return None if value is None else f"{round(value * 100)}%"

    # тренд: сравнение с предыдущим периодом той же длины (п.6.3)
    if current["days_with_entries"] < 2 or previous["days_with_entries"] < 2:
        trend_text = "пока мало данных для сравнения"
        trend_direction = "unknown"
    else:
        parts = []
        direction = "flat"

        ds = (current["avg_stress"] or 0) - (previous["avg_stress"] or 0)
        if abs(ds) >= 0.3:
            parts.append(
                f"средний стресс {'вырос' if ds > 0 else 'снизился'} на {abs(round(ds, 1))}"
            )
            direction = "worse" if ds > 0 else "better"
        dm = (current["avg_mood"] or 0) - (previous["avg_mood"] or 0)
        if abs(dm) >= 0.3:
            parts.append(
                f"среднее настроение {'выросло' if dm > 0 else 'снизилось'} на {abs(round(dm, 1))}"
            )
            if (dm > 0 and direction != "worse") or direction == "flat":
                direction = "better" if dm > 0 else ("worse" if dm < 0 else direction)
        dc = current["completion_rate"]
        pc = previous["completion_rate"]
        if dc is not None and pc is not None:
            pp = round((dc - pc) * 100)
            if abs(pp) >= 10:
                parts.append(f"% выполнения {'вырос' if pp > 0 else 'снизился'} на {abs(pp)} п.п.")
                if pp > 0 and direction == "flat":
                    direction = "better"
                elif pp < 0 and direction == "flat":
                    direction = "worse"

        if parts:
            trend_text = "По сравнению с прошлым периодом: " + ", ".join(parts) + "."
        else:
            trend_text = "Без заметных изменений по сравнению с прошлым периодом."
        trend_direction = direction

    return {
        "period": period,
        "length_days": length,
        "current": {
            **current,
            "completion_rate_text": fmt_pct(current["completion_rate"]),
            "range": [cur_start.isoformat(), today.isoformat()],
        },
        "previous": {
            **previous,
            "completion_rate_text": fmt_pct(previous["completion_rate"]),
            "range": [prev_start.isoformat(), prev_end.isoformat()],
        },
        "trend": {"text": trend_text, "direction": trend_direction},
    }
