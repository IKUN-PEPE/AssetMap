import csv
import logging
from datetime import datetime
from uuid import uuid4
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.huey import huey
from app.models import CollectJob, Host, Service, SourceObservation, WebEndpoint
from app.services.normalizer.service import build_url_hash, normalize_url

logger = logging.getLogger(__name__)

def process_chunk(db: Session, job: CollectJob, chunk: list[dict], field_mapping: dict, dedup_strategy: str):
    success_in_chunk = 0
    dup_in_chunk = 0
    failed_in_chunk = 0
    
    for row in chunk:
        try:
            # 映射字段
            record = {}
            for target_field, csv_field in field_mapping.items():
                if csv_field in row:
                    record[target_field] = row[csv_field]
            
            url = record.get("url")
            ip = record.get("ip")
            port_val = record.get("port")
            
            if not url or not ip or not port_val:
                failed_in_chunk += 1
                continue
            
            try:
                port = int(port_val)
            except (ValueError, TypeError):
                failed_in_chunk += 1
                continue

            normalized_url = normalize_url(url)
            
            # 去重检测：基于 (url, ip, port)
            existing_web = db.query(WebEndpoint).join(Service).join(Host).filter(
                WebEndpoint.normalized_url == normalized_url,
                Host.ip == ip,
                Service.port == port
            ).first()
            
            if existing_web:
                if dedup_strategy == "skip":
                    dup_in_chunk += 1
                    continue
                elif dedup_strategy == "overwrite":
                    existing_web.title = record.get("title") or existing_web.title
                    # 更新 tags (存储在 source_meta 中)
                    if "tags" in record:
                        meta = existing_web.source_meta or {}
                        meta["tags"] = record["tags"]
                        existing_web.source_meta = meta
                    db.flush()
                    dup_in_chunk += 1
                    continue
                # keep_all 则继续执行插入逻辑
            
            # 获取或创建 Host
            host = db.query(Host).filter(Host.ip == ip).first()
            if not host:
                host = Host(
                    ip=ip, 
                    first_seen_at=datetime.utcnow(), 
                    last_seen_at=datetime.utcnow()
                )
                db.add(host)
                db.flush()
            
            # 获取或创建 Service
            service = db.query(Service).filter(
                Service.host_id == host.id, 
                Service.port == port
            ).first()
            if not service:
                service = Service(
                    host_id=host.id, 
                    port=port, 
                    service_name="unknown",
                    first_seen_at=datetime.utcnow(), 
                    last_seen_at=datetime.utcnow()
                )
                db.add(service)
                db.flush()
            
            # 创建 WebEndpoint
            url_hash = build_url_hash(normalized_url)
            
            # 处理 unique 约束冲突 (针对 keep_all 策略)
            if dedup_strategy == "keep_all":
                # 如果 hash 已存在，则生成一个带有随机后缀的 hash
                check_hash = db.query(WebEndpoint).filter(WebEndpoint.normalized_url_hash == url_hash).first()
                if check_hash:
                    url_hash = build_url_hash(normalized_url + "#" + str(uuid4())[:8])

            web = WebEndpoint(
                host_id=host.id,
                service_id=service.id,
                normalized_url=normalized_url,
                normalized_url_hash=url_hash,
                title=record.get("title"),
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                source_meta={
                    "tags": record.get("tags"),
                    "import_job_id": job.id
                }
            )
            db.add(web)
            
            # 创建 Observation
            obs = SourceObservation(
                collect_job_id=job.id,
                source_name="csv_import",
                raw_payload=row,
                observed_at=datetime.utcnow()
            )
            db.add(obs)
            
            success_in_chunk += 1
            
        except Exception as e:
            logger.error(f"Error processing row in job {job.id}: {e}")
            failed_in_chunk += 1
    
    # 更新任务统计
    job.success_count += success_in_chunk
    job.duplicate_count += dup_in_chunk
    job.failed_count += failed_in_chunk
    db.flush()

