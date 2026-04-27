from pathlib import Path

from app.models.support import Screenshot


class PostProcessResult:
    def __init__(self):
        self.verified_success = 0
        self.verified_failed = 0
        self.screenshot_success = 0
        self.screenshot_failed = 0


def run_auto_post_process_impl(
    job_id: str,
    *,
    session_factory,
    open_job_logger,
    close_job_logger,
    load_job,
    is_job_cancelled,
    iter_job_scoped_assets,
    run_coro_in_fresh_loop,
    verify_assets_for_post_process,
    append_post_process_job_link,
    append_stage_job_link,
):
    from app.core.config import settings
    from app.services.screenshot.service import build_output_filename, run_screenshot_job

    db = session_factory()
    task_logger, file_handler, job_logger = open_job_logger(job_id, mode="a")
    result = PostProcessResult()
    try:
        job = load_job(db, job_id)
        if not job or job.status == "cancelled":
            return

        ordered_assets = iter_job_scoped_assets(db, job_id)
        if not ordered_assets:
            job_logger.info("Auto verify skipped: no collected assets")
            return

        if is_job_cancelled(db, job_id):
            return

        job_logger.info("Auto verify start assets=%s", len(ordered_assets))
        try:
            verify_results = run_coro_in_fresh_loop(verify_assets_for_post_process(ordered_assets))
            for asset in ordered_assets:
                status_code, verify_error = verify_results.get(asset.id, (None, "未执行验证"))
                asset.status_code = status_code
                asset.verified = status_code is not None
                source_meta = dict(asset.source_meta or {})
                append_post_process_job_link(source_meta, job_id)
                append_stage_job_link(source_meta, "verify_job_ids", job_id)
                if verify_error:
                    source_meta["verify_error"] = verify_error
                    result.verified_failed += 1
                    job_logger.warning(
                        "Verify failed asset_id=%s url=%s reason=%s",
                        asset.id,
                        asset.normalized_url,
                        verify_error,
                    )
                else:
                    source_meta.pop("verify_error", None)
                    result.verified_success += 1
                    job_logger.info(
                        "Verify success asset_id=%s url=%s status=%s",
                        asset.id,
                        asset.normalized_url,
                        status_code,
                    )
                asset.source_meta = source_meta
            db.commit()
        except Exception as exc:
            for asset in ordered_assets:
                source_meta = dict(asset.source_meta or {})
                append_post_process_job_link(source_meta, job_id)
                append_stage_job_link(source_meta, "verify_job_ids", job_id)
                source_meta["verify_error"] = str(exc)
                asset.source_meta = source_meta
                asset.verified = False
                result.verified_failed += 1
                job_logger.warning(
                    "Verify failed asset_id=%s url=%s reason=%s",
                    asset.id,
                    asset.normalized_url,
                    exc,
                )
            db.commit()

        job_logger.info("Verify post-process finished success=%s failed=%s", result.verified_success, result.verified_failed)

        output_dir = Path(settings.screenshot_output_dir)
        result_csv = Path(settings.result_output_dir) / "assetmap_results.csv"
        summary_txt = Path(settings.result_output_dir) / "assetmap_summary.txt"

        asset_rows = [
            {
                "seq": asset.id,
                "host": asset.domain or asset.normalized_url,
                "title": asset.title or "未命名站点",
                "url": asset.normalized_url,
            }
            for asset in ordered_assets
        ]

        if asset_rows:
            job_logger.info("Screenshot post-process start assets=%s", len(asset_rows))
            try:
                run_coro_in_fresh_loop(
                    run_screenshot_job(
                        asset_rows=asset_rows,
                        output_dir=output_dir,
                        result_csv=result_csv,
                        summary_txt=summary_txt,
                        skip_existing=True,
                    )
                )
            except Exception as exc:
                for asset in ordered_assets:
                    source_meta = dict(asset.source_meta or {})
                    append_post_process_job_link(source_meta, job_id)
                    append_stage_job_link(source_meta, "screenshot_job_ids", job_id)
                    source_meta["screenshot_error"] = str(exc)
                    asset.source_meta = source_meta
                    asset.screenshot_status = "failed"
                    result.screenshot_failed += 1
                    job_logger.warning(
                        "Screenshot failed asset_id=%s reason=%s",
                        asset.id,
                        exc,
                    )
                db.commit()
            else:
                if is_job_cancelled(db, job_id):
                    return

                for asset in ordered_assets:
                    source_meta = dict(asset.source_meta or {})
                    append_post_process_job_link(source_meta, job_id)
                    append_stage_job_link(source_meta, "screenshot_job_ids", job_id)
                    file_name = build_output_filename(asset.id, asset.title or "未命名站点", asset.normalized_url)
                    screenshot_path = output_dir / file_name
                    db.query(Screenshot).filter(Screenshot.web_endpoint_id == asset.id).delete(synchronize_session=False)
                    if screenshot_path.exists():
                        asset.screenshot_status = "success"
                        source_meta.pop("screenshot_error", None)
                        db.add(
                            Screenshot(
                                web_endpoint_id=asset.id,
                                file_name=file_name,
                                object_path=str(screenshot_path),
                                status="success",
                            )
                        )
                        result.screenshot_success += 1
                        job_logger.info("Screenshot success asset_id=%s file=%s", asset.id, file_name)
                    else:
                        asset.screenshot_status = "failed"
                        source_meta["screenshot_error"] = "截图文件未生成"
                        result.screenshot_failed += 1
                        job_logger.warning("Screenshot failed asset_id=%s reason=missing-file", asset.id)
                    asset.source_meta = source_meta
                db.commit()
                job_logger.info(
                    "Screenshot post-process finished success=%s failed=%s",
                    result.screenshot_success,
                    result.screenshot_failed,
                )

        job_logger.info(
            "Auto verify finished verify_success=%s verify_failed=%s screenshot_success=%s screenshot_failed=%s",
            result.verified_success,
            result.verified_failed,
            result.screenshot_success,
            result.screenshot_failed,
        )
    except Exception as exc:
        job_logger.exception("Post-process failed: %s", exc)
    finally:
        close_job_logger(task_logger, file_handler)
        db.close()
