import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import WebEndpoint

router = APIRouter()
logger = logging.getLogger(__name__)
UTC8 = timezone(timedelta(hours=8))


def get_month_bounds_utc8(reference: datetime | None = None) -> tuple[datetime, datetime]:
    current = reference or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)

    local = current.astimezone(UTC8)
    month_start_local = datetime(local.year, local.month, 1, tzinfo=UTC8)
    if local.month == 12:
        next_month_local = datetime(local.year + 1, 1, 1, tzinfo=UTC8)
    else:
        next_month_local = datetime(local.year, local.month + 1, 1, tzinfo=UTC8)

    return (
        month_start_local.astimezone(timezone.utc).replace(tzinfo=None),
        next_month_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def distribution_source_expr():
    return WebEndpoint.source_meta["source"].astext


@router.get("/overview")
def get_overview(db: Session = Depends(get_db)):
    total_assets = db.query(WebEndpoint).count()
    month_start, month_end = get_month_bounds_utc8()
    month_new = (
        db.query(WebEndpoint)
        .filter(
            WebEndpoint.first_seen_at >= month_start,
            WebEndpoint.first_seen_at < month_end,
        )
        .count()
    )

    today_start = datetime.now() - timedelta(days=1)
    today_count = (
        db.query(WebEndpoint)
        .filter(WebEndpoint.first_seen_at >= today_start)
        .count()
    )

    high_risk = db.query(WebEndpoint).filter(WebEndpoint.status_code >= 400).count()

    return {
        "total": total_assets,
        "month_new": month_new,
        "today": today_count,
        "rate": 78,
        "critical": high_risk,
    }


@router.get("/distribution")
def get_distribution(db: Session = Depends(get_db)):
    source_counts = (
        db.query(
            distribution_source_expr().label("source"),
            func.count(WebEndpoint.id).label("count"),
        )
        .group_by("source")
        .all()
    )

    sources = [
        {"name": str(item.source or "unknown"), "value": item.count}
        for item in source_counts
    ]

    success = db.query(WebEndpoint).filter(WebEndpoint.status_code == 200).count()
    failed = (
        db.query(WebEndpoint)
        .filter(
            and_(
                WebEndpoint.status_code != 200,
                WebEndpoint.status_code.is_not(None),
            )
        )
        .count()
    )
    pending = db.query(WebEndpoint).filter(WebEndpoint.status_code.is_(None)).count()

    verify_status = [
        {"name": "验证成功", "value": success},
        {"name": "验证失败", "value": failed},
        {"name": "待验证", "value": pending},
    ]

    return {"sources": sources, "verify": verify_status}


@router.get("/trends")
def get_trends(db: Session = Depends(get_db)):
    dates: list[str] = []
    data: list[int] = []

    for i in range(6, -1, -1):
        target_date = (datetime.now() - timedelta(days=i)).date()
        dates.append(target_date.strftime("%m/%d"))

        count = (
            db.query(WebEndpoint)
            .filter(func.date(WebEndpoint.first_seen_at) <= target_date)
            .count()
        )
        data.append(count)

    return {"dates": dates, "data": data}
