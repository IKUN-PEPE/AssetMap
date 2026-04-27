from hashlib import sha256
from urllib.parse import urlsplit


def _looks_like_http_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _format_host_for_url(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""

    try:
        parts = urlsplit(value if _looks_like_http_url(value) else f"https://{value}")
    except Exception:
        return ""

    scheme = (parts.scheme or "https").lower()
    if scheme not in {"http", "https"}:
        return ""
    if parts.username or parts.password:
        # urlsplit already separates credentials; reject nothing, just ignore them.
        pass

    host = (parts.hostname or "").strip().lower()
    if not host:
        return ""

    netloc = _format_host_for_url(host)
    try:
        port = parts.port
    except ValueError:
        return ""

    if port is not None:
        netloc = f"{netloc}:{port}"

    path = parts.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{scheme}://{netloc}{path}"


def build_url_hash(url: str) -> str:
    normalized_url = normalize_url(url)
    return sha256(normalized_url.encode("utf-8")).hexdigest()
