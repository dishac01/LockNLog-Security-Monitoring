from __future__ import annotations

from flask import Blueprint, jsonify, session

from app.models.log import Log
from app.services.access_control_service import filter_logs_by_role
from app.services.dashboard_service import (
    get_ceo_dashboard,
    get_finance_dashboard,
    get_hr_dashboard,
    get_soc_dashboard,
    summarize_intel_from_log_dicts,
)
from app.utils.decorators import login_required

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/v1")


@dashboard_bp.get("/dashboard")
@login_required
def get_dashboard():
    """Return the dashboard for the logged-in user's role."""
    normalized_role = (session.get("role") or "observer").lower()

    if normalized_role == "soc":
        return jsonify(get_soc_dashboard())
    if normalized_role == "finance":
        return jsonify(get_finance_dashboard())
    if normalized_role == "hr":
        return jsonify(get_hr_dashboard())
    if normalized_role == "observer":
        logs = [log.to_dict() for log in Log.query.order_by(Log.timestamp.desc()).limit(20)]
        return jsonify(
            {
                "role": "observer",
                "intelligence": summarize_intel_from_log_dicts(logs),
                "recent_logs": filter_logs_by_role("observer", logs),
            }
        )
    if normalized_role == "ceo":
        payload = get_ceo_dashboard()
        payload["role"] = "ceo"
        return jsonify(payload)

    return jsonify({"error": "unsupported role", "status": 400}), 400


@dashboard_bp.get("/dashboard/<role>")
@login_required
def get_dashboard_legacy(role: str):
    """Legacy endpoint kept for compatibility; ignores URL role and uses session role."""
    return get_dashboard()
