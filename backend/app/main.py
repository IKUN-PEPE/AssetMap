import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.services.logs.runtime_buffer import runtime_log_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
runtime_log_handler.setFormatter(logging.Formatter("%(message)s"))
root_logger = logging.getLogger()
if runtime_log_handler not in root_logger.handlers:
    root_logger.addHandler(runtime_log_handler)

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.add_middleware(
      CORSMiddleware,
      allow_origins=[
          "http://127.0.0.1:5173",
          "http://localhost:5173",
          "http://127.0.0.1:9527",
          "http://localhost:9527",
      ],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
      expose_headers=["Content-Disposition"],
  )
app.mount(
    "/static/screenshots",
    StaticFiles(directory=Path(settings.screenshot_output_dir), check_dir=False),
    name="screenshots",
)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
