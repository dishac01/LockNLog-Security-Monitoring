from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, or_

from app.models.log import Log

FEATURE_LOOKBACK_MINUTES = 60
HIGH_VALUE_AMOUNT = 100_000.0


def _window_start(ts):
    return ts - timedelta(minutes=FEATURE_LOOKBACK_MINUTES)


def _failed_status_condition():
    return or_(
        func.lower(Log.status) == "failed",
        func.lower(Log.status) == "denied",
    )


def extract_features(normalized: dict) -> dict:
    """
    Build domain-specific behavioral features from recent logs (strictly before this event).
    """
    log_type = (normalized.get("log_type") or "soc").lower()
    ts = normalized["timestamp"]
    asset_id = normalized["asset_id"]
    user_id = normalized.get("user_id")
    ws = _window_start(ts)

    base_t = [Log.timestamp >= ws, Log.timestamp < ts]

    if log_type == "soc":
        return _soc_features(base_t, asset_id)
    if log_type == "finance":
        return _finance_features(base_t, user_id, asset_id)
    if log_type == "hr":
        return _hr_features(base_t, user_id, asset_id)
    return _soc_features(base_t, asset_id)


def _soc_features(base_t, asset_id: str) -> dict:
    q = Log.query.filter(
        *base_t,
        Log.log_type == "soc",
        Log.asset_id == asset_id,
    )
    total = q.count()
    failed = q.filter(_failed_status_condition()).count()
    window_minutes = float(FEATURE_LOOKBACK_MINUTES)
    request_frequency = float(total) / max(window_minutes, 1.0)
    return {
        "failed_login_count": float(failed),
        "request_frequency": request_frequency,
    }


def _finance_features(base_t, user_id: int | None, asset_id: str) -> dict:
    fq = Log.query.filter(
        *base_t,
        Log.log_type == "finance",
    )
    if user_id is not None:
        fq = fq.filter(Log.user_id == user_id)
    else:
        fq = fq.filter(Log.asset_id == asset_id)

    rows = fq.with_entities(Log.amount).all()
    amounts = [float(r[0] or 0) for r in rows if r[0] is not None]
    n = len(amounts)
    if n == 0:
        return {"avg_transaction_amount": 0.0, "high_value_ratio": 0.0}
    avg_amt = sum(amounts) / n
    hv = sum(1 for a in amounts if a >= HIGH_VALUE_AMOUNT)
    return {
        "avg_transaction_amount": avg_amt,
        "high_value_ratio": float(hv) / float(n),
    }


def _hr_features(base_t, user_id: int | None, asset_id: str) -> dict:
    hq = Log.query.filter(
        *base_t,
        Log.log_type == "hr",
    )
    if user_id is not None:
        hq = hq.filter(Log.user_id == user_id)
    else:
        hq = hq.filter(Log.asset_id == asset_id)

    logs = hq.all()
    off_hours = sum(
        1
        for log in logs
        if (log.metadata_json or {}).get("off_hours") in (True, "true", 1, "1")
    )
    return {
        "off_hours_activity_count": float(off_hours),
        "resource_access_count": float(len(logs)),
    }
