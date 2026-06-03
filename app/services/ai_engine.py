from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import sqrt
from typing import Any

SEVERITY_WEIGHTS = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.7, "CRITICAL": 1.0}


def _to_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def _zscore(value: float, values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / len(values)
    sd = sqrt(var) if var > 1e-12 else 0.0
    return (value - mean) / sd if sd > 1e-12 else 0.0


def classify_risk_band(score: float) -> str:
    s = max(0.0, min(1.0, float(score or 0.0)))
    if s < 0.3:
        return "LOW"
    if s < 0.6:
        return "MEDIUM"
    if s < 0.8:
        return "HIGH"
    return "CRITICAL"


def compute_anomaly_score(log_or_type: dict[str, Any] | str, history_or_features: list[dict[str, Any]] | dict[str, Any] | None = None) -> float:
    """
    Backward compatible entrypoint:
    - New usage: compute_anomaly_score(log_dict, history_logs)
    - Legacy usage: compute_anomaly_score(log_type, feature_dict)
    """
    if isinstance(log_or_type, str):
        # Legacy path used by ingestion_service: heuristic from feature vector.
        feats = history_or_features if isinstance(history_or_features, dict) else {}
        vals = [float(v or 0) for v in feats.values()]
        if not vals:
            return 0.0
        mean_v = sum(vals) / len(vals)
        spike = max(vals) if vals else 0.0
        score = 0.25 * (1.0 if spike > (2.0 * max(mean_v, 1e-9)) else 0.0)
        score += min(0.75, max(0.0, (mean_v / 10.0)))
        return max(0.0, min(1.0, score))

    log = dict(log_or_type or {})
    history = history_or_features if isinstance(history_or_features, list) else []
    return _compute_anomaly_score_rule(log, history)


def _compute_anomaly_score_rule(log: dict[str, Any], history: list[dict[str, Any]]) -> float:
    score = 0.0
    metadata = log.get("metadata") or {}
    ts = _to_dt(log.get("timestamp"))
    event = str(log.get("event_type") or "").lower()
    actor = str(log.get("username") or log.get("user_id") or "unknown")
    action = str(log.get("action") or event)

    same_actor = [h for h in history if str(h.get("username") or h.get("user_id") or "unknown") == actor]
    recent_window = [h for h in same_actor if (_to_dt(h.get("timestamp")) >= ts.replace(minute=0, second=0, microsecond=0))]
    current_activity = len(recent_window) + 1
    hist_counts = []
    bucket_counts: dict[str, int] = defaultdict(int)
    for h in same_actor:
        dt = _to_dt(h.get("timestamp"))
        key = dt.strftime("%Y-%m-%d %H")
        bucket_counts[key] += 1
    if bucket_counts:
        hist_counts = list(bucket_counts.values())
        avg_activity = sum(hist_counts) / len(hist_counts)
        if current_activity > 2 * max(1.0, avg_activity):
            score += 0.4

    off_hours = bool(metadata.get("off_hours")) or (ts.hour < 6 or ts.hour > 22)
    if off_hours:
        score += 0.2

    action_hist = Counter(str(h.get("action") or h.get("event_type") or "").lower() for h in same_actor)
    if action and action_hist:
        total = sum(action_hist.values())
        freq = action_hist.get(action.lower(), 0) / max(total, 1)
        if freq < 0.05:
            score += 0.2

    if hist_counts:
        z = _zscore(float(current_activity), [float(v) for v in hist_counts])
        if z >= 1.8:
            score += 0.2

    # Domain-specific bumps.
    if "login_failure" in event or ("login" in event and str(log.get("status") or "").lower() in {"failed", "denied"}):
        score += 0.15
    if log.get("log_type") == "finance" and float(log.get("amount") or 0) >= 100000:
        score += 0.15
    if log.get("log_type") == "hr" and "export" in event and off_hours:
        score += 0.2

    return max(0.0, min(1.0, score))


def compute_risk_score(log: dict[str, Any]) -> float:
    severity_weight = SEVERITY_WEIGHTS.get(str(log.get("severity") or "LOW").upper(), 0.2)
    anomaly_score = float(log.get("anomaly_score") or 0.0)
    status_weight = 1.0 if str(log.get("status") or "").lower() in {"denied", "failed"} else 0.0
    asset_criticality = float(log.get("asset_criticality") or log.get("criticality") or 0.0)
    if asset_criticality > 1:
        asset_criticality = min(1.0, asset_criticality / 5.0)
    score = (0.4 * severity_weight) + (0.3 * anomaly_score) + (0.2 * status_weight) + (0.1 * asset_criticality)
    return max(0.0, min(1.0, score))


def calculate_risk(log: dict[str, Any]) -> float:
    # Backward alias for previous function name.
    return compute_risk_score(log)


def hotspot_detection(logs: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in logs:
        event = str(row.get("event_type") or "unknown_event")
        asset = str(row.get("asset_name") or row.get("asset_id") or "unknown-asset")
        key = (asset.lower(), event.lower())
        if key not in grouped:
            grouped[key] = {"asset_name": asset, "event_type": event, "count": 0, "avg_risk_score": 0.0}
        g = grouped[key]
        g["count"] += 1
        g["avg_risk_score"] += float(row.get("risk_score") or 0.0)
    out: list[dict[str, Any]] = []
    for g in grouped.values():
        n = max(1, int(g["count"]))
        g["avg_risk_score"] = round(float(g["avg_risk_score"]) / n, 4)
        g["risk_band"] = classify_risk_band(g["avg_risk_score"])
        g["summary"] = f"{g['event_type']} on {g['asset_name']} — {g['count']} events ({g['risk_band']})"
        out.append(g)
    out.sort(key=lambda x: (float(x.get("avg_risk_score") or 0), int(x.get("count") or 0)), reverse=True)
    return out[:limit]


def detect_hotspots(logs: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    # Alias retained for compatibility.
    return hotspot_detection(logs, limit=limit)


def generate_insights(logs: list[dict[str, Any]]) -> list[str]:
    insights: list[str] = []
    for h in hotspot_detection(logs, limit=10):
        evt = str(h.get("event_type") or "").lower()
        risk = str(h.get("risk_band") or "")
        if "login" in evt and risk in {"HIGH", "CRITICAL"}:
            insights.append(f"Repeated login failures on {h.get('asset_name')} — possible brute force")
        elif "transaction" in evt and risk in {"HIGH", "CRITICAL"}:
            insights.append("High-value finance anomalies — possible fraud")
        elif "export" in evt:
            insights.append("HR export during off-hours — insider threat")
    uniq: list[str] = []
    for x in insights:
        if x not in uniq:
            uniq.append(x)
    return uniq[:8]
