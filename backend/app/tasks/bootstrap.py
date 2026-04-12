from app.core.db import Base, engine
from app.models import *  # noqa: F401,F403


def create_all_tables() -> None:
    Base.metadata.create_all(bind=engine)
