from fastapi import APIRouter, Query

from app.services.logs.runtime_buffer import runtime_log_buffer

router = APIRouter()


@router.get("/recent")
def get_recent_logs(
    source: str = Query("all", pattern="^(task|service|all)$"),
    limit: int = Query(200, ge=1, le=500),
    since: str | None = None,
):
    items = runtime_log_buffer.list_recent(source=source, since=since, limit=limit)
    next_since = items[-1]["timestamp"] if items else since
    return {"items": items, "next_since": next_since}
