from __future__ import annotations

from collections import Counter
from math import sqrt

from sqlalchemy import func

from app.extensions import db
from app.models.log import Log
from app.services.ceo_executive_metrics import build_executive_payload


RISK_BANDS_ORDER = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _bucketize_counts(rows: list[dict], z_threshold: float = 2.25) -> dict:
    """Detect spikes in a time series of {'bucket': str, 'count': int}."""
    counts = [float(r.get("count") or 0) for r in rows]
    if len(counts) < 6:
        return {"z_threshold": z_threshold, "spikes": [], "mean": (sum(counts) / len(counts)) if counts else 0.0}
    mean = sum(counts) / len(counts)
    var = sum((c - mean) ** 2 for c in counts) / max(len(counts), 1)
    sd = sqrt(var) if var > 1e-12 else 0.0
    spikes = []
    for r in rows:
        c = float(r.get("count") or 0)
        z = (c - mean) / sd if sd > 1e-12 else 0.0
        if z >= z_threshold and c >= 3:
            spikes.append({"bucket": r.get("bucket"), "count": int(c), "z": round(z, 2)})
    return {"z_threshold": z_threshold, "spikes": spikes, "mean": round(mean, 3), "sd": round(sd, 3)}


def _events_over_time(log_type: str) -> list[dict]:
    rows = (
        db.session.query(
            func.strftime("%Y-%m-%d %H:%M:00", Log.timestamp).label("bucket"),
            func.count(Log.id).label("count"),
        )
        .filter(Log.log_type == log_type)
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )
    return [{"bucket": row.bucket, "count": row.count} for row in rows]


def _asset_risk_trend(log_type: str, limit_assets: int = 4) -> dict:
    """
    Return per-asset risk trend by minute bucket:
    {
      "assets":[{"asset_id":..., "label":...}],
      "buckets":[...],
      "series": {"asset_id": [avg_risk,...]}  # aligned with buckets
    }
    """
    top = (
        db.session.query(Log.asset_id, func.avg(Log.risk_score).label("avg_r"))
        .filter(Log.log_type == log_type, Log.risk_score.isnot(None))
        .group_by(Log.asset_id)
        .order_by(func.avg(Log.risk_score).desc())
        .limit(limit_assets)
        .all()
    )
    asset_ids = [r.asset_id for r in top]
    if not asset_ids:
        return {"assets": [], "buckets": [], "series": {}}

    rows = (
        db.session.query(
            func.strftime("%Y-%m-%d %H:%M:00", Log.timestamp).label("bucket"),
            Log.asset_id.label("asset_id"),
            func.avg(Log.risk_score).label("avg_r"),
        )
        .filter(Log.log_type == log_type, Log.asset_id.in_(asset_ids), Log.risk_score.isnot(None))
        .group_by("bucket", "asset_id")
        .order_by("bucket")
        .all()
    )
    buckets = sorted({r.bucket for r in rows})
    series: dict[str, list[float | None]] = {aid: [None] * len(buckets) for aid in asset_ids}
    b_index = {b: i for i, b in enumerate(buckets)}
    for r in rows:
        series[str(r.asset_id)][b_index[r.bucket]] = float(r.avg_r or 0)
    return {
        "assets": [{"asset_id": aid, "label": aid} for aid in asset_ids],
        "buckets": buckets,
        "series": series,
    }


