from datetime import datetime

from sqlalchemy.orm import Session

from app.models import CollectJob, Host, Service, SourceObservation, WebEndpoint
from app.services.collectors.dedup import touch_existing_web_endpoint
from app.services.normalizer.service import build_url_hash, normalize_url


class SampleImportService:
    def import_records(self, db: Session, job: CollectJob, records: list[dict]) -> dict[str, int]:
        imported = 0
        current_now = datetime.now()
        for record in records:
            # 强化时间解析逻辑：即使 record.get("observed_at") 键不存在或值为 None，也必须返回一个时间对象
            observed_at = self._parse_dt(record.get("observed_at")) or current_now

            host = db.query(Host).filter(Host.ip == record["ip"]).one_or_none()
            if not host:
                host = Host(
                    ip=record["ip"],
                    org_name=record.get("org"),
                    country=record.get("country"),
                    city=record.get("city"),
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                )
                db.add(host)
                db.flush()

            service = (
                db.query(Service)
                .filter(Service.host_id == host.id, Service.port == record["port"], Service.service_name == record["protocol"])
                .one_or_none()
            )
            if not service:
                service = Service(
                    host_id=host.id,
                    port=record["port"],
                    protocol=record["protocol"],
                    service_name=record["protocol"],
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                )
                db.add(service)
                db.flush()

            normalized_url = normalize_url(record["url"])
            normalized_url_hash = build_url_hash(normalized_url)
            web = db.query(WebEndpoint).filter(WebEndpoint.normalized_url_hash == normalized_url_hash).one_or_none()
            if not web:
                web = WebEndpoint(
                    host_id=host.id,
                    service_id=service.id,
                    normalized_url=normalized_url,
                    normalized_url_hash=normalized_url_hash,
                    domain=record.get("domain"),
                    title=record.get("title"),
                    status_code=record.get("status_code"),
                    scheme=record.get("protocol"),
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                    source_meta={
                        "source": record.get("source"),
                        "host": record.get("host"),
                        "org": record.get("org"),
                        "country": record.get("country"),
                        "city": record.get("city"),
                    },
                )
                db.add(web)
            else:
                touch_existing_web_endpoint(web, observed_at)

            db.flush()

            db.add(
                SourceObservation(
                    collect_job_id=job.id,
                    source_name=record.get("source", "sample"),
                    source_record_id=f"{record.get('source', 'sample')}:{record['ip']}:{record['port']}",
                    observed_at=observed_at,
                    raw_payload=record,
                    quota_meta={"mode": "sample" if record.get("source") == "sample" else "import"},
                )
            )
            imported += 1
        db.commit()
        return {"imported": imported}

    @staticmethod
    def _parse_dt(value: str | None):
        if not value:
            return None
        return datetime.fromisoformat(value)
