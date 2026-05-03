import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.db import Base
from app.models.exposure_search import ExposureSearchTask, ExposureSearchResult
from app.services.exposure_search import ExposureSearchService
from app.services.exposure_search.risk_classifier import RiskClassifier

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

@pytest.mark.asyncio
async def test_handle_manual_clue(db: Session):
    import uuid
    task_id = str(uuid.uuid4())
    task = ExposureSearchTask(
        id=task_id,

        name="Test Manual Capture",
        org_keywords=["ExampleOrg"],
        title_keywords=[],
        url_keywords=[],
        file_types=[],
        sources=["manual"]
    )
    db.add(task)
    db.commit()

    service = ExposureSearchService(db=db)
    classifier = RiskClassifier(org_keywords=["ExampleOrg"])

    clue_data = {
        "title": "Sensitive ExampleOrg Data",
        "url": "http://example.com/sensitive",
        "snippet": "Internal document for ExampleOrg",
        "source_page": "https://www.bing.com/search?q=ExampleOrg"
    }

    # Call the internal handler
    await service._handle_manual_clue(task.id, classifier, clue_data)

    # Verify result saved
    result = db.query(ExposureSearchResult).filter(ExposureSearchResult.url == clue_data["url"]).first()
    assert result is not None
    assert result.task_id == task.id
    assert result.source == "manual"
    assert result.status == "valid"
    assert "Sensitive" in result.title
    assert "exampleorg" in result.matched_keywords

    # Verify task counts updated
    db.refresh(task)
    assert task.total_results == 1
    assert task.valid_count == 1

    # Verify deduplication
    await service._handle_manual_clue(task.id, classifier, clue_data)
    db.refresh(task)
    assert task.total_results == 1 # Still 1
