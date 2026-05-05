from __future__ import annotations

import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.system_service import SystemConfigService
from app.tasks.bootstrap import create_all_tables


def wait_for_database(database_url: str | None = None, *, retries: int = 30, delay: float = 1.0) -> None:
    target_url = database_url or settings.database_url
    engine = create_engine(target_url, future=True)
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[init_db] database is ready on attempt {attempt}")
            return
        except Exception as exc:  # pragma: no cover - exercised through retry behavior
            last_error = exc
            print(f"[init_db] waiting for database ({attempt}/{retries}): {exc}")
            time.sleep(delay)
        finally:
            engine.dispose()

    raise RuntimeError(f"database is not ready after {retries} attempts") from last_error


def drop_legacy_selection_tables(db) -> None:
    for statement in (
        "DROP TABLE IF EXISTS selection_items",
        "DROP TABLE IF EXISTS saved_selections",
    ):
        db.execute(text(statement))
    db.commit()


def init_database(*, drop_all: bool = False) -> None:
    wait_for_database()
    create_all_tables(drop_all=drop_all)

    db = SessionLocal()
    try:
        drop_legacy_selection_tables(db)
        SystemConfigService.init_defaults(db)
        print("[init_db] schema initialized")
        print("[init_db] default system configs initialized")
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


def init() -> None:
    init_database()


if __name__ == "__main__":
    init_database()
    print("[init_db] database tables created and seeded")
