import shutil
from pathlib import Path
from uuid import uuid4

from app.services.collectors.mapped_csv import MappedCsvParseResult, parse_mapped_csv


def test_parse_mapped_csv_maps_required_and_optional_fields():
    tmp_dir = Path("backend/tests") / f"tmp_{uuid4().hex}"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        csv_path = tmp_dir / "assets.csv"
        csv_path.write_text(
            "link,host_ip,svc_port,site_title,proto,status\n"
            "https://demo.example.com,1.1.1.1,443,Portal,https,200\n",
            encoding="utf-8-sig",
        )

        result = parse_mapped_csv(
            csv_path,
            {
                "url": "link",
                "ip": "host_ip",
                "port": "svc_port",
                "title": "site_title",
                "protocol": "proto",
                "status_code": "status",
            },
        )

        assert result == MappedCsvParseResult(
            records=[
                {
                    "source": "csv_import",
                    "ip": "1.1.1.1",
                    "port": 443,
                    "protocol": "https",
                    "domain": None,
                    "url": "https://demo.example.com",
                    "title": "Portal",
                    "status_code": 200,
                    "observed_at": None,
                    "country": None,
                    "city": None,
                    "org": None,
                    "host": None,
                }
            ],
            failed_rows=0,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_parse_mapped_csv_counts_bad_rows_and_defaults_protocol():
    tmp_dir = Path("backend/tests") / f"tmp_{uuid4().hex}"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        csv_path = tmp_dir / "assets.csv"
        csv_path.write_text(
            "url,ip,port,title\n"
            "https://demo.example.com,1.1.1.1,443,Portal\n"
            "https://broken.example.com,2.2.2.2,not-a-port,Broken\n"
            ",3.3.3.3,8443,Missing Url\n",
            encoding="utf-8-sig",
        )

        result = parse_mapped_csv(
            csv_path,
            {"url": "url", "ip": "ip", "port": "port", "title": "title"},
        )

        assert result.failed_rows == 1
        assert result.records == [
            {
                "source": "csv_import",
                "ip": "1.1.1.1",
                "port": 443,
                "protocol": "http",
                "domain": None,
                "url": "https://demo.example.com",
                "title": "Portal",
                "status_code": None,
                "observed_at": None,
                "country": None,
                "city": None,
                "org": None,
                "host": None,
            },
            {
                "source": "csv_import",
                "ip": "3.3.3.3",
                "port": 8443,
                "protocol": "http",
                "domain": None,
                "url": None,
                "title": "Missing Url",
                "status_code": None,
                "observed_at": None,
                "country": None,
                "city": None,
                "org": None,
                "host": None,
            },
        ]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
