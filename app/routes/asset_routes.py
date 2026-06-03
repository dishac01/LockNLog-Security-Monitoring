from __future__ import annotations

from flask import Blueprint, jsonify, session

from app.extensions import db
from app.models.asset import Asset
from app.models.user import User
from app.services.asset_service import (
    filter_asset_fields,
    get_asset_detail_payload,
    list_assets_for_session,
    refresh_asset_computed_fields,
)
from app.utils.decorators import login_required


asset_bp = Blueprint("assets", __name__, url_prefix="/api/v1/assets")


@asset_bp.get("")
@asset_bp.get("/")
@login_required
def list_assets():
    uid = session.get("user_id")
    role = session.get("role") or "observer"
    user = db.session.get(User, uid) if uid else None

    assets = list_assets_for_session(
        role=str(role),
        user_id=user.id if user else None,
        user_department=user.department if user else None,
    )

    out = [filter_asset_fields(a, str(role)) for a in assets]

    return jsonify({"count": len(out), "assets": out})


@asset_bp.get("/<asset_id>")
@login_required
def asset_detail(asset_id: str):
    role = session.get("role") or "observer"
    try:
        payload = get_asset_detail_payload(asset_id, str(role))
    except LookupError as exc:
        return jsonify({"error": str(exc), "status": 404}), 404
    return jsonify(payload)

