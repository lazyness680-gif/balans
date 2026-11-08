"""Серверные страницы (Jinja2): Сегодня, История, Задачи, Аналитика, Настройки.

Прогрессивное улучшение: формы работают и без JavaScript (POST → redirect),
графики и подтверждения подключаются JS (см. static/js).
"""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dates import BACKFILL_DAYS, can_edit_on, today_in
from ..database import get_session
from ..deps import get_config, rate_limit
from ..models import MOOD_TAGS, TASK_CATEGORIES, TASK_PRIORITIES, TASK_STATUSES, TIMEZONES, MoodEntry, Task, User
from ..security import hash_password, verify_password
from ..services.recommendation import build_recommendation
from ..schemas import ProfilePatch

pages = APIRouter()

STATUS_LABELS = {"planned": "запланирована", "done": "выполнена", "cancelled": "отменена"}


def _templates(request: Request):
    return request.app.state.templates


def _redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url, status_code=status_code)


def _with_message(url: str, key: str, message: str) -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    return _redirect(f"{url}{sep}{key}={quote(message)}")


def current_user_optional_impl(request: Request, session: Session):
    from ..config import load_config
    from ..security import decode_access_token

    config = load_config()
    token = request.cookies.get(config.cookie_name)
    if not token:
        return None
    user_id = decode_access_token(token, config)
    if user_id is None:
        return None
    return session.get(User, user_id)


def _page_context(request: Request, session: Session, user: User, **extra) -> dict:
    today = today_in(user.timezone)
    has_entry = (
        session.scalar(
            select(MoodEntry.id).where(MoodEntry.user_id == user.id, MoodEntry.date == today)
        )
        is not None
    )
    ctx = {
        "request": request,
        "user": user,
        "today": today,
        "has_entry_today": has_entry,
        # FR-27: in-app напоминание, если отметки за сегодня нет
        "show_reminder": not has_entry,
        "mood_tags": MOOD_TAGS,
        "task_categories": TASK_CATEGORIES,
        "task_priorities": TASK_PRIORITIES,
        "status_labels": STATUS_LABELS,
        "error": request.query_params.get("error"),
        "ok": request.query_params.get("ok"),
        "path": request.url.path,
    }
    ctx.update(extra)
    return ctx


# ---------------- Аутентификация (страницы) ----------------

