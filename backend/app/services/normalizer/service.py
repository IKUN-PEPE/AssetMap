from hashlib import sha256
from urllib.parse import urlsplit


def normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return value
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parts = urlsplit(value)
    path = parts.path.rstrip("/") or "/"
    return f"{parts.scheme}://{parts.netloc}{path}"


def build_url_hash(url: str) -> str:
    normalized_url = normalize_url(url)
    return sha256(normalized_url.encode("utf-8")).hexdigest()