@huey.task()
def run_collect_task(job_id: str):
    db: Session = SessionLocal()
    job = None
    try:
        job = db.query(CollectJob).filter(CollectJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()

        # 从 query_payload 获取文件路径
        file_path = job.query_payload.get("file_path")
        if not file_path:
            job.status = "failed"
            job.error_message = "Missing file_path in query_payload"
            db.commit()
            return
        
        file_path = str(file_path)
        field_mapping = job.field_mapping or {}
        dedup_strategy = job.dedup_strategy or "skip"
        
        # 获取总行数以计算进度
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                total_rows = sum(1 for _ in f) - 1
            job.total_count = max(0, total_rows)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to count CSV rows for job {job_id}: {e}")
            job.total_count = 0

        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            chunk = []
            processed_count = 0
            
            for row in reader:
                # 支持取消：检查任务状态
                if processed_count % 10 == 0:
                    db.refresh(job)
                    if job.status == "cancelled":
                        logger.info(f"Job {job_id} was cancelled by user")
                        return

                chunk.append(row)
                if len(chunk) >= 100:
                    process_chunk(db, job, chunk, field_mapping, dedup_strategy)
                    processed_count += len(chunk)
                    if job.total_count > 0:
                        job.progress = min(99, int((processed_count / job.total_count) * 100))
                    db.commit()
                    chunk = []
            
            # 处理剩余数据
            if chunk:
                process_chunk(db, job, chunk, field_mapping, dedup_strategy)
                processed_count += len(chunk)
                db.commit()
        
        # 任务完成
        job.status = "success"
        job.progress = 100
        job.finished_at = datetime.utcnow()
        db.commit()
        logger.info(f"Job {job_id} completed successfully")

        # 联动触发：自动截图与验证
        if job.auto_verify:
            logger.info(f"Triggering auto post-process for job {job_id}")
            run_auto_post_process.schedule(args=(job_id,), delay=2)

    except Exception as e:
        logger.exception(f"Error executing collect task {job_id}: {e}")
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
    finally:
        db.close()

@huey.task()
def run_auto_post_process(job_id: str):
    """
    采集任务完成后，自动对新导入的资产进行验证和截图
    """
    db: Session = SessionLocal()
    try:
        job = db.query(CollectJob).filter(CollectJob.id == job_id).first()
        if not job:
            return

        # 查找该任务导入的所有 WebEndpoints
        all_web = db.query(WebEndpoint).all()
        target_assets = [w for w in all_web if w.source_meta and w.source_meta.get("import_job_id") == job_id]
        
        if not target_assets:
            logger.info(f"No assets found for post-processing in job {job_id}")
            return

        logger.info(f"Post-processing {len(target_assets)} assets for job {job_id}")

        # 1. 批量自动截图
        from app.services.screenshot.service import run_screenshot_job, build_output_filename
        from app.core.config import settings
        from app.models.support import Screenshot
        import asyncio

        output_dir = Path(settings.screenshot_output_dir)
        result_csv = Path(settings.result_output_dir) / 'assetmap_results.csv'
        summary_txt = Path(settings.result_output_dir) / 'assetmap_summary.txt'

        asset_rows = []
        for asset in target_assets:
            asset_rows.append({
                'seq': asset.id,
                'host': asset.domain or asset.normalized_url,
                'title': asset.title or '未命名',
                'url': asset.normalized_url,
            })

        if asset_rows:
            try:
                # 批量执行截图
                asyncio.run(run_screenshot_job(
                    asset_rows=asset_rows,
                    output_dir=output_dir,
                    result_csv=result_csv,
                    summary_txt=summary_txt,
                    skip_existing=True
                ))
                
                # 同步更新数据库状态与记录
                for asset in target_assets:
                    asset.screenshot_status = 'success'
                    # 生成预期的文件名
                    file_name = build_output_filename(asset.id, asset.title or '未命名', asset.normalized_url)
                    full_path = str(output_dir / file_name)
                    
                    # 清理旧记录并添加新记录
                    db.query(Screenshot).filter(Screenshot.web_endpoint_id == asset.id).delete(synchronize_session=False)
                    db.add(Screenshot(
                        web_endpoint_id=asset.id,
                        file_name=file_name,
                        object_path=full_path,
                        status='success'
                    ))
                
                db.commit()
                logger.info(f"Batch screenshot completed for job {job_id}")
            except Exception as e:
                logger.error(f"Batch auto screenshot failed for job {job_id}: {e}")
                db.rollback()

    except Exception as e:
        logger.exception(f"Error in auto post-process for job {job_id}: {e}")
    finally:
        db.close()
