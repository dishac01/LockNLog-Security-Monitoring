"""
CEO executive dashboard: KPIs, trends, compliance heuristics, department analytics.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, desc, func

from app.extensions import db
from app.models.asset import Asset
from app.models.log import Log


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _risk_band_from_score(score: float) -> str:
    if score < 0.25:
        return "Low"
    if score < 0.5:
        return "Medium"
    if score < 0.75:
        return "High"
    return "Critical"


def _avg_risk_between(start: datetime, end: datetime) -> float | None:
    q = (
        Log.query.filter(Log.timestamp >= start, Log.timestamp < end)
        .filter(Log.risk_score.isnot(None))
        .with_entities(Log.risk_score)
    )
    rows = q.all()
    if not rows:
        return None
    return sum(float(r[0]) for r in rows) / len(rows)


def _overall_kpi() -> dict[str, Any]:
    now = _utcnow()
    w7 = now - timedelta(days=7)
    w14 = now - timedelta(days=14)
    recent = _avg_risk_between(w7, now)
    prior = _avg_risk_between(w14, w7)
    all_scores = Log.query.filter(Log.risk_score.isnot(None)).with_entities(Log.risk_score).all()
    portfolio_avg = sum(float(s[0]) for s in all_scores) / len(all_scores) if all_scores else 0.0
    score = portfolio_avg
    change_pct = None
    if recent is not None and prior is not None and prior > 1e-9:
        change_pct = round((recent - prior) / prior * 100.0, 1)
    elif recent is not None and prior is not None and prior <= 1e-9 and recent > 0:
        change_pct = 100.0
    return {
        "score": round(score, 3),
        "severity": _risk_band_from_score(score),
        "change_percent": change_pct,
        "window_note": "Portfolio avg risk_score; change vs prior 7-day window.",
    }


def _financial_exposure_trend(days: int = 14) -> dict[str, Any]:
    now = _utcnow()
    start = now - timedelta(days=days)
    rows = (
        db.session.query(
            func.date(Log.timestamp).label("d"),
            func.coalesce(func.sum(Log.amount), 0.0).label("vol"),
            func.sum(case((Log.risk_band.in_(["HIGH", "CRITICAL"]), 1), else_=0)).label("hrisk_n"),
        )
        .filter(Log.log_type == "finance", Log.timestamp >= start)
        .group_by("d")
        .order_by("d")
        .all()
    )
    trend = [{"date": str(r.d), "volume": float(r.vol or 0), "high_risk_events": int(r.hrisk_n or 0)} for r in rows]
    fin_logs = Log.query.filter_by(log_type="finance").all()
    high_risk_fin = [log for log in fin_logs if log.risk_band in ("HIGH", "CRITICAL")]
    failed_fin = [log for log in fin_logs if str(log.status).lower() != "success"]
    est_impact = sum(float(log.amount or 0) for log in high_risk_fin)
    est_impact += sum(float(log.amount or 0) * 0.15 for log in failed_fin)
    return {
        "estimated_impact": round(est_impact, 2),
        "estimated_impact_note": "Sum of HIGH/CRITICAL finance amounts + 15% weight on non-success amounts (heuristic).",
        "trend": trend,
    }


def _department_risk_comparison() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lt, label in (("soc", "IT (SOC)"), ("finance", "Finance"), ("hr", "HR")):
        q = Log.query.filter_by(log_type=lt).filter(Log.risk_score.isnot(None)).with_entities(Log.risk_score)
        rows = q.all()
        if not rows:
            out.append(
                {
                    "department": label,
                    "log_type": lt,
                    "avg_risk_score": 0.0,
                    "log_count": Log.query.filter_by(log_type=lt).count(),
                    "critical_count": Log.query.filter_by(log_type=lt, risk_band="CRITICAL").count(),
                }
            )
            continue
        vals = [float(r[0]) for r in rows]
        out.append(
            {
                "department": label,
                "log_type": lt,
                "avg_risk_score": round(sum(vals) / len(vals), 4),
                "log_count": len(vals),
                "critical_count": Log.query.filter_by(log_type=lt, risk_band="CRITICAL").count(),
            }
        )
    return out


def _risk_trend_daily(days: int = 21) -> list[dict[str, Any]]:
    now = _utcnow()
    start = now - timedelta(days=days)
    rows = (
        db.session.query(
            func.date(Log.timestamp).label("d"),
            func.avg(Log.risk_score).label("avg_r"),
            func.sum(case((Log.risk_band == "CRITICAL", 1), else_=0)).label("crit"),
        )
        .filter(Log.timestamp >= start, Log.risk_score.isnot(None))
        .group_by("d")
        .order_by("d")
        .all()
    )
    return [
        {
            "date": str(r.d),
            "avg_risk_score": round(float(r.avg_r or 0), 4),
            "critical_count": int(r.crit or 0),
        }
        for r in rows
    ]


def _top_risky_assets(limit: int = 12) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            Log.asset_id,
            func.avg(Log.risk_score).label("avg_r"),
            func.count(Log.id).label("cnt"),
            func.sum(case((Log.risk_band == "CRITICAL", 1), else_=0)).label("crit_c"),
        )
        .filter(Log.risk_score.isnot(None))
        .group_by(Log.asset_id)
        .order_by(desc("avg_r"))
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        aid = r.asset_id
        asset = db.session.get(Asset, aid)
        logs = Log.query.filter_by(asset_id=aid).all()
        avg_anomaly = 0.0
        total_anomalies = 0
        if logs:
            vals = [float(l.anomaly_score or 0) for l in logs if l.anomaly_score is not None]
            avg_anomaly = (sum(vals) / len(vals)) if vals else 0.0
            total_anomalies = sum(1 for l in logs if (l.anomaly_score or 0) >= 0.7)
        avg_risk = float(r.avg_r or 0)
        crit_count = int(r.crit_c or 0)
        # Composite prioritization score for executive ranking.
        exec_score = (avg_risk * 0.6) + (avg_anomaly * 0.25) + (min(1.0, crit_count / 10.0) * 0.15)
        out.append(
            {
                "asset_id": aid,
                "asset_name": asset.name if asset else aid,
                "department": asset.department if asset else None,
                "avg_risk_score": round(avg_risk, 4),
                "avg_anomaly_score": round(avg_anomaly, 4),
                "total_anomalies": int(total_anomalies),
                "log_count": int(r.cnt or 0),
                "critical_count": crit_count,
                "risk_level": _risk_band_from_score(avg_risk),
                "executive_priority_score": round(exec_score, 4),
            }
        )
    out.sort(key=lambda x: (x.get("avg_risk_score") or 0, x.get("critical_count") or 0), reverse=True)
    return out[:limit]


def _top_risky_users(limit: int = 12) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            Log.user_id,
            func.avg(Log.risk_score).label("avg_r"),
            func.count(Log.id).label("cnt"),
            func.sum(case((Log.risk_band == "CRITICAL", 1), else_=0)).label("crit_c"),
        )
        .filter(Log.user_id.isnot(None), Log.risk_score.isnot(None))
        .group_by(Log.user_id)
        .order_by(desc("avg_r"))
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        logs = Log.query.filter_by(user_id=int(r.user_id)).all()
        vals = [float(l.anomaly_score or 0) for l in logs if l.anomaly_score is not None]
        avg_anomaly = (sum(vals) / len(vals)) if vals else 0.0
        out.append(
            {
                "user_id": int(r.user_id),
                "avg_risk_score": round(float(r.avg_r or 0), 4),
                "avg_anomaly_score": round(avg_anomaly, 4),
                "event_count": int(r.cnt or 0),
                "critical_count": int(r.crit_c or 0),
                "risk_level": _risk_band_from_score(float(r.avg_r or 0)),
            }
        )
    return out


def _anomaly_hotspots(limit: int = 10) -> list[dict[str, Any]]:
    rows = Log.query.filter(Log.anomaly_score.isnot(None)).all()
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for l in rows:
        evt = (l.event_type or "unknown event").strip()
        asset_name = (l.asset.name if l.asset else l.asset_id) or "unknown-asset"
        key = (evt.lower(), str(asset_name).lower())
        if key not in grouped:
            grouped[key] = {
                "event_type": evt,
                "asset_name": str(asset_name),
                "asset_id": l.asset_id,
                "log_type": l.log_type,
                "count": 0,
                "max_anomaly_score": 0.0,
                "avg_anomaly_score": 0.0,
                "max_risk_score": 0.0,
                "avg_risk_score": 0.0,
                "risk_band": "LOW",
                "latest_timestamp": None,
            }
        g = grouped[key]
        g["count"] += 1
        an = float(l.anomaly_score or 0)
        rs = float(l.risk_score or 0)
        g["max_anomaly_score"] = max(float(g["max_anomaly_score"]), an)
        g["max_risk_score"] = max(float(g["max_risk_score"]), rs)
        g["avg_anomaly_score"] += an
        g["avg_risk_score"] += rs
        ts = l.timestamp.isoformat() if l.timestamp else None
        if ts and ((g["latest_timestamp"] is None) or ts > g["latest_timestamp"]):
            g["latest_timestamp"] = ts
        rb = (l.risk_band or "").upper()
        order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        if order.get(rb, 0) >= order.get(str(g["risk_band"]).upper(), 0):
            g["risk_band"] = rb or g["risk_band"]
    out: list[dict[str, Any]] = []
    for g in grouped.values():
        n = max(1, int(g["count"]))
        g["avg_anomaly_score"] = round(float(g["avg_anomaly_score"]) / n, 4)
        g["avg_risk_score"] = round(float(g["avg_risk_score"]) / n, 4)
        g["summary"] = (
            f"{g['event_type']} on {g['asset_name']} — {g['count']} events "
            f"({g['risk_band'] or _risk_band_from_score(g['avg_risk_score'])})"
        )
        out.append(g)
    out.sort(key=lambda x: (float(x.get("avg_risk_score") or 0), int(x.get("count") or 0)), reverse=True)
    return out[:limit]


def _critical_alerts_feed(limit: int = 15) -> list[dict[str, Any]]:
    rows = Log.query.filter(Log.risk_band == "CRITICAL").order_by(desc(Log.timestamp)).all()
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for l in rows:
        evt = (l.event_type or "critical_event").strip()
        asset_name = (l.asset.name if l.asset else l.asset_id) or "unknown-asset"
        key = (evt.lower(), str(asset_name).lower())
        if key not in grouped:
            grouped[key] = {
                "event_type": evt,
                "asset_name": str(asset_name),
                "asset_id": l.asset_id,
                "log_type": l.log_type,
                "count": 0,
                "latest_timestamp": None,
                "max_risk_score": 0.0,
                "max_anomaly_score": 0.0,
                "risk_band": "CRITICAL",
            }
        g = grouped[key]
        g["count"] += 1
        g["max_risk_score"] = max(float(g["max_risk_score"]), float(l.risk_score or 0))
        g["max_anomaly_score"] = max(float(g["max_anomaly_score"]), float(l.anomaly_score or 0))
        ts = l.timestamp.isoformat() if l.timestamp else None
        if ts and ((g["latest_timestamp"] is None) or ts > g["latest_timestamp"]):
            g["latest_timestamp"] = ts
    out = list(grouped.values())
    out.sort(key=lambda x: (x.get("latest_timestamp") or "", int(x.get("count") or 0)), reverse=True)
    return out[:limit]


def _risk_heatmap_asset_vs_department(limit_assets: int = 12) -> dict[str, Any]:
    """
    Provide a CEO-friendly heatmap dataset: asset (x) vs department (y), value = avg_risk_score.
    Rendered as a matrix/scatter in Chart.js.
    """
    top_assets = _top_risky_assets(limit_assets)
    assets = [a.get("asset_name") or a.get("asset_id") for a in top_assets]
    asset_ids = [a.get("asset_id") for a in top_assets if a.get("asset_id")]
    depts = ["SOC", "Finance", "HR"]
    dept_to_log = {"SOC": "soc", "Finance": "finance", "HR": "hr"}
    rows = (
        db.session.query(
            Log.asset_id,
            Log.log_type,
            func.avg(Log.risk_score).label("avg_risk"),
            func.count(Log.id).label("event_count"),
        )
        .filter(Log.asset_id.in_(asset_ids), Log.risk_score.isnot(None))
        .group_by(Log.asset_id, Log.log_type)
        .all()
    )
    lookup: dict[tuple[str, str], tuple[float, int]] = {}
    for r in rows:
        lookup[(str(r.asset_id), str(r.log_type))] = (float(r.avg_risk or 0), int(r.event_count or 0))
    points: list[dict[str, Any]] = []
    matrix: list[list[float]] = []
    event_matrix: list[list[int]] = []
    for dep in depts:
        dep_row: list[float] = []
        dep_events: list[int] = []
        for a in top_assets:
            aid = str(a.get("asset_id") or "")
            avg_r, ev_n = lookup.get((aid, dept_to_log[dep]), (0.0, 0))
            dep_row.append(round(avg_r, 4))
            dep_events.append(ev_n)
            points.append(
                {
                    "asset": a.get("asset_name") or a.get("asset_id"),
                    "department": dep,
                    "avg_risk_score": round(avg_r, 4),
                    "event_count": ev_n,
                    "risk_band": _risk_band_from_score(avg_r),
                }
            )
        matrix.append(dep_row)
        event_matrix.append(dep_events)
    return {"departments": depts, "assets": assets, "matrix": matrix, "event_matrix": event_matrix, "points": points}


def _decision_hints(executive_payload: dict[str, Any]) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    hotspots = executive_payload.get("anomaly_hotspots") or []
    top_assets = executive_payload.get("top_risky_assets") or []
    critical = executive_payload.get("critical_alerts_feed") or []
    top_users = executive_payload.get("top_risky_users") or []
    if hotspots:
        h = hotspots[0]
        hints.append(
            {
                "widget": "anomaly_hotspots",
                "hint": f"{h.get('event_type', 'Anomalous activity')} on {h.get('asset_name', 'asset')} appears repeatedly — investigate root cause and suppress noisy signatures.",
            }
        )
    if top_assets:
        a = top_assets[0]
        hints.append(
            {
                "widget": "top_risky_assets",
                "hint": f"{a.get('asset_name', 'Top asset')} sits at {a.get('risk_level', 'elevated')} risk with score {a.get('avg_risk_score', 0)} — assign immediate owner and remediation checkpoint.",
            }
        )
    if critical:
        c = critical[0]
        hints.append(
            {
                "widget": "critical_alerts_feed",
                "hint": f"Latest CRITICAL cluster is {c.get('event_type', 'event')} on {c.get('asset_name', 'asset')} — triage this stream first.",
            }
        )
    if top_users:
        u = top_users[0]
        hints.append(
            {
                "widget": "top_risky_users",
                "hint": f"User {u.get('user_id')} has the highest average risk ({u.get('avg_risk_score', 0)}) — review account behavior and access scope.",
            }
        )
    return hints[:8]


def _top_priority(executive_payload: dict[str, Any]) -> dict[str, Any]:
    top_asset = (executive_payload.get("top_risky_assets") or [None])[0]
    top_hotspot = (executive_payload.get("anomaly_hotspots") or [None])[0]
    top_log = Log.query.filter(Log.risk_score.isnot(None)).order_by(Log.risk_score.desc(), Log.timestamp.desc()).first()
    top_log_score = float(top_log.risk_score or 0) if top_log else 0.0
    top_asset_score = float(top_asset.get("avg_risk_score") or 0) if top_asset else 0.0
    if top_log and (top_log_score >= top_asset_score):
        asset_name = top_log.asset.name if top_log.asset else (top_log.asset_id or "unknown-asset")
        return {
            "type": "log",
            "title": str(asset_name),
            "issue": top_log.event_type or "high risk event",
            "risk_band": top_log.risk_level or _risk_band_from_score(top_log_score),
            "risk_score": round(top_log_score, 4),
            "reason": "Highest risk score event in current telemetry.",
        }
    if top_asset:
        return {
            "type": "asset",
            "title": top_asset.get("asset_name"),
            "issue": (top_hotspot or {}).get("event_type") or "elevated multi-event risk",
            "risk_band": top_asset.get("risk_level"),
            "risk_score": round(top_asset_score, 4),
            "reason": "Highest average risk asset in current telemetry.",
        }
    if top_hotspot:
        return {
            "type": "event_hotspot",
            "title": f"{top_hotspot.get('event_type')} on {top_hotspot.get('asset_name')}",
            "issue": top_hotspot.get("event_type") or "hotspot",
            "risk_band": top_hotspot.get("risk_band") or "CRITICAL",
            "risk_score": round(float(top_hotspot.get("avg_risk_score") or 0), 4),
            "reason": f"Most concentrated anomaly hotspot with {top_hotspot.get('count', 0)} events.",
        }
    return {"type": "none", "title": "No priority item", "issue": "-", "risk_band": "LOW", "risk_score": 0.0, "reason": "No high-risk telemetry found in this window."}


def _insider_risk_alerts() -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    hr_logs = Log.query.filter_by(log_type="hr").all()
    def _off_hours(meta: dict) -> bool:
        v = (meta or {}).get("off_hours")
        return v in (True, "true", 1, "1")

    off_exports = sum(
        1
        for log in hr_logs
        if _off_hours(log.metadata_json) and "export" in (log.action or "").lower()
    )
    if off_exports:
        alerts.append(
            {
                "severity": "high",
                "title": "Off-hours HR exports",
                "detail": f"{off_exports} export-related HR events occurred outside business hours.",
                "category": "insider",
            }
        )
    hr_denied = sum(1 for log in hr_logs if str(log.status).lower() == "denied" and log.risk_band in ("HIGH", "CRITICAL"))
    if hr_denied >= 3:
        alerts.append(
            {
                "severity": "medium",
                "title": "Elevated denied HR actions",
                "detail": f"{hr_denied} high/critical HR events with denied status — review access patterns.",
                "category": "insider",
            }
        )
    fin = Log.query.filter_by(log_type="finance").all()
    large_failed = [log for log in fin if str(log.status).lower() != "success" and (log.amount or 0) >= 50000]
    if len(large_failed) >= 2:
        alerts.append(
            {
                "severity": "high",
                "title": "Large failed treasury movements",
                "detail": f"{len(large_failed)} failed finance events at or above 50k — possible fraud or operational stress.",
                "category": "finance",
            }
        )
    soc = Log.query.filter_by(log_type="soc").all()
    bf = sum(1 for log in soc if (log.metadata_json or {}).get("attack_type"))
    if bf >= 5:
        alerts.append(
            {
                "severity": "medium",
                "title": "Credential attack telemetry",
                "detail": f"{bf} SOC events tagged with attack_type (e.g. bruteforce) — confirm MFA coverage.",
                "category": "external",
            }
        )
    return alerts


def _compliance_status() -> dict[str, Any]:
    total = Log.query.count()
    if total == 0:
        return {"level": "Partial", "score": 50, "reasons": ["No telemetry ingested yet."]}
    bands = defaultdict(int)
    for log in Log.query.all():
        bands[log.risk_band or "UNKNOWN"] += 1
    crit = bands.get("CRITICAL", 0)
    high = bands.get("HIGH", 0)
    unk = bands.get("UNKNOWN", 0)
    crit_pct = crit / total * 100
    high_crit_pct = (crit + high) / total * 100
    unk_pct = unk / total * 100
    reasons: list[str] = []
    level = "Compliant"
    score = 92
    if crit_pct > 8 or crit > 25:
        level = "Non-compliant"
        score = 38
        reasons.append(f"CRITICAL share {crit_pct:.1f}% exceeds policy threshold.")
    elif high_crit_pct > 35 or unk_pct > 30:
        level = "Partial"
        score = 68
        reasons.append("HIGH/CRITICAL or UNKNOWN bands are elevated; remediation tracking required.")
    else:
        reasons.append("Portfolio bands within executive tolerance (heuristic).")
    return {"level": level, "score": score, "reasons": reasons, "band_counts": dict(bands)}


def _risk_category_matrix() -> list[dict[str, Any]]:
    counts = defaultdict(int)
    for log in Log.query.all():
        counts[log.risk_band or "UNKNOWN"] += 1
    definitions = [
        {
            "band": "LOW",
            "business_impact": "Routine operations; limited customer or financial exposure.",
            "owner": "Department managers",
        },
        {
            "band": "MEDIUM",
            "business_impact": "Elevated noise or control gaps; monitor for drift into HIGH.",
            "owner": "SOC / IT GRC",
        },
        {
            "band": "HIGH",
            "business_impact": "Material exposure — customer trust, liquidity, or data at stake.",
            "owner": "CISO + CFO + CHRO (domain-specific)",
        },
        {
            "band": "CRITICAL",
            "business_impact": "Severe or imminent harm; executive war-room and regulator paths possible.",
            "owner": "Executive committee + legal",
        },
    ]
    for row in definitions:
        row["log_count"] = counts.get(row["band"], 0)
    return definitions


def _department_recommendations(dept_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    for row in dept_rows:
        avg = row.get("avg_risk_score") or 0.0
        dept = row.get("department") or ""
        lt = row.get("log_type") or ""
        if avg >= 0.62:
            pri = "P1"
            issues = ["Average risk score for this stream is in the upper band."]
            actions = [
                "Assign an executive owner for a 48h remediation checkpoint.",
                "Tighten detective controls and validate access baselines.",
            ]
        elif avg >= 0.48:
            pri = "P2"
            issues = ["Risk concentration trending above comfort zone."]
            actions = ["Weekly steering with domain lead until avg_risk drops for 2 consecutive weeks."]
        else:
            pri = "P3"
            issues = ["Within normal operating variance for this snapshot."]
            actions = ["Maintain monitoring; revisit after major releases or vendor changes."]
        if lt == "finance":
            actions.append("Treasury: reconcile failed high-value attempts with SOC identity signals.")
        if lt == "hr":
            actions.append("HR: review bulk exports and privileged role assignments.")
        if lt == "soc":
            actions.append("SOC: validate edge rules and MFA enrollment for internet-facing tiers.")
        recs.append(
            {
                "department": dept,
                "log_type": lt,
                "priority": pri,
                "identified_issues": issues,
                "actions": actions,
            }
        )
    return recs


def _future_scope() -> dict[str, Any]:
    return {
        "title": "Future scope — prediction & forecasting",
        "items": [
            "Time-series forecasting (ARIMA / Prophet) on daily avg_risk_score and finance volume.",
            "Graph-based lateral movement models combining SOC + HR signals.",
            "Federated learning across business units with privacy-preserving aggregates.",
            "Scenario simulators for liquidity and insider-threat tabletop exercises.",
        ],
    }


def _positive_signals(
    department_rows: list[dict[str, Any]],
    risk_trend_daily: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Balanced, data-backed positives for the CEO overview — same telemetry as risk views.
    """
    total = Log.query.count()
    if total == 0:
        return {
            "headline": "Ingest telemetry to unlock momentum and risk views.",
            "telemetry_total": 0,
            "summary_lines": [],
        }

    band_rows = db.session.query(Log.risk_band, func.count(Log.id)).group_by(Log.risk_band).all()
    band_map: dict[str, int] = {}
    for band, cnt in band_rows:
        key = band or "UNKNOWN"
        band_map[key] = int(cnt)

    low_m = band_map.get("LOW", 0) + band_map.get("MEDIUM", 0)
    low_medium_pct = round(low_m / total * 100, 1)
    non_critical = total - band_map.get("CRITICAL", 0)
    non_critical_pct = round(non_critical / total * 100, 1)

    fin_total = Log.query.filter_by(log_type="finance").count()
    fin_succ = Log.query.filter(
        Log.log_type == "finance",
        func.lower(func.coalesce(Log.status, "")) == "success",
    ).count()
    finance_success_pct = round(fin_succ / fin_total * 100, 1) if fin_total > 0 else None

    n_assets = int(db.session.query(func.count(func.distinct(Log.asset_id))).scalar() or 0)

    on_track_depts = sum(
        1
        for d in department_rows
        if d.get("avg_risk_score") is not None and float(d["avg_risk_score"]) < 0.48
    )
    dept_n = max(len(department_rows), 1)

    recent_trend = risk_trend_daily[-7:] if len(risk_trend_daily) >= 7 else risk_trend_daily
    calm_days = sum(1 for r in recent_trend if int(r.get("critical_count") or 0) == 0)

    headline = (
        f"{low_medium_pct}% of events are LOW/MEDIUM band — most volume is routine or moderated. "
        "Controls and monitoring remain active across the estate."
    )

    lines: list[str] = [
        f"{non_critical_pct}% of events sit below CRITICAL — worst-case severity is the exception, not the norm.",
        f"Full-stack visibility: {n_assets:,} assets linked across {total:,} correlated events.",
    ]
    if fin_total > 0 and finance_success_pct is not None:
        lines.append(
            f"{fin_succ:,} treasury-class events settled successfully ({finance_success_pct}% success rate).",
        )
    if on_track_depts > 0:
        lines.append(
            f"{on_track_depts} of {dept_n} department streams sit below elevated average-risk thresholds.",
        )
    if recent_trend:
        lines.append(
            f"Daily rollup (last {len(recent_trend)} days): {calm_days} day(s) with no CRITICAL spike in count.",
        )

    return {
        "headline": headline,
        "telemetry_total": total,
        "low_medium_share_pct": low_medium_pct,
        "non_critical_share_pct": non_critical_pct,
        "distinct_assets": n_assets,
        "finance_success_count": fin_succ,
        "finance_total": fin_total,
        "finance_success_pct": finance_success_pct,
        "department_streams_on_track": on_track_depts,
        "department_streams_total": dept_n,
        "recent_calm_days": calm_days,
        "recent_days_window": len(recent_trend),
        "summary_lines": lines[:6],
    }


def build_executive_payload() -> dict[str, Any]:
    dept = _department_risk_comparison()
    rt = _risk_trend_daily()
    payload = {
        "overall_kpi": _overall_kpi(),
        "financial_exposure": _financial_exposure_trend(),
        "department_risk": dept,
        "risk_trend_daily": rt,
        "top_risky_assets": _top_risky_assets(),
        "top_risky_users": _top_risky_users(),
        "risk_heatmap": _risk_heatmap_asset_vs_department(),
        "anomaly_hotspots": _anomaly_hotspots(),
        "critical_alerts_feed": _critical_alerts_feed(),
        "insider_alerts": _insider_risk_alerts(),
        "compliance": _compliance_status(),
        "risk_category_matrix": _risk_category_matrix(),
        "department_recommendations": _department_recommendations(dept),
        "future_scope": _future_scope(),
        "positive_signals": _positive_signals(dept, rt),
    }
    payload["decision_hints"] = _decision_hints(payload)
    payload["top_priority"] = _top_priority(payload)
    return payload
