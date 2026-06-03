from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.access_request import AccessRequest


DEPARTMENT_TO_LOG_TYPE: dict[str, str] = {
    "IT": "soc",
    "SOC": "soc",
    "Finance": "finance",
    "HR": "hr",
}


ALLOWED_TARGET_DEPARTMENTS = {"IT", "Finance", "HR"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_department(dept: str | None) -> str | None:
    if dept is None:
        return None
    d = str(dept).strip()
    if not d:
        return None
    # Preserve canonical names used in seeding & UI
    if d.lower() in {"it", "soc"}:
        return "IT"
    if d.lower() == "finance":
        return "Finance"
    if d.lower() == "hr":
        return "HR"
    return d


def log_type_for_department(dept: str | None) -> str | None:
    d = normalize_department(dept)
    if not d:
        return None
    return DEPARTMENT_TO_LOG_TYPE.get(d)


def list_active_approved_requests_for_user(user_id: int) -> list[AccessRequest]:
    now = _utcnow()
    return (
        AccessRequest.query.filter_by(requester_user_id=user_id, status="approved")
        .filter(AccessRequest.expires_at.isnot(None))
        .filter(AccessRequest.expires_at > now)
        .order_by(AccessRequest.expires_at.asc())
        .all()
    )


def compute_effective_departments(
    base_department: str | None,
    user_role: str,
    user_id: int | None,
) -> set[str]:
    """
    Returns the set of departments the user can view.
    - Admin/CEO -> all
    - Dept roles -> their own department + approved temporary grants
    - Observer -> none (observer uses separate masking rule)
    """
    role = (user_role or "observer").lower().strip()
    if role in {"admin", "ceo"}:
        return {"IT", "Finance", "HR"}

    base = normalize_department(base_department)
    if role == "observer":
        return set()

    effective: set[str] = set()
    if base in ALLOWED_TARGET_DEPARTMENTS:
        effective.add(base)

    if user_id is not None:
        for req in list_active_approved_requests_for_user(int(user_id)):
            td = normalize_department(req.target_department)
            if td in ALLOWED_TARGET_DEPARTMENTS:
                effective.add(td)
    return effective


def create_access_request(
    requester_user_id: int,
    requester_department: str | None,
    target_department: str,
    reason: str,
    duration_hours: int,
) -> AccessRequest:
    td = normalize_department(target_department)
    if td not in ALLOWED_TARGET_DEPARTMENTS:
        raise ValueError("invalid target_department")

    hrs = int(duration_hours)
    if hrs < 1:
        raise ValueError("duration_hours must be >= 1")
    if hrs > 24 * 14:
        raise ValueError("duration_hours too long (max 336h)")

    req = AccessRequest(
        requester_user_id=int(requester_user_id),
        requester_department=normalize_department(requester_department),
        target_department=td,
        reason=(reason or "").strip(),
        status="pending",
    )
    db.session.add(req)
    db.session.commit()
    return req


def approve_request(request_id: int, duration_hours: int) -> AccessRequest:
    req = db.session.get(AccessRequest, int(request_id))
    if not req:
        raise LookupError("access request not found")
    if req.status != "pending":
        return req
    hrs = int(duration_hours)
    if hrs < 1:
        raise ValueError("duration_hours must be >= 1")
    if hrs > 24 * 14:
        raise ValueError("duration_hours too long (max 336h)")
    now = _utcnow()
    req.status = "approved"
    req.approved_at = now
    req.expires_at = now + timedelta(hours=hrs)
    db.session.commit()
    return req


def deny_request(request_id: int) -> AccessRequest:
    req = db.session.get(AccessRequest, int(request_id))
    if not req:
        raise LookupError("access request not found")
    if req.status != "pending":
        return req
    req.status = "denied"
    req.approved_at = _utcnow()
    db.session.commit()
    return req

