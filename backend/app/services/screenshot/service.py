import logging
from pathlib import Path

from app.services.screenshot.core import (
    build_candidate_urls,
    build_output_filename,
    build_output_path,
    build_result_row,
    build_summary,
    classify_failure_reason,
    finalize_screenshot_path,
    render_summary_text,
    run_batch,
    write_results_csv,
    write_summary_text,
)

LOGGER = logging.getLogger("assetmap.screenshot")


def build_screenshot_job_config(asset_rows: list[dict], output_dir: Path, result_csv: Path, summary_txt: Path) -> dict:
    return {
        "assets": asset_rows,
        "output_dir": output_dir,
        "result_csv": result_csv,
        "summary_txt": summary_txt,
    }


async def run_screenshot_job(
    asset_rows: list[dict[str, str]],
    output_dir: Path,
    result_csv: Path,
    summary_txt: Path,
    timeout_sec: int = 15,
    wait_after_load: int = 5,
    concurrency: int = 5,
    retry_count: int = 1,
    skip_existing: bool = True,
    headful: bool = False,
) -> dict[str, str]:
    results = await run_batch(
        assets=asset_rows,
        out_dir=output_dir,
        timeout_sec=timeout_sec,
        wait_after_load=wait_after_load,
        concurrency=concurrency,
        retry_count=retry_count,
        skip_existing=skip_existing,
        headful=headful,
        logger=LOGGER,
    )
    write_results_csv(results, result_csv)
    summary = build_summary(results)
    summary_text = render_summary_text(summary)
    write_summary_text(summary_txt, summary_text)
    return {
        "result_csv": str(result_csv),
        "summary_txt": str(summary_txt),
        "summary_text": summary_text,
    }


__all__ = [
    "build_candidate_urls",
    "build_output_filename",
    "build_output_path",
    "build_result_row",
    "build_screenshot_job_config",
    "build_summary",
    "classify_failure_reason",
    "finalize_screenshot_path",
    "run_screenshot_job",
]
