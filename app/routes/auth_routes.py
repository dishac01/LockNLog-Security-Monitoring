from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from app.extensions import db
from app.models.user import User
from app.services.auth_service import authenticate_user, create_user
from app.utils.decorators import login_required

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_bp.post("/users")
def create_user():
    """Create a local user record."""
    payload = request.get_json(silent=True) or {}
    password = payload.get("password")
    if not password:
        return jsonify({"error": "password required", "status": 400}), 400

    user = create_user(
        username=payload["username"],
        email=payload["email"],
        password=password,
        role=payload.get("role", "observer"),
        department=payload.get("department"),
        access_level=payload.get("access_level", "read-only"),
        status=payload.get("status", "active"),
    )
    return jsonify({"user": user.to_dict()}), 201


@auth_bp.get("/users")
def list_users():
    """List local users."""
    return jsonify({"users": [user.to_dict() for user in User.query.order_by(User.id).all()]})


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        return jsonify({"error": "username and password required", "status": 400}), 400

    user = authenticate_user(username=username, password=password)
    if not user:
        return jsonify({"error": "invalid credentials", "status": 401}), 401

    session.clear()
    session["user_id"] = user.id
    session["role"] = user.role
    return jsonify({"status": "ok", "user": user.to_dict()})


@auth_bp.post("/logout")
def logout():
    session.clear()
    
    # Delete all temporary logs
    try:
        from app.models.log import Log
        Log.query.filter_by(is_temporary=True).delete()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error cleaning up temporary logs: {e}")

    return jsonify({"status": "ok"})


@auth_bp.get("/me")
@login_required
def me():
    user = db.session.get(User, session["user_id"])
    if not user:
        session.clear()
        return jsonify({"error": "authentication required", "status": 401}), 401
    return jsonify({"user": user.to_dict(), "role": session.get("role")})
