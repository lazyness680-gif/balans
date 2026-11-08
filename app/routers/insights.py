"""API рекомендаций и аналитики (FR-20…FR-26, FR-30…FR-36)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_session
from ..deps import require_user
from ..models import MOOD_TAGS, User
from ..services.analytics import build_analytics, build_digest
from ..services.recommendation import build_recommendation

router = APIRouter(prefix="/api", tags=["insights"])


def _parse_tags(tags: list[str] | None) -> list[str]:
    """Принимает повторяющиеся параметры и запятые: ?tags=сон,работа."""
    result: list[str] = []
    for raw in tags or []:
        for part in raw.split(","):
            part = part.strip()
            if part and part in MOOD_TAGS and part not in result:
                result.append(part)
    return result


@router.get("/recommendations/today")
def recommendations_today(
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    return build_recommendation(session, user)


@router.get("/analytics")
def analytics(
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
    period: int = Query(default=7),
    tags: list[str] | None = Query(default=None),
):
    return build_analytics(
        session, user, period=period, tags=_parse_tags(tags)
    )


@router.get("/digest")
def digest(
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
    period: str = Query(default="week"),
):
    if period not in ("week", "month"):
        period = "week"
    return build_digest(session, user, period=period)
