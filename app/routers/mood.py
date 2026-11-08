"""API записей настроения/стресса (FR-5…FR-12).

Правила дат проверяются на бэкенде (п.3.2 ТЗ):
- создание: не будущее и не старше 7 дней (FR-7, FR-9);
- редактирование: запись не старше 3 дней (FR-8);
- одна запись на дату: upsert по (user_id, date) (FR-6).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dates import can_create_on, can_edit_on, today_in
from ..database import get_session
from ..deps import require_user
from ..models import MoodEntry, User
from ..schemas import MoodEntryIn, MoodEntryOut, MoodEntryPatch

router = APIRouter(prefix="/api/mood-entries", tags=["mood"])


def _get_owned(entry_id: int, user: User, session: Session) -> MoodEntry:
    """Изоляция данных: чужие ID недоступны (FR-3, AC-2) — отвечаем 404."""
    entry = session.get(MoodEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return entry


@router.get("", response_model=list[MoodEntryOut])
def list_entries(
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
):
    today = today_in(user.timezone)
    start = from_ if from_ is not None else today - timedelta(days=7)
    end = to if to is not None else today
    if start > end:
        start, end = end, start
    rows = session.scalars(
        select(MoodEntry)
        .where(MoodEntry.user_id == user.id, MoodEntry.date >= start, MoodEntry.date <= end)
        .order_by(MoodEntry.date.desc())
    ).all()
    return rows


@router.post("", response_model=MoodEntryOut, status_code=201)
def create_entry(
    payload: MoodEntryIn,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    today = today_in(user.timezone)
    if payload.date > today:
        raise HTTPException(status_code=422, detail="Нельзя создать запись на будущую дату")
    if not can_create_on(payload.date, today):
        raise HTTPException(
            status_code=422, detail="Можно заполнить задним числом не более 7 дней"
        )

    # FR-6: повторное сохранение на ту же дату обновляет существующую запись
    existing = session.scalar(
        select(MoodEntry).where(MoodEntry.user_id == user.id, MoodEntry.date == payload.date)
    )
    if existing is not None:
        existing.mood = payload.mood
        existing.stress = payload.stress
        existing.note = payload.note
        existing.tags = payload.tags
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    entry = MoodEntry(
        user_id=user.id,
        date=payload.date,
        mood=payload.mood,
        stress=payload.stress,
        note=payload.note,
        tags=payload.tags,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=MoodEntryOut)
def update_entry(
    entry_id: int,
    payload: MoodEntryPatch,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    entry = _get_owned(entry_id, user, session)
    today = today_in(user.timezone)

    # FR-8: редактирование — не более 3 дней назад
    if not can_edit_on(entry.date, today):
        raise HTTPException(
            status_code=422,
            detail="Редактировать запись можно в течение 3 дней после её даты",
        )

    data = payload.model_dump(exclude_unset=True)
    new_date = data.get("date")
    if new_date is not None and new_date != entry.date:
        if new_date > today:
            raise HTTPException(status_code=422, detail="Нельзя перенести запись на будущую дату")
        if not can_edit_on(new_date, today):
            raise HTTPException(status_code=422, detail="Перенос возможен не более чем на 3 дня назад")
        conflict = session.scalar(
            select(MoodEntry).where(
                MoodEntry.user_id == user.id, MoodEntry.date == new_date, MoodEntry.id != entry.id
            )
        )
        if conflict is not None:
            raise HTTPException(status_code=409, detail="На эту дату запись уже есть")
        entry.date = new_date

    for field in ("mood", "stress", "note", "tags"):
        if field in data and data[field] is not None:
            setattr(entry, field, data[field])

    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    entry = _get_owned(entry_id, user, session)
    session.delete(entry)
    session.commit()
