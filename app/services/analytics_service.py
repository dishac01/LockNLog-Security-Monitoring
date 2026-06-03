from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, desc, func

from app.extensions import db
from app.models.log import Log


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_risk_trend(days: int = 14) -> list[dict[str, Any]]:
    start = _utcnow() - timedelta(days=days)
    rows = (
        db.session.query(
            func.date(Log.timestamp).label("d"),
            func.avg(Log.risk_score).label("avg_risk"),
            func.sum(case((Log.risk_band == "CRITICAL", 1), else_=0)).label("critical_events"),
        )
        .filter(Log.timestamp >= start, Log.risk_score.isnot(None))
        .group_by("d")
        .order_by("d")
        .all()
    )
    return [
        {
            "date": str(r.d),
            "avg_risk_score": round(float(r.avg_risk or 0.0), 4),
            "critical_events": int(r.critical_events or 0),
        }
        for r in rows
    ]


def get_top_assets(limit: int = 10) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            Log.asset_id,
            func.avg(Log.risk_score).label("avg_risk"),
            func.sum(case((Log.anomaly_score >= 0.7, 1), else_=0)).label("anomaly_count"),
            func.sum(case((Log.risk_band == "CRITICAL", 1), else_=0)).label("critical_count"),
            func.count(Log.id).label("event_count"),
        )
        .filter(Log.asset_id.isnot(None), Log.risk_score.isnot(None))
        .group_by(Log.asset_id)
        .order_by(desc("avg_risk"))
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        avg = float(r.avg_risk or 0)
        band = "LOW" if avg <= 0.3 else "MEDIUM" if avg <= 0.6 else "HIGH" if avg <= 0.8 else "CRITICAL"
        out.append(
            {
                "asset_id": r.asset_id,
                "avg_risk_score": round(avg, 4),
                "anomaly_count": int(r.anomaly_count or 0),
                "critical_count": int(r.critical_count or 0),
                "event_count": int(r.event_count or 0),
                "risk_band": band,
            }
        )
    return out


def get_top_users(limit: int = 10) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            Log.user_id,
            func.avg(Log.risk_score).label("avg_risk"),
            func.sum(case((Log.anomaly_score >= 0.7, 1), else_=0)).label("anomaly_count"),
            func.count(Log.id).label("event_count"),
        )
        .filter(Log.user_id.isnot(None), Log.risk_score.isnot(None))
        .group_by(Log.user_id)
        .order_by(desc("avg_risk"))
        .limit(limit)
        .all()
    )
    return [
        {
            "user_id": int(r.user_id),
            "avg_risk_score": round(float(r.avg_risk or 0), 4),
            "anomaly_count": int(r.anomaly_count or 0),
            "event_count": int(r.event_count or 0),
        }
        for r in rows
    ]


def get_hotspots(limit: int = 10) -> list[dict[str, Any]]:
    logs = Log.query.filter(Log.risk_score.isnot(None)).all()
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"event_type": "", "asset_name": "", "count": 0, "avg_risk_score": 0.0}
    )
    for log in logs:
        event = str(log.event_type or "unknown_event")
        asset = str(log.asset.name if log.asset else (log.asset_id or "unknown-asset"))
        key = (event.lower(), asset.lower())
        g = grouped[key]
        g["event_type"] = event
        g["asset_name"] = asset
        g["count"] += 1
        g["avg_risk_score"] += float(log.risk_score or 0)
    out: list[dict[str, Any]] = []
    for g in grouped.values():
        n = max(1, int(g["count"]))
        avg = float(g["avg_risk_score"]) / n
        out.append(
            {
                "event_type": g["event_type"],
                "asset_name": g["asset_name"],
                "count": int(g["count"]),
                "avg_risk_score": round(avg, 4),
            }
        )
    out.sort(key=lambda x: (x["avg_risk_score"], x["count"]), reverse=True)
    return out[:limit]


def get_dashboard_summary() -> dict[str, Any]:
    total = Log.query.count()
    bands = Counter((row[0] or "UNKNOWN") for row in db.session.query(Log.risk_band).all())
    avg_risk = db.session.query(func.avg(Log.risk_score)).scalar() or 0.0
    return {
        "total_logs": int(total),
        "avg_risk_score": round(float(avg_risk), 4),
        "risk_bands": dict(bands),
        "top_assets": get_top_assets(5),
        "top_users": get_top_users(5),
        "hotspots": get_hotspots(5),
        "risk_trend": get_risk_trend(10),
    }