def _asset_risk_band_heatmap(log_type: str, limit_assets: int = 12) -> dict:
    """
    Heatmap counts: assets (x) vs risk_band (y).
    Output matrix[y][x].
    """
    top_assets = (
        db.session.query(Log.asset_id, func.avg(Log.risk_score).label("avg_r"))
        .filter(Log.log_type == log_type, Log.risk_score.isnot(None))
        .group_by(Log.asset_id)
        .order_by(func.avg(Log.risk_score).desc())
        .limit(limit_assets)
        .all()
    )
    asset_ids = [r.asset_id for r in top_assets]
    if not asset_ids:
        return {"assets": [], "levels": list(RISK_BANDS_ORDER), "matrix": [[0] * 0 for _ in RISK_BANDS_ORDER]}
    counts = (
        db.session.query(Log.asset_id, Log.risk_band, func.count(Log.id))
        .filter(Log.log_type == log_type, Log.asset_id.in_(asset_ids))
        .group_by(Log.asset_id, Log.risk_band)
        .all()
    )
    idx = {aid: i for i, aid in enumerate(asset_ids)}
    lev = list(RISK_BANDS_ORDER)
    lidx = {l: i for i, l in enumerate(lev)}
    matrix = [[0 for _ in asset_ids] for _ in lev]
    for aid, band, cnt in counts:
        b = (band or "UNKNOWN").upper()
        if b not in lidx:
            continue
        matrix[lidx[b]][idx[aid]] = int(cnt or 0)
    return {"assets": asset_ids, "levels": lev, "matrix": matrix}


def _finance_flow_over_time() -> list[dict]:
    """Per-minute bucket: transaction count and summed amounts (funding / flow proxy)."""
    rows = (
        db.session.query(
            func.strftime("%Y-%m-%d %H:%M:00", Log.timestamp).label("bucket"),
            func.count(Log.id).label("cnt"),
            func.coalesce(func.sum(Log.amount), 0.0).label("amt"),
        )
        .filter(Log.log_type == "finance")
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )
    return [
        {
            "bucket": row.bucket,
            "count": row.cnt,
            "amount_total": float(row.amt or 0),
        }
        for row in rows
    ]


def _finance_status_counts() -> dict[str, int]:
    logs = Log.query.filter_by(log_type="finance").all()
    success = sum(1 for log in logs if str(log.status).lower() == "success")
    failed = sum(1 for log in logs if str(log.status).lower() != "success")
    return {"success": success, "failed": failed}


def _portfolio_risk_bands() -> dict[str, int]:
    return dict(Counter((log.risk_band or "UNKNOWN") for log in Log.query.all()))


def _risk_intel_summary(logs: list[Log]) -> dict:
    bands = Counter((log.risk_band or "UNKNOWN") for log in logs)
    scores = [log.risk_score for log in logs if log.risk_score is not None]
    anoms = [log.anomaly_score for log in logs if log.anomaly_score is not None]
    return {
        "risk_by_band": dict(bands),
        "avg_risk_score": sum(scores) / len(scores) if scores else 0.0,
        "avg_anomaly_score": sum(anoms) / len(anoms) if anoms else 0.0,
    }


def _high_risk_events(logs: list[Log], limit: int = 25) -> list[dict]:
    ranked = sorted(
        [log for log in logs if log.risk_band in ("HIGH", "CRITICAL")],
        key=lambda x: x.risk_score or 0.0,
        reverse=True,
    )[:limit]
    return [log.to_dict() for log in ranked]


def summarize_intel_from_log_dicts(log_dicts: list[dict]) -> dict:
    """Aggregate anomaly / risk from serialized logs (e.g. observer recent rows)."""
    bands = Counter((d.get("risk_band") or "UNKNOWN") for d in log_dicts)
    scores = [d["risk_score"] for d in log_dicts if d.get("risk_score") is not None]
    anoms = [d["anomaly_score"] for d in log_dicts if d.get("anomaly_score") is not None]
    return {
        "risk_by_band": dict(bands),
        "avg_risk_score": sum(scores) / len(scores) if scores else 0.0,
        "avg_anomaly_score": sum(anoms) / len(anoms) if anoms else 0.0,
    }


