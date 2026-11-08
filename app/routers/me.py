"""Профиль: GET/PATCH /api/me (FR-4, FR-23, FR-38…FR-40)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_session
from ..deps import require_user
from ..models import User
from ..schemas import ProfileOut, ProfilePatch

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=ProfileOut)
def get_me(user: User = Depends(require_user)):
    return user


@router.patch("/me", response_model=ProfileOut)
def patch_me(
    payload: ProfilePatch,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    data = payload.model_dump(exclude_unset=True)
    if "comfort_limit" in data:
        user.comfort_limit = data["comfort_limit"]
    if "theme" in data and data["theme"] is not None:
        user.theme = data["theme"]
    if "timezone" in data and data["timezone"] is not None:
        user.timezone = data["timezone"]
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
