from __future__ import annotations

from flask import abort

from app.extensions import db
from app.models.asset import Asset
from app.models.feature_vector import FeatureVector
from app.models.log import Log
from app.services.ai_engine import compute_anomaly_score
from app.services.classification_service import classify_log
from app.services.feature_engineering_service import extract_features
from app.services.risk_engine import compute_risk_score
from app.utils.helpers import parse_timestamp


REQUIRED_FIELDS = ()

def _map_event_to_asset(event_type: str) -> str | None:
    event_lower = (event_type or "").lower()
    if "sql injection" in event_lower or "web" in event_lower or "login" in event_lower:
        asset = db.session.query(Asset).filter(Asset.department == "IT").first()
        if asset: return asset.id
    if "transaction" in event_lower or "payment" in event_lower or "finance" in event_lower or "transfer" in event_lower:
        asset = db.session.query(Asset).filter(Asset.department == "Finance").first()
        if asset: return asset.id
    if "salary" in event_lower or "employee" in event_lower or "hr" in event_lower:
        asset = db.session.query(Asset).filter(Asset.department == "HR").first()
        if asset: return asset.id
    return None


def _normalize_log(raw_log: dict) -> dict:
    normalized = dict(raw_log or {})

    event_type = normalized.get("event_type") or normalized.get("message") or "event"
    normalized["event_type"] = event_type
    
    if not normalized.get("asset_id"):
        mapped_asset_id = _map_event_to_asset(event_type)
        if mapped_asset_id:
            normalized["asset_id"] = mapped_asset_id
        else:
            abort(400, description="missing required field: asset_id and could not infer from event_type")

    asset = db.session.get(Asset, normalized["asset_id"])
    if not asset:
        abort(400, description=f"unknown asset_id: {normalized['asset_id']}")

    normalized["timestamp"] = parse_timestamp(normalized.get("timestamp"))
    normalized["event_type"] = normalized.get("event_type") or normalized.get("message") or "event"
    normalized["status"] = normalized.get("status") or "observed"
    normalized["metadata"] = dict(normalized.get("metadata") or {})
    return classify_log(normalized)


def process_log(raw_log: dict) -> Log:
    normalized = _normalize_log(raw_log)
    asset = db.session.get(Asset, normalized["asset_id"])

    features = extract_features(normalized)
    anomaly_score = compute_anomaly_score(normalized["log_type"], features)
    risk_score, risk_band = compute_risk_score(
        anomaly_score,
        asset.business_value,
        normalized["severity"],
    )

    log_row = Log(
        timestamp=normalized["timestamp"],
        asset_id=normalized["asset_id"],
        user_id=normalized.get("user_id"),
        event_type=normalized["event_type"],
        log_type=normalized["log_type"],
        severity=normalized["severity"],
        source_ip=normalized.get("source_ip"),
        destination_ip=normalized.get("destination_ip"),
        action=normalized.get("action"),
        status=normalized.get("status"),
        amount=normalized.get("amount"),
        metadata_json=normalized.get("metadata", {}),
        risk_level=normalized.get("risk_level"),
        anomaly_score=anomaly_score,
        risk_score=risk_score,
        risk_band=risk_band,
        is_temporary=bool(normalized.get("is_temporary", False)),
    )

    db.session.add(log_row)
    db.session.flush()

    db.session.add(
        FeatureVector(
            log_id=log_row.id,
            log_type=normalized["log_type"],
            features_json=features,
        )
    )

    return log_row  # NO COMMIT HERE
