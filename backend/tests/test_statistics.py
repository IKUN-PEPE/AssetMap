from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api.statistics import distribution_source_expr
from app.models import WebEndpoint


def test_distribution_source_expr_uses_postgres_json_text_operator():
    stmt = select(distribution_source_expr().label("source")).select_from(WebEndpoint)
    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "->>" in compiled
    assert "json_extract" not in compiled
