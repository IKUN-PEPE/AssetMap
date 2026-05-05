from fastapi import APIRouter

from app.api import (
    assets,
    exposure_search,
    jobs,
    labels,
    logs,
    reports,
    screenshots,
    system,
    statistics,
)

api_router = APIRouter()
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(exposure_search.router, prefix="/exposure-search", tags=["exposure-search"])
api_router.include_router(statistics.router, prefix="/stats", tags=["stats"])
api_router.include_router(screenshots.router, prefix="/screenshots", tags=["screenshots"])
api_router.include_router(labels.router, prefix="/labels", tags=["labels"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
