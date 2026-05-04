import csv
from pathlib import Path

from app.services.collectors.base import BaseCollector


def parse_zoomeye_csv(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    records: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ip = (row.get("ip") or "").strip() or None
            host = (row.get("site") or row.get("domain") or row.get("host") or "").strip() or None
            port_value = (row.get("portinfo.port") or row.get("port") or "").strip()
            try:
                port = int(port_value) if port_value else None
            except ValueError:
                port = None
            protocol = (row.get("service.app") or row.get("protocol") or "http").strip() or "http"
            url = (row.get("site") or row.get("url") or "").strip() or BaseCollector.build_url(protocol=protocol, host=host, ip=ip, port=port)
            if not url and not ip and not host:
                continue
            records.append(
                {
                    "source": "zoomeye",
                    "ip": ip,
                    "port": port,
                    "protocol": protocol,
                    "domain": (row.get("domain") or row.get("site") or "").strip() or None,
                    "url": url,
                    "title": (row.get("title") or row.get("site.title") or "").strip() or None,
                    "status_code": None,
                    "observed_at": None,
                    "country": (row.get("geoinfo.country.names.zh-CN") or row.get("country") or "").strip() or None,
                    "city": (row.get("geoinfo.city.names.zh-CN") or row.get("city") or "").strip() or None,
                    "org": (row.get("org") or "").strip() or None,
                    "host": host,
                    "raw_data": dict(row),
                }
            )
    return records
