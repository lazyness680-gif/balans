"""Обработка ошибок: API — JSON 422/429, страницы — редирект с сообщением.

Браузерная форма не должна получать «сырой» JSON: POST-запрос страницы при
невалидных данных перенаправляется обратно с параметром `error`, который
рендерит base.html (см. also pages._with_message).
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse

# Подписи полей для сообщений об ошибках (UI на русском).
FIELD_LABELS = {
    "email": "Email",
    "password": "Пароль",
    "title": "Название",
    "mood": "Настроение",
    "stress": "Стресс",
    "note": "Заметка",
    "date": "Дата",
    "planned_date": "Дата планирования",
    "task_id": "ID задачи",
    "timezone": "Часовой пояс",
    "comfort_limit": "Комфортный лимит",
    "theme": "Тема",
}

# Статусы, при которых POST-запрос страницы стоит вернуть редиректом с текстом.
_FORM_ERROR_STATUSES = {400, 401, 403, 409, 429}


def _error_field(loc) -> str | None:
    """Последний «осмысленный» сегмент loc: ('body', 'email') → 'email'."""
    for part in reversed(loc or []):
        if isinstance(part, str) and part != "body":
            return part
    return None


def _message_for_error(err: dict) -> str:
    field = _error_field(err.get("loc"))
    etype = err.get("type", "")
    empty = not str(err.get("input") or "")
    if field is None:
        return "Проверьте отправленные данные"
    if field == "email":
        return "Укажите email" if etype in ("missing", "string_type") or empty else "Некорректный email"
    if field == "password":
        if etype in ("missing", "string_type") or empty:
            return "Укажите пароль"
        if etype == "string_too_short":
            return "Пароль — не короче 6 символов"
        if etype == "string_too_long":
            return "Пароль — не длиннее 128 символов"
        return "Проверьте пароль"
    label = FIELD_LABELS.get(field) or field
    if etype == "missing" or empty:
        return f"Не заполнено поле «{label}»"
    return f"Некорректное значение в поле «{label}»"


def friendly_validation_message(errors) -> str:
    """Русские сообщения об ошибках Pydantic для HTML-страниц (вместо JSON)."""
    parts: list[str] = []
    for err in errors:
        text = _message_for_error(err)
        if text and text not in parts:
            parts.append(text)
    return "; ".join(parts) or "Проверьте введённые данные"


def page_error_redirect(request: Request, message: str) -> RedirectResponse:
    """303 назад в раздел (первый сегмент пути) с параметром error."""
    segments = [s for s in request.url.path.split("/") if s]
    target = "/" + segments[0] if segments else "/"
    query = [(k, v) for k, v in request.query_params.multi_items() if k != "error"]
    if query:
        target += "?" + urlencode(query)
    sep = "&" if "?" in target else "?"
    return RedirectResponse(f"{target}{sep}error={quote(message)}", status_code=303)


def register_error_handlers(app) -> None:
    """JSON для /api/*, дружелюбный редирект для HTML-страниц."""

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(request: Request, exc: RequestValidationError):
        if request.method == "POST" and not request.url.path.startswith("/api/"):
            return page_error_redirect(request, friendly_validation_message(exc.errors()))
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(HTTPException)
    async def _on_http_error(request: Request, exc: HTTPException):
        if (
            request.method == "POST"
            and not request.url.path.startswith("/api/")
            and exc.status_code in _FORM_ERROR_STATUSES
        ):
            return page_error_redirect(request, str(exc.detail))
        return await http_exception_handler(request, exc)
