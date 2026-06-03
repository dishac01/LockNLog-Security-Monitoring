from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from app.extensions import db
from app.models.log import Log
from app.models.user import User
from app.services.access_control_service import filter_logs_for_session, filter_logs_by_role
from app.services.ingestion_service import process_log
from app.services.mock_data_service import seed_base_data, generate_soc_logs, generate_finance_logs, generate_hr_logs
from app.utils.decorators import login_required
import random

ingestion_bp = Blueprint("ingestion", __name__, url_prefix="/api/v1")


@ingestion_bp.post("/inject_log")
def inject_log():
    """Accept a local log payload and store it through the ingestion pipeline."""
    payload = request.get_json(silent=True) or {}
    log_row = process_log(payload)
    db.session.commit()
    return jsonify({"log": log_row.to_dict()}), 201


@ingestion_bp.post("/inject")
@login_required
def inject_logs():
    """Inject 40-50 temporary logs."""
    num_logs = random.randint(40, 50)
    
    logs_to_process = []
    while len(logs_to_process) < num_logs:
        generators = [generate_soc_logs, generate_finance_logs, generate_hr_logs]
        chosen = random.choice(generators)
        # Generate 1 to 5 logs at a time
        batch = chosen(count=random.randint(1, 5))
        logs_to_process.extend(batch)
    
    logs_to_process = logs_to_process[:num_logs]
    
    injected = []
    for raw_log in logs_to_process:
        raw_log["is_temporary"] = True
        log_row = process_log(raw_log)
        injected.append(log_row.to_dict())
        
    db.session.commit()
    return jsonify({"count": len(injected), "status": "ok"}), 201


@ingestion_bp.post("/seed_data")
def seed_data():
    """Create sample users, assets, and realistic logs."""
    return jsonify(seed_base_data()), 201


@ingestion_bp.get("/logs")
@login_required
def get_logs():
    """Return stored logs filtered by the logged-in user's role."""
    role = session.get("role") or "observer"
    uid = session.get("user_id")
    user = None
    if uid:
        user = db.session.get(User, uid)
    logs = [log.to_dict() for log in Log.query.order_by(Log.timestamp.desc()).all()]
    # Executive roles see the full feed (matches access_control_service + avoids stale deploy edge cases).
    if str(role).strip().lower() in {"admin", "ceo"}:
        filtered_logs = logs
    else:
        if user:
            filtered_logs = filter_logs_for_session(
                role=str(role),
                user_id=user.id,
                user_department=user.department,
                logs=logs,
            )
        else:
            filtered_logs = filter_logs_by_role(str(role), logs)
    return jsonify({"count": len(filtered_logs), "logs": filtered_logs})
