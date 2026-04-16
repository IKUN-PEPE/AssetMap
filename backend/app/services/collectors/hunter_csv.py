import csv
from pathlib import Path


def parse_hunter_csv(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    records: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ip = (row.get("IP") or "").strip()
            if not ip:
                continue

            port_value = (row.get("端口") or "0").strip()
            try:
                port = int(port_value)
            except ValueError:
                port = 0

            protocol = (row.get("协议") or "http").strip() or "http"
            url = (row.get("url") or "").strip()
            if not url:
                if port and port not in {80, 443}:
                    url = f"{protocol}://{ip}:{port}"
                else:
                    url = f"{protocol}://{ip}"

            status_code_str = (row.get("网站状态码") or "").strip()
            status_code = None
            if status_code_str:
                try:
                    status_code = int(status_code_str)
                except ValueError:
                    pass

            org = (row.get("备案单位") or row.get("运营商") or "").strip() or None

            records.append(
                {
                    "source": "hunter",
                    "ip": ip,
                    "port": port,
                    "protocol": protocol,
                    "domain": (row.get("域名") or "").strip() or None,
                    "url": url,
                    "title": (row.get("网站标题") or "").strip() or None,
                    "status_code": status_code,
                    "observed_at": None,
                    "country": (row.get("国家") or "").strip() or None,
                    "city": (row.get("市区") or "").strip() or None,
                    "org": org,
                    "host": (row.get("Web资产") or "").strip() or None,
                }
            )
    return records
