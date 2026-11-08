"""Аутентификация API: регистрация, вход, выход (FR-1, FR-2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Config
from ..database import get_session
from ..deps import get_config, rate_limit, require_user
from ..models import DEFAULT_TIMEZONE, User
from ..schemas import LoginIn, ProfileOut, RegisterIn
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def set_auth_cookie(response: Response, user: User, config: Config) -> None:
    token = create_access_token(user.id, config)
    response.set_cookie(
        key=config.cookie_name,
        value=token,
        max_age=config.access_token_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=config.cookie_secure,
        path="/",
    )


def clear_auth_cookie(response: Response, config: Config) -> None:
    response.delete_cookie(config.cookie_name, path="/")


def _client_key(request: Request, action: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{action}:{ip}"


@router.post("/register", response_model=ProfileOut, status_code=201)
def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    config: Config = Depends(get_config),
):
    rate_limit(_client_key(request, "register"), config)

    exists = session.scalar(select(User).where(User.email == payload.email))
    if exists is not None:
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        timezone=DEFAULT_TIMEZONE,
        theme="light",
    )
    session.add(user)
    session.commit()
    set_auth_cookie(response, user, config)
    return user


@router.post("/login", response_model=ProfileOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    config: Config = Depends(get_config),
):
    rate_limit(_client_key(request, "login"), config)

    user = session.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    set_auth_cookie(response, user, config)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response, config: Config = Depends(get_config)):
    clear_auth_cookie(response, config)


@router.get("/whoami", response_model=ProfileOut)
def whoami(user: User = Depends(require_user)):
    return user
