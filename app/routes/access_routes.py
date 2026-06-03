from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from app.extensions import db
from app.models.access_request import AccessRequest
from app.models.user import User
from app.services.access_request_service import (
    ALLOWED_TARGET_DEPARTMENTS,
    create_access_request,
    list_active_approved_requests_for_user,
    normalize_department,
)
from app.utils.decorators import login_required


access_bp = Blueprint("access", __name__, url_prefix="/api/v1/access")


@access_bp.get("/me")
@login_required
def me():
    uid = session.get("user_id")
    user = db.session.get(User, uid) if uid else None
    if not user:
        session.clear()
        return jsonify({"error": "authentication required", "status": 401}), 401

    approved = list_active_approved_requests_for_user(user.id)
    pending = (
        AccessRequest.query.filter_by(requester_user_id=user.id, status="pending")
        .order_by(AccessRequest.requested_at.desc())
        .limit(25)
        .all()
    )
    return jsonify(
        {
            "user": user.to_dict(),
            "approved_grants": [r.to_dict() for r in approved],
            "pending_requests": [r.to_dict() for r in pending],
            "allowed_target_departments": sorted(ALLOWED_TARGET_DEPARTMENTS),
        }
    )


@access_bp.post("/request")
@login_required
def request_access():
    uid = session.get("user_id")
    user = db.session.get(User, uid) if uid else None
    if not user:
        session.clear()
        return jsonify({"error": "authentication required", "status": 401}), 401

    payload = request.get_json(silent=True) or {}
    target_department = payload.get("target_department")
    reason = payload.get("reason") or ""
    duration_hours = payload.get("duration_hours") or payload.get("duration") or 8

    try:
        req = create_access_request(
            requester_user_id=user.id,
            requester_department=normalize_department(user.department),
            target_department=str(target_department or ""),
            reason=str(reason),
            duration_hours=int(duration_hours),
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "status": 400}), 400

    return jsonify({"status": "ok", "request": req.to_dict()}), 201

