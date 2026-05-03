from sqlalchemy import create_engine, JSON
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import sqlalchemy.dialects.postgresql as postgresql
from sqlalchemy.sql.operators import ColumnOperators

from app.core.config import settings

# SQLite compatibility: Map JSONB to JSON and shim .astext
if settings.database_url.startswith("sqlite"):
    postgresql.JSONB = JSON
    if not hasattr(ColumnOperators, 'astext'):
        ColumnOperators.astext = property(lambda self: self)


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
