from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.models.asset import Asset
from app.models.access_request import AccessRequest
from app.models.log import Log
from app.models.user import User
from app.services.access_request_service import approve_request, deny_request
from app.utils.decorators import login_required, role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")


@admin_bp.get("/summary")
def get_summary():
    """Return simple admin counts for local system visibility."""
    return jsonify(
        {
            "users": User.query.count(),
            "assets": Asset.query.count(),
            "logs": Log.query.count(),
        }
    )


@admin_bp.get("/requests")
@login_required
@role_required({"admin"})
def list_access_requests():
    rows = AccessRequest.query.order_by(AccessRequest.requested_at.desc()).limit(500).all()
    return jsonify({"count": len(rows), "requests": [r.to_dict() for r in rows]})


@admin_bp.post("/requests/<int:request_id>/approve")
@login_required
@role_required({"admin"})
def approve_access_request(request_id: int):
    payload = request.get_json(silent=True) or {}
    duration_hours = payload.get("duration_hours") or payload.get("duration") or 8
    try:
        req = approve_request(request_id, int(duration_hours))
    except LookupError as exc:
        return jsonify({"error": str(exc), "status": 404}), 404
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "status": 400}), 400
    return jsonify({"status": "ok", "request": req.to_dict()})


@admin_bp.post("/requests/<int:request_id>/deny")
@login_required
@role_required({"admin"})
def deny_access_request(request_id: int):
    try:
        req = deny_request(request_id)
    except LookupError as exc:
        return jsonify({"error": str(exc), "status": 404}), 404
    return jsonify({"status": "ok", "request": req.to_dict()})
