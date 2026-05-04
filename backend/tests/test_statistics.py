from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api import statistics as statistics_api
from app.models import WebEndpoint


class FilterableCountQuery:
    def __init__(self, items):
        self.items = items
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def count(self):
        result = list(self.items)
        for criterion in self.criteria:
            result = [item for item in result if _matches(item, criterion)]
        return len(result)


class FakeDb:
    def __init__(self, items):
        self.items = items

    def query(self, model):
        assert model is WebEndpoint
        return FilterableCountQuery(self.items)


def _matches(item, criterion):
    left = getattr(criterion, "left", None)
    right = getattr(criterion, "right", None)
    key = getattr(left, "key", None)
    operator = getattr(getattr(criterion, "operator", None), "__name__", None)
    value = getattr(right, "value", None)
    candidate = getattr(item, key, None)

    if operator == "ge":
        return candidate >= value
    if operator == "gt":
        return candidate > value
    if operator == "le":
        return candidate <= value
    if operator == "lt":
        return candidate < value
    if operator == "ne":
        return candidate != value
    if operator == "is_not":
        return candidate is not value
    if operator == "is_":
        return candidate is value
    return True


def test_distribution_source_expr_uses_postgres_json_text_operator():
    stmt = select(statistics_api.distribution_source_expr().label("source")).select_from(WebEndpoint)
    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "->>" in compiled
    assert "json_extract" not in compiled




def test_get_month_bounds_utc8_uses_china_calendar_month():
    assert statistics_api.get_month_bounds_utc8.__module__ == "app.api.statistics"
    start, end = statistics_api.get_month_bounds_utc8(datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc))

    assert start == datetime(2026, 3, 31, 16, 0)
    assert end == datetime(2026, 4, 30, 16, 0)


def test_get_overview_includes_month_new_count(monkeypatch):
    now = datetime(2026, 4, 22, 12, 0, 0)
    month_start = datetime(2026, 3, 31, 16, 0, 0)
    month_end = datetime(2026, 4, 30, 16, 0, 0)
    items = [
        SimpleNamespace(first_seen_at=now - timedelta(days=10), status_code=200),
        SimpleNamespace(first_seen_at=now - timedelta(days=40), status_code=200),
        SimpleNamespace(first_seen_at=now - timedelta(hours=12), status_code=500),
    ]

    monkeypatch.setattr(statistics_api, "datetime", SimpleNamespace(now=lambda tz=None: now))
    monkeypatch.setattr(statistics_api, "get_month_bounds_utc8", lambda reference=None: (month_start, month_end))

    body = statistics_api.get_overview(db=FakeDb(items))

    assert body["total"] == 3
    assert body["month_new"] == 2
    assert body["today"] == 1
    assert body["critical"] == 1
