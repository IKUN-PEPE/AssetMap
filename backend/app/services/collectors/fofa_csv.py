import csv
from pathlib import Path

from app.services.collectors.base import BaseCollector


def parse_fofa_csv(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    records: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            link = (row.get("link") or row.get("url") or "").strip()
            protocol = (row.get("protocol") or "http").strip() or "http"
            ip = (row.get("ip") or "").strip() or None
            host = (row.get("host") or row.get("domain") or "").strip() or None
            port_value = (row.get("port") or "").strip()
            try:
                port = int(port_value) if port_value else None
            except ValueError:
                port = None
            url = link or BaseCollector.build_url(protocol=protocol, host=host, ip=ip, port=port)
            if not url and not ip and not host:
                continue
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
                    "org": (row.get("org") or row.get("as_organization") or "").strip() or None,
                    "host": host,
                    "raw_data": dict(row),
                }
            )
    return records
