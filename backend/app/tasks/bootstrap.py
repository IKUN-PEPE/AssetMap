from app.core.db import Base, engine
from app.models import *  # noqa: F401,F403


def create_all_tables(drop_all: bool = False) -> None:
    if drop_all:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