def get_soc_dashboard() -> dict:
    logs = Log.query.filter_by(log_type="soc").all()
    severity_counts = Counter(log.severity for log in logs)
    event_counts = Counter((log.event_type or "unknown") for log in logs)
    top_assets = (
        db.session.query(
            Log.asset_id,
            func.avg(Log.risk_score).label("avg_r"),
            func.count(Log.id).label("cnt"),
        )
        .filter(Log.log_type == "soc", Log.risk_score.isnot(None))
        .group_by(Log.asset_id)
        .order_by(func.avg(Log.risk_score).desc())
        .limit(10)
        .all()
    )
    return {
        "total_events": len(logs),
        "events_by_severity": dict(severity_counts),
        "event_distribution": dict(event_counts),
        "events_over_time": _events_over_time("soc"),
        "attack_timeline": _events_over_time("soc"),
        "alert_spikes": _bucketize_counts(_events_over_time("soc")),
        "asset_risk_trend": _asset_risk_trend("soc"),
        "asset_risk_heatmap": _asset_risk_band_heatmap("soc"),
        "top_risky_assets": [
            {"asset_id": r.asset_id, "avg_risk_score": float(r.avg_r or 0), "count": int(r.cnt or 0)}
            for r in top_assets
        ],
        "intelligence": _risk_intel_summary(logs),
        "high_risk_events": _high_risk_events(logs),
    }


def get_finance_dashboard() -> dict:
    logs = Log.query.filter_by(log_type="finance").all()
    success_count = sum(1 for log in logs if str(log.status).lower() == "success")
    failed_count = sum(1 for log in logs if str(log.status).lower() != "success")
    high_value_transactions = [
        log.to_dict() for log in logs if (log.amount or 0) >= 100000
    ]
    risk_vs_amount = [
        {
            "amount": float(log.amount or 0),
            "risk_score": float(log.risk_score or 0),
            "risk_band": log.risk_band,
            "status": log.status,
        }
        for log in logs
        if log.amount is not None
    ][:300]
    flow = _finance_flow_over_time()
    top_high_value = (
        Log.query.filter(Log.log_type == "finance", Log.amount.isnot(None))
        .order_by(Log.amount.desc())
        .limit(12)
        .all()
    )
    policy_violations = sum(
        1 for log in logs if str(log.status or "").lower() in {"unauthorized"} or (log.metadata_json or {}).get("flagged")
    )
    insider_indicators = sum(
        1 for log in logs if (log.anomaly_score or 0) >= 0.78 and (log.risk_band in ("HIGH", "CRITICAL"))
    )
    exposure_total = sum(float(log.amount or 0) * float(log.risk_score or 0) for log in logs if log.amount is not None and log.risk_score is not None)
    exposure_trend_rows = (
        db.session.query(
            func.strftime("%Y-%m-%d %H:%M:00", Log.timestamp).label("bucket"),
            func.coalesce(func.sum(Log.amount * Log.risk_score), 0.0).label("exposure"),
        )
        .filter(Log.log_type == "finance", Log.amount.isnot(None), Log.risk_score.isnot(None))
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )
    exposure_trend = [{"bucket": r.bucket, "exposure": float(r.exposure or 0)} for r in exposure_trend_rows]
    return {
        "total_transactions": len(logs),
        "success_vs_failed": {"success": success_count, "failed": failed_count},
        "high_value_transactions": high_value_transactions,
        "transaction_volume_trend": flow,
        "top_high_value": [l.to_dict() for l in top_high_value],
        "access_violations": {"policy_violations": int(policy_violations), "insider_indicators": int(insider_indicators)},
        "financial_risk_exposure": {
            "total_exposure": round(float(exposure_total), 2),
            "trend": exposure_trend[-240:],
        },
        "risk_vs_amount": risk_vs_amount,
        "intelligence": _risk_intel_summary(logs),
        "high_risk_events": _high_risk_events(logs),
    }


