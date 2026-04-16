import csv
from pathlib import Path


def parse_fofa_csv(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    records: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            link = (row.get("link") or "").strip()
            protocol = (row.get("protocol") or "http").strip() or "http"
            ip = (row.get("ip") or "").strip()
            port_value = (row.get("port") or "0").strip()
            try:
                port = int(port_value)
            except ValueError:
                port = 0
            url = link or _build_url(protocol, ip, port)
            records.append(
                {
                    "source": "fofa",
                    "ip": ip,
                    "port": port,
                    "protocol": protocol,
                    "domain": (row.get("domain") or "").strip() or None,
                    "url": url,
                    "title": (row.get("title") or "").strip() or None,
                    "observed_at": None,
                    "country": (row.get("country") or "").strip() or None,
                    "city": (row.get("city") or "").strip() or None,
                    "org": (row.get("org") or "").strip() or None,
                    "host": (row.get("host") or "").strip() or None,
                }
            )
    return records


def _build_url(protocol: str, ip: str, port: int) -> str:
    if not ip:
        return ""
    if port and port not in {80, 443}:
        return f"{protocol}://{ip}:{port}"
    return f"{protocol}://{ip}"
