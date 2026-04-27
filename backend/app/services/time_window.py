from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