def get_hr_dashboard() -> dict:
    logs = Log.query.filter_by(log_type="hr").all()
    action_counts = Counter((log.action or "unknown") for log in logs)
    off_hours = sum(1 for log in logs if log.metadata_json.get("off_hours"))
    top_users = (
        db.session.query(Log.user_id, func.count(Log.id).label("cnt"))
        .filter(Log.log_type == "hr", Log.user_id.isnot(None))
        .group_by(Log.user_id)
        .order_by(func.count(Log.id).desc())
        .limit(10)
        .all()
    )
    sensitive_alerts = []
    for log in logs:
        meta = log.metadata_json or {}
        if "salary" in str(meta.get("data_type", "")).lower() or "export" in str(log.action or "").lower():
            if log.risk_band in ("HIGH", "CRITICAL"):
                sensitive_alerts.append(log.to_dict())
    # Time series
    activity_trend = _events_over_time("hr")
    # action_context distribution + over time
    ctx_dist = Counter(str((log.metadata_json or {}).get("action_context") or "unknown") for log in logs)
    # Note: use python-side extraction for ctx series (SQLite JSON support varies).
    # We already have serialized logs in memory, so keep this lightweight.
    ctx_rows = []
    for log in logs:
        bucket = log.timestamp.strftime("%Y-%m-%d %H:%M:00")
        ctx = str((log.metadata_json or {}).get("action_context") or "unknown")
        ctx_rows.append({"bucket": bucket, "ctx": ctx})
    ctx_counter = Counter((r["bucket"], r["ctx"]) for r in ctx_rows)
    ctx_buckets = sorted({r["bucket"] for r in ctx_rows})
    ctx_keys = sorted({r["ctx"] for r in ctx_rows})
    ctx_series: dict[str, list[int]] = {k: [0] * len(ctx_buckets) for k in ctx_keys}
    b_index = {b: i for i, b in enumerate(ctx_buckets)}
    for (bucket, ctx), cnt in ctx_counter.items():
        ctx_series[ctx][b_index[bucket]] = int(cnt or 0)
    denied_n = sum(1 for log in logs if str(log.status or "").lower() in {"denied", "failed"})
    suspicious_n = sum(1 for log in logs if (log.anomaly_score or 0) >= 0.78 or (log.metadata_json or {}).get("off_hours"))
    data_types = Counter(str((log.metadata_json or {}).get("data_type") or "unknown") for log in logs)
    return {
        "activity_count": len(logs),
        "action_types": dict(action_counts),
        "off_hour_activity": off_hours,
        "user_activity_trend": activity_trend,
        "activity_type_distribution": dict(ctx_dist),
        "activity_type_over_time": {"buckets": ctx_buckets, "series": ctx_series},
        "top_users": [{"user_id": int(u), "count": int(c)} for (u, c) in top_users if u is not None],
        "off_hours_compare": {"off_hours": int(off_hours), "normal_hours": int(max(len(logs) - off_hours, 0))},
        "violations_access": {"denied_or_failed": int(denied_n), "suspicious": int(suspicious_n)},
        "sensitive_data_access": dict(data_types),
        "sensitive_data_alerts": sensitive_alerts[:20],
        "intelligence": _risk_intel_summary(logs),
        "high_risk_events": _high_risk_events(logs),
    }


def get_ceo_dashboard() -> dict:
    recent = Log.query.order_by(Log.timestamp.desc()).limit(100).all()
    finance_logs = Log.query.filter_by(log_type="finance").all()
    fin_amounts = [float(log.amount or 0) for log in finance_logs if log.amount is not None]
    volume_sum = sum(fin_amounts)
    soc_n = Log.query.filter_by(log_type="soc").count()
    fin_n = Log.query.filter_by(log_type="finance").count()
    hr_n = Log.query.filter_by(log_type="hr").count()
    return {
        "summary": {
            "soc_events": soc_n,
            "finance_events": fin_n,
            "hr_events": hr_n,
        },
        "intelligence": _risk_intel_summary(recent),
        "high_risk_events": _high_risk_events(recent, 20),
        "ceo_charts": {
            "finance_flow_over_time": _finance_flow_over_time(),
            "finance_success_vs_failed": _finance_status_counts(),
            "domain_event_mix": {
                "labels": ["SOC", "Finance", "HR"],
                "values": [soc_n, fin_n, hr_n],
            },
            "risk_bands_portfolio": _portfolio_risk_bands(),
            "finance_totals": {
                "transaction_count": fin_n,
                "volume_sum": volume_sum,
                "avg_transaction": (volume_sum / len(fin_amounts)) if fin_amounts else 0.0,
                "high_value_count": sum(1 for log in finance_logs if (log.amount or 0) >= 100000),
            },
        },
        "executive": build_executive_payload(),
    }
