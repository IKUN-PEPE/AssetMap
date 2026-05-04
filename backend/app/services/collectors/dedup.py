from datetime import datetime

from app.models import WebEndpoint


def touch_existing_web_endpoint(web: WebEndpoint, observed_at: datetime) -> None:
    if not web.first_seen_at:
        web.first_seen_at = observed_at
    web.last_seen_at = observed_at
