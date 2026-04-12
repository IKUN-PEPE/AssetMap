import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models import Screenshot, WebEndpoint
from app.schemas import ScreenshotBatchRequest
from app.services.screenshot.service import build_output_filename, run_screenshot_job

router = APIRouter()


@router.post("/batch")
def batch_screenshots(payload: ScreenshotBatchRequest, db: Session = Depends(get_db)):
    assets = db.query(WebEndpoint).filter(WebEndpoint.id.in_(payload.asset_ids)).all()
    if not assets:
        raise HTTPException(status_code=404, detail="No assets found")

    asset_rows = [
        {
            "seq": str(index + 1),
            "host": asset.domain or asset.normalized_url,
            "title": asset.title or "未命名",
            "url": asset.normalized_url,
        }
        for index, asset in enumerate(assets)
    ]
    output_dir = Path(settings.screenshot_output_dir)
    result_csv = Path(settings.result_output_dir) / "assetmap_results.csv"
    summary_txt = Path(settings.result_output_dir) / "assetmap_summary.txt"
    result = asyncio.run(
        run_screenshot_job(
            asset_rows=asset_rows,
            output_dir=output_dir,
            result_csv=result_csv,
            summary_txt=summary_txt,
            skip_existing=payload.skip_existing,
        )
    )

    for asset in assets:
        asset.screenshot_status = "success"
        file_name = build_output_filename(asset.id, asset.title or "未命名", asset.normalized_url)
        db.add(
            Screenshot(
                web_endpoint_id=asset.id,
                file_name=file_name,
                object_path=str(output_dir / file_name),
                status="success",
            )
        )
    db.commit()
    return result