@pages.get("/")
def index(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    return _redirect("/today" if user else "/login")


@pages.get("/login")
def login_page(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user:
        return _redirect("/today")
    return _templates(request).TemplateResponse(
        request, "auth.html", {"mode": "login", "request": request,
                               "error": request.query_params.get("error")}
    )


@pages.get("/register")
def register_page(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user:
        return _redirect("/today")
    return _templates(request).TemplateResponse(
        request, "auth.html", {"mode": "register", "request": request,
                               "error": request.query_params.get("error")}
    )


@pages.post("/login")
def login_submit(
    request: Request,
    session: Session = Depends(get_session),
    email: str = Form(...),
    password: str = Form(...),
):
    config = get_config()
    ip = request.client.host if request.client else "unknown"
    rate_limit(f"page-login:{ip}", config)
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        return _with_message("/login", "error", "Неверный email или пароль")
    from ..routers.auth_api import set_auth_cookie

    resp = _redirect("/today")
    set_auth_cookie(resp, user, config)
    return resp


@pages.post("/register")
def register_submit(
    request: Request,
    session: Session = Depends(get_session),
    email: str = Form(...),
    password: str = Form(...),
):
    from ..errors import friendly_validation_message
    from ..schemas import RegisterIn

    config = get_config()
    ip = request.client.host if request.client else "unknown"
    rate_limit(f"page-register:{ip}", config)
    try:
        payload = RegisterIn(email=email, password=password)
    except Exception as exc:  # noqa: BLE001 — сообщение валидации Pydantic
        detail = (
            friendly_validation_message(exc.errors())
            if hasattr(exc, "errors")
            else str(exc)
        )
        return _with_message("/register", "error", detail[:200])

    exists = session.scalar(select(User).where(User.email == payload.email))
    if exists is not None:
        return _with_message("/register", "error", "Пользователь с таким email уже существует")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    from ..routers.auth_api import set_auth_cookie

    resp = _redirect("/today")
    set_auth_cookie(resp, user, config)
    return resp


@pages.post("/logout")
def logout_page():
    from ..routers.auth_api import clear_auth_cookie

    config = get_config()
    resp = _redirect("/login")
    clear_auth_cookie(resp, config)
    return resp


# ---------------- Сегодня ----------------

@pages.get("/today")
def today_page(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    today = today_in(user.timezone)
    recommendation = build_recommendation(session, user, today)
    tasks = session.scalars(
        select(Task)
        .where(Task.user_id == user.id, Task.planned_date == today)
        .order_by(Task.created_at)
    ).all()
    entry = session.scalar(
        select(MoodEntry).where(MoodEntry.user_id == user.id, MoodEntry.date == today)
    )
    return _templates(request).TemplateResponse(
        request,
        "today.html",
        _page_context(
            request,
            session,
            user,
            entry=entry,
            tasks=tasks,
            recommendation=recommendation,
            completed_today=sum(1 for t in tasks if t.status == "done"),
        ),
    )


def _parse_mood_form(form, allow_future_date: bool = False, today: date | None = None):
    """Валидация HTML-формы записи (те же правила, что и в API)."""
    try:
        mood = int(form.get("mood", ""))
        stress = int(form.get("stress", ""))
    except (TypeError, ValueError):
        return None, "Укажите настроение (1–5) и стресс (1–10)"
    if not (1 <= mood <= 5):
        return None, "Настроение — от 1 до 5"
    if not (1 <= stress <= 10):
        return None, "Стресс — от 1 до 10"
    note = (form.get("note") or "").strip() or None
    if note and len(note) > 500:
        return None, "Заметка — не длиннее 500 символов"
    tags = [t for t in form.getlist("tags") if t in MOOD_TAGS]
    return {"mood": mood, "stress": stress, "note": note, "tags": tags}, None


@pages.post("/today/entry")
async def today_entry_submit(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    form = await request.form()
    today = today_in(user.timezone)
    data, error = _parse_mood_form(form)
    if error:
        return _with_message("/today", "error", error)

    # FR-6: одна запись на дату — повторное сохранение обновляет запись
    entry = session.scalar(
        select(MoodEntry).where(MoodEntry.user_id == user.id, MoodEntry.date == today)
    )
    if entry is None:
        entry = MoodEntry(user_id=user.id, date=today, **data)
    else:
        for key, value in data.items():
            setattr(entry, key, value)
    session.add(entry)
    session.commit()
    # FR-29: баннер скрывается — запись есть, баннер не рендерится
    return _redirect("/today?ok=" + quote("Отметка сохранена"))


# ---------------- Быстрое добавление задачи на сегодня ----------------

@pages.post("/today/task")
async def today_task_submit(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    form = await request.form()
    title = (form.get("title") or "").strip()
    if not title:
        return _with_message("/today", "error", "Название задачи не может быть пустым")
    if len(title) > 300:
        return _with_message("/today", "error", "Название — не длиннее 300 символов")
    today = today_in(user.timezone)
    task = Task(
        user_id=user.id,
        title=title,
        planned_date=today,
        priority=form.get("priority") if form.get("priority") in TASK_PRIORITIES else "средний",
        category=form.get("category") if form.get("category") in TASK_CATEGORIES else "другое",
    )
    session.add(task)
    session.commit()
    return _redirect("/today")


@pages.post("/tasks/{task_id}/toggle")
async def task_toggle(task_id: int, request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    task = session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        return _with_message("/tasks", "error", "Задача не найдена")
    from ..routers.tasks import _apply_status

    if task.status == "done":
        _apply_status(task, "planned")   # отмена выполнения (FR-15)
    else:
        _apply_status(task, "done")      # отметка «выполнена» (FR-15)
    session.add(task)
    session.commit()
    form = await request.form()
    next_url = form.get("next") or "/today"
    if not str(next_url).startswith("/"):
        next_url = "/today"
    return _redirect(next_url)


# ---------------- История ----------------

@pages.get("/history")
def history_page(
    request: Request,
    session: Session = Depends(get_session),
    period: int = 7,
    edit: int | None = None,
):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    if period not in (7, 30, 90):
        period = 7
    today = today_in(user.timezone)
    start = today - timedelta(days=period - 1)
    entries = session.scalars(
        select(MoodEntry)
        .where(MoodEntry.user_id == user.id, MoodEntry.date >= start, MoodEntry.date <= today)
        .order_by(MoodEntry.date.desc())
    ).all()

    edit_entry = None
    edit_allowed = False
    if edit is not None:
        candidate = session.get(MoodEntry, edit)
        if candidate is not None and candidate.user_id == user.id:
            edit_entry = candidate
            edit_allowed = can_edit_on(candidate.date, today)  # FR-8: ≤ 3 дней

    return _templates(request).TemplateResponse(
        request,
        "history.html",
        _page_context(
            request,
            session,
            user,
            entries=entries,
            period=period,
            edit_entry=edit_entry,
            edit_allowed=edit_allowed,
        ),
    )


@pages.post("/history/entry")
async def history_entry_submit(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    form = await request.form()
    action = form.get("action")
    entry_id = int(form.get("id") or 0)
    entry = session.get(MoodEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        return _with_message("/history", "error", "Запись не найдена")
    today = today_in(user.timezone)

    if action == "delete":
        # FR-12: удаление с подтверждением (confirm() на стороне UI)
        session.delete(entry)
        session.commit()
        return _redirect("/history?ok=" + quote("Запись удалена"))

    # FR-8: редактирование не более 3 дней назад
    if not can_edit_on(entry.date, today):
        return _with_message("/history", "error", "Редактировать запись можно в течение 3 дней")

    data, error = _parse_mood_form(form)
    if error:
        return _with_message(f"/history?edit={entry.id}", "error", error)
    for key, value in data.items():
        setattr(entry, key, value)
    session.add(entry)
    session.commit()
    return _redirect("/history?ok=" + quote("Изменения сохранены"))


# ---------------- Задачи ----------------

@pages.get("/tasks")
def tasks_page(
    request: Request,
    session: Session = Depends(get_session),
    status: str = "",
    category: str = "",
    edit: int | None = None,
):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    stmt = select(Task).where(Task.user_id == user.id)
    if status in TASK_STATUSES:
        stmt = stmt.where(Task.status == status)
    else:
        status = ""
    if category in TASK_CATEGORIES:
        stmt = stmt.where(Task.category == category)
    else:
        category = ""
    tasks = session.scalars(stmt.order_by(Task.planned_date.desc(), Task.created_at)).all()

    edit_task = None
    if edit is not None:
        candidate = session.get(Task, edit)
        if candidate is not None and candidate.user_id == user.id:
            edit_task = candidate

    return _templates(request).TemplateResponse(
        request,
        "tasks.html",
        _page_context(
            request,
            session,
            user,
            tasks=tasks,
            filter_status=status,
            filter_category=category,
            edit_task=edit_task,
        ),
    )


@pages.post("/tasks")
async def task_create_submit(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    form = await request.form()
    title = (form.get("title") or "").strip()
    if not title:
        return _with_message("/tasks", "error", "Название задачи не может быть пустым")
    try:
        planned = date.fromisoformat(form.get("planned_date") or "")
    except ValueError:
        return _with_message("/tasks", "error", "Укажите дату планирования")
    deadline = None
    raw_deadline = form.get("deadline") or ""
    if raw_deadline:
        try:
            deadline = date.fromisoformat(raw_deadline)
        except ValueError:
            return _with_message("/tasks", "error", "Некорректная дата дедлайна")
    task = Task(
        user_id=user.id,
        title=title[:300],
        planned_date=planned,
        deadline=deadline,
        priority=form.get("priority") if form.get("priority") in TASK_PRIORITIES else "средний",
        category=form.get("category") if form.get("category") in TASK_CATEGORIES else "другое",
    )
    session.add(task)
    session.commit()
    return _redirect("/tasks?ok=" + quote("Задача добавлена"))


@pages.post("/tasks/task")
async def task_edit_submit(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    form = await request.form()
    action = form.get("action")
    task_id = int(form.get("id") or 0)
    task = session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        return _with_message("/tasks", "error", "Задача не найдена")

    if action == "delete":
        # FR-16: удаление с подтверждением
        session.delete(task)
        session.commit()
        return _redirect("/tasks?ok=" + quote("Задача удалена"))

    title = (form.get("title") or "").strip()
    if not title:
        return _with_message(f"/tasks?edit={task.id}", "error", "Название не может быть пустым")
    try:
        task.planned_date = date.fromisoformat(form.get("planned_date") or "")
    except ValueError:
        return _with_message(f"/tasks?edit={task.id}", "error", "Укажите дату планирования")
    raw_deadline = form.get("deadline") or ""
    task.deadline = date.fromisoformat(raw_deadline) if raw_deadline else None
    task.title = title[:300]
    task.priority = form.get("priority") if form.get("priority") in TASK_PRIORITIES else task.priority
    task.category = form.get("category") if form.get("category") in TASK_CATEGORIES else task.category
    session.add(task)
    session.commit()
    return _redirect("/tasks?ok=" + quote("Задача обновлена"))


# ---------------- Аналитика ----------------

@pages.get("/analytics")
def analytics_page(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    return _templates(request).TemplateResponse(
        request, "analytics.html", _page_context(request, session, user)
    )


# ---------------- Настройки ----------------

@pages.get("/settings")
def settings_page(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    return _templates(request).TemplateResponse(
        request, "settings.html", _page_context(request, session, user, timezones=TIMEZONES)
    )


@pages.post("/settings")
async def settings_submit(request: Request, session: Session = Depends(get_session)):
    user = current_user_optional_impl(request, session)
    if user is None:
        return _redirect("/login")
    form = await request.form()

    payload: dict = {}
    raw_limit = (form.get("comfort_limit") or "").strip()
    if raw_limit == "":
        payload["comfort_limit"] = None
    else:
        try:
            limit = int(raw_limit)
        except ValueError:
            return _with_message("/settings", "error", "Комфортное число — это число")
        if not 1 <= limit <= 30:
            return _with_message("/settings", "error", "Комфортное число — от 1 до 30")
        payload["comfort_limit"] = limit

    theme = form.get("theme")
    if theme in ("light", "dark"):
        payload["theme"] = theme

    timezone_name = form.get("timezone")
    if timezone_name:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            return _with_message("/settings", "error", "Неизвестный часовой пояс")
        payload["timezone"] = timezone_name

    patch = ProfilePatch(**payload)
    data = patch.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    session.add(user)
    session.commit()
    return _redirect("/settings?ok=" + quote("Настройки сохранены"))
