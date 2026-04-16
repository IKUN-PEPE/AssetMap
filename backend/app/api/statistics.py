import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import WebEndpoint

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/overview")
def get_overview(db: Session = Depends(get_db)):
    """获取顶部 KPI 指标数据"""
    total_assets = db.query(WebEndpoint).count()

    # 最近 24 小时新增
    today_start = datetime.now() - timedelta(days=1)
    today_count = db.query(WebEndpoint).filter(WebEndpoint.first_seen_at >= today_start).count()

    # 风险资产 (状态码 >= 400)
    high_risk = db.query(WebEndpoint).filter(WebEndpoint.status_code >= 400).count()

    return {
        "total": total_assets,
        "today": today_count,
        "rate": 78,  # 模拟发现率
        "critical": high_risk
    }

@router.get("/distribution")
def get_distribution(db: Session = Depends(get_db)):
    """获取来源分布和验证状态分布"""
    # 来源分布
    source_counts = db.query(
        func.json_extract(WebEndpoint.source_meta, '$.source').label('source'),
        func.count(WebEndpoint.id).label('count')
    ).group_by('source').all()

    sources = [{"name": str(s.source).strip('"') or "unknown", "value": s.count} for s in source_counts]

    # 验证状态
    success = db.query(WebEndpoint).filter(WebEndpoint.status_code == 200).count()
    failed = db.query(WebEndpoint).filter(and_(WebEndpoint.status_code != 200, WebEndpoint.status_code != None)).count()
    pending = db.query(WebEndpoint).filter(WebEndpoint.status_code == None).count()

    verify_status = [
        {"name": "访问成功", "value": success},
        {"name": "访问失败", "value": failed},
        {"name": "待验证", "value": pending},
    ]

    return {
        "sources": sources,
        "verify": verify_status
    }

@router.get("/trends")
def get_trends(db: Session = Depends(get_db)):
    """获取 7 天发现趋势"""
    dates = []
    data = []

    for i in range(6, -1, -1):
        target_date = (datetime.now() - timedelta(days=i)).date()
        dates.append(target_date.strftime("%m/%d"))

        # 统计在那天之前发现的所有资产（累积）
        count = db.query(WebEndpoint).filter(func.date(WebEndpoint.first_seen_at) <= target_date).count()
        data.append(count)

    return {
        "dates": dates,
        "data": data
    }
