import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.db import Base
from app.models.exposure_search import ExposureSearchTask, ExposureSearchResult

@pytest.fixture
def db():
    # Use SQLite for tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_exposure_search_models(db: Session):
    # This should fail if models are not defined correctly or if JSONB issues persist
    from app.models.exposure_search import ExposureSearchTask, ExposureSearchResult
    
    task = ExposureSearchTask(
        name="测试任务",
        org_keywords=["test"],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=["bing"]
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    
    assert task.id is not None
    assert task.name == "测试任务"
    
    result = ExposureSearchResult(
        task_id=task.id,
        source="bing",
        query="test",
        title="Test Result",
        url="http://example.com"
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    
    assert result.id is not None
    assert result.task.name == "测试任务"
