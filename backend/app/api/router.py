from fastapi import APIRouter

from app.api import assets, jobs, labels, reports, screenshots, selections, system

api_router = APIRouter()
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(screenshots.router, prefix="/screenshots", tags=["screenshots"])
api_router.include_router(labels.router, prefix="/labels", tags=["labels"])
api_router.include_router(selections.router, prefix="/selections", tags=["selections"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
