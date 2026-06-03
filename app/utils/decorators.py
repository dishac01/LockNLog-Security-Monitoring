from __future__ import annotations

from functools import wraps

from flask import jsonify, session


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "authentication required", "status": 401}), 401
        return fn(*args, **kwargs)

    return wrapper


def role_required(allowed_roles: set[str] | list[str] | tuple[str, ...]):
    allowed = set(allowed_roles)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            role = (session.get("role") or "").lower()
            if role not in allowed:
                return jsonify({"error": "forbidden", "status": 403}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator

