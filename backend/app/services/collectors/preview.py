import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_csv_source(headers: list[str]) -> str | None:
    normalized = {header.strip().lower() for header in headers if header}
    if {"link", "ip", "port"}.issubset(normalized):
        return "fofa"
    if {"ip", "端口", "网站标题"}.issubset(normalized):
        return "hunter"
    if any(header in normalized for header in {"site", "portinfo.port", "service.app"}):
        return "zoomeye"
    if any(header in normalized for header in {"service", "http_load_url", "port", "url"}):
        return "quake"
    return None


def get_csv_preview(file_path: Path) -> dict:
    headers = []
    rows = []

    if not file_path.exists():
        logger.error("File not found for preview: %s", file_path)
        return {"headers": [], "rows": [], "detected_source_type": None}

    try:
        with open(file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames if reader.fieldnames else []
            if not headers:
                raise ValueError("CSV 文件缺少表头")

            count = 0
            for row in reader:
                if count >= 10:
                    break
                rows.append({k: (v if v is not None else "") for k, v in row.items()})
                count += 1

            if not rows:
                raise ValueError("CSV 文件缺少表头")

        logger.info("Generated CSV preview for %s, rows=%s", file_path.name, len(rows))
    except Exception as exc:
        logger.exception("Failed to get CSV preview for %s: %s", file_path, exc)
        raise exc

    return {"headers": headers, "rows": rows, "detected_source_type": detect_csv_source(headers)}
