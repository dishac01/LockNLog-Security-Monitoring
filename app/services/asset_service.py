from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, func

from app.extensions import db
from app.models.asset import Asset
from app.models.log import Log
from app.services.access_request_service import compute_effective_departments, normalize_department


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_asset_risk_score(asset_id: str) -> float:
    """
    Heuristic: average of recent risk_score values for this asset.
    If no scores exist yet, returns 0.0.
    """
    rows = (
        db.session.query(func.avg(Log.risk_score))
        .filter(Log.asset_id == asset_id, Log.risk_score.isnot(None))
        .scalar()
    )
    return float(rows or 0.0)


def compute_asset_last_activity(asset_id: str) -> datetime | None:
    ts = (
        db.session.query(func.max(Log.timestamp))
        .filter(Log.asset_id == asset_id)
        .scalar()
    )
    return ts


def refresh_asset_computed_fields(asset: Asset) -> Asset:
    asset.risk_score = compute_asset_risk_score(asset.id)
    asset.last_activity = compute_asset_last_activity(asset.id)
    return asset


def _asset_visible_to_user(asset: Asset, effective_departments: set[str]) -> bool:
    if not effective_departments:
        return False
    return normalize_department(asset.department) in effective_departments


def list_assets_for_session(
    *,
    role: str,
    user_id: int | None,
    user_department: str | None,
) -> list[Asset]:
    role_n = (role or "observer").lower().strip()
    if role_n in {"admin", "ceo"}:
        return Asset.query.order_by(Asset.department.asc(), Asset.name.asc()).all()
    if role_n == "observer":
        return Asset.query.order_by(Asset.department.asc(), Asset.name.asc()).all()

    effective_depts = compute_effective_departments(user_department, role_n, user_id)
    assets = Asset.query.order_by(Asset.department.asc(), Asset.name.asc()).all()
    return [a for a in assets if _asset_visible_to_user(a, effective_depts)]


def filter_asset_fields(asset: Asset, role: str) -> dict:
    """
    Field-level visibility by role (single-table assets, role-scoped fields).
    - Finance -> sees finance fields
    - HR -> sees HR fields
    - SOC -> sees network fields
    - Admin/CEO -> full
    - Observer -> safe summary
    """
    r = (role or "observer").lower().strip()
    base = {
        "id": asset.id,
        "name": asset.name,
        "department": asset.department,
        "asset_type": asset.asset_type,
        "business_value": asset.business_value,
        "criticality": asset.criticality,
        "sensitivity": asset.sensitivity,
        "risk_score": asset.risk_score,
        "last_activity": asset.last_activity.isoformat() if asset.last_activity else None,
    }

    if r in {"admin", "ceo"}:
        d = asset.to_dict()
        return d

    if r == "finance":
        base.update(
            {
                "transaction_volume": asset.transaction_volume,
                "avg_transaction_amount": asset.avg_transaction_amount,
            }
        )
        return base

    if r == "hr":
        base.update(
            {
                "data_types": asset.data_types_json,
                "employee_count": asset.employee_count,
            }
        )
        return base

    if r == "soc":
        base.update(
            {
                "ip_address": asset.ip_address,
                "exposed_ports": asset.exposed_ports_json,
                "exposure": asset.exposure,
            }
        )
        return base

    # observer + unknown roles: summary only
    return base


def get_asset_detail_payload(asset_id: str, role: str) -> dict:
    asset = db.session.get(Asset, asset_id)
    if not asset:
        raise LookupError("asset not found")
    refresh_asset_computed_fields(asset)

    recent_logs = (
        Log.query.filter_by(asset_id=asset.id)
        .order_by(Log.timestamp.desc())
        .limit(40)
        .all()
    )
    users = (
        db.session.query(Log.user_id, func.count(Log.id).label("cnt"))
        .filter(Log.asset_id == asset.id, Log.user_id.isnot(None))
        .group_by(Log.user_id)
        .order_by(desc("cnt"))
        .limit(10)
        .all()
    )
    top_users = [{"user_id": int(u), "count": int(c)} for (u, c) in users if u is not None]

    trend_rows = (
        db.session.query(
            func.strftime("%Y-%m-%d %H:00:00", Log.timestamp).label("bucket"),
            func.avg(Log.risk_score).label("avg_risk"),
        )
        .filter(Log.asset_id == asset.id, Log.risk_score.isnot(None))
        .group_by("bucket")
        .order_by("bucket")
        .limit(168)
        .all()
    )
    risk_trend = [{"bucket": r.bucket, "avg_risk_score": float(r.avg_risk or 0)} for r in trend_rows]

    return {
        "asset": filter_asset_fields(asset, role),
        "recent_logs": [l.to_dict() for l in recent_logs],
        "risk_trend": risk_trend,
        "top_users": top_users,
        "generated_at": _utcnow().isoformat(),
    }

