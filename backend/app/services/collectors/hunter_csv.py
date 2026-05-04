import csv
from pathlib import Path

from app.services.collectors.base import BaseCollector


def parse_hunter_csv(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    records: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ip = (row.get("IP") or row.get("ip") or "").strip() or None
            host = (row.get("Web资产") or row.get("域名") or row.get("host") or "").strip() or None

            port_value = (row.get("端口") or row.get("port") or "").strip()
            try:
                port = int(port_value) if port_value else None
            except ValueError:
                port = None

            protocol = (row.get("协议") or row.get("protocol") or "http").strip() or "http"
            url = (row.get("url") or "").strip() or BaseCollector.build_url(protocol=protocol, host=host, ip=ip, port=port)
            if not url and not ip and not host:
                continue

            status_code_str = (row.get("网站状态码") or row.get("status_code") or "").strip()
            status_code = None
            if status_code_str:
                try:
                    status_code = int(status_code_str)
                except ValueError:
                    pass

            org = (row.get("备案单位") or row.get("运营商") or row.get("company") or "").strip() or None

            records.append(
                {
                    "source": "hunter",
                    "ip": ip,
                    "port": port,
                    "protocol": protocol,
                    "domain": (row.get("域名") or row.get("domain") or "").strip() or None,
                    "url": url,
                    "title": (row.get("网站标题") or row.get("title") or "").strip() or None,
                    "status_code": status_code,
                    "observed_at": None,
                    "country": (row.get("国家") or row.get("country") or "").strip() or None,
                    "city": (row.get("市区") or row.get("city") or "").strip() or None,
                    "org": org,
                    "host": host,
                    "raw_data": dict(row),
                }
            )
    return records
