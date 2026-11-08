"""API задач (FR-13…FR-19): CRUD, статусы, фильтры, учёт по planned_date."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dates import today_in, utcnow
from ..database import get_session
from ..deps import require_user
from ..models import Task, User
from ..schemas import TaskIn, TaskOut, TaskPatch

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_PRIORITY_ORDER = {p: i for i, p in enumerate(["высокий", "средний", "низкий"])}


def _get_owned(task_id: int, user: User, session: Session) -> Task:
    task = session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


def _apply_status(task: Task, status: str) -> None:
    task.status = status
    if status == "done":
        if task.completed_at is None:
            task.completed_at = utcnow()
    else:
        task.completed_at = None


@router.get("", response_model=list[TaskOut])
def list_tasks(
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
    date_: date | None = Query(default=None, alias="date"),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
):
    stmt = select(Task).where(Task.user_id == user.id)
    if date_ is not None:
        stmt = stmt.where(Task.planned_date == date_)
    if status:
        stmt = stmt.where(Task.status == status)
    if category:
        stmt = stmt.where(Task.category == category)
    rows = session.scalars(stmt).all()
    rows.sort(
        key=lambda t: (
            t.planned_date,
            _PRIORITY_ORDER.get(t.priority, 9),
            t.created_at or datetime.min,
        )
    )
    return rows


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    payload: TaskIn,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    task = Task(user_id=user.id, **payload.model_dump())
    if task.status == "done":
        task.completed_at = utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskPatch,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    task = _get_owned(task_id, user, session)
    data = payload.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)
    for field, value in data.items():
        if value is not None or field == "deadline":
            setattr(task, field, value)
    if new_status is not None:
        _apply_status(task, new_status)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    task = _get_owned(task_id, user, session)
    session.delete(task)
    session.commit()
