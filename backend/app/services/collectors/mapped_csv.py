import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(eq=True)
class MappedCsvParseResult:
    records: list[dict]
    failed_rows: int


def parse_mapped_csv(
    file_path: str | Path, field_mapping: dict[str, str]
) -> MappedCsvParseResult:
    path = Path(file_path)
    records: list[dict] = []
    failed_rows = 0

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                url = _get_value(row, field_mapping, "url")
                ip = _get_value(row, field_mapping, "ip")
                host = _get_value(row, field_mapping, "host")
                domain = _get_value(row, field_mapping, "domain")
                protocol = _get_value(row, field_mapping, "protocol") or "http"
                port = _coerce_int(_get_value(row, field_mapping, "port"))
                if not url and not ip and not host and not domain:
                    failed_rows += 1
                    continue

                status_code = _coerce_int(_get_value(row, field_mapping, "status_code"))
                records.append(
                    {
                        "source": "csv_import",
                        "ip": ip or None,
                        "port": port,
                        "protocol": protocol,
                        "domain": domain or None,
                        "url": url or None,
                        "title": _get_value(row, field_mapping, "title") or None,
                        "status_code": status_code,
                        "observed_at": None,
                        "country": _get_value(row, field_mapping, "country") or None,
                        "city": _get_value(row, field_mapping, "city") or None,
                        "org": _get_value(row, field_mapping, "org") or None,
                        "host": host or None,
                    }
                )
            except ValueError:
                failed_rows += 1

    return MappedCsvParseResult(records=records, failed_rows=failed_rows)


def _get_value(
    row: dict[str, str | None], field_mapping: dict[str, str], target_field: str
) -> str:
    column_name = field_mapping.get(target_field)
    if not column_name:
        return ""
    return (row.get(column_name) or "").strip()


def _coerce_int(raw_value: str) -> int | None:
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
