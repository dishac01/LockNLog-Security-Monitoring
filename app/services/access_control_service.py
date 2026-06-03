from __future__ import annotations

from copy import deepcopy

from app.services.access_request_service import compute_effective_departments, log_type_for_department, normalize_department

def mask_ip(ip_value: str | None) -> str | None:
    if not ip_value or "." not in ip_value:
        return ip_value
    parts = ip_value.split(".")
    if len(parts) != 4:
        return ip_value
    return ".".join(parts[:3] + ["xxx"])


def filter_logs_by_role(role: str, logs: list[dict]) -> list[dict]:
    """
    Server-side access enforcement for the log feed.

    Backwards compatible: callers can pass just `role` and a list of serialized logs.
    When a session user exists, this also honors approved, unexpired cross-department
    access grants.
    """
    normalized_role = (role or "observer").lower().strip()

    if normalized_role in {"admin", "ceo"}:
        return logs

    if normalized_role == "observer":
        masked_logs = []
        for log in logs:
            item = deepcopy(log)
            item["source_ip"] = mask_ip(item.get("source_ip"))
            item["destination_ip"] = mask_ip(item.get("destination_ip"))
            masked_logs.append(item)
        return masked_logs

    # Back-compat behavior: only own stream for dept roles.
    if normalized_role in {"soc", "finance", "hr"}:
        return [log for log in logs if (log.get("log_type") or "").lower() == normalized_role]

    # Unknown roles: default to previous permissive behavior.
    return logs


def filter_logs_for_session(
    *,
    role: str,
    user_id: int | None,
    user_department: str | None,
    logs: list[dict],
) -> list[dict]:
    """Preferred filter: uses session user + approved grants; masks observer IPs."""
    normalized_role = (role or "observer").lower().strip()
    if normalized_role in {"admin", "ceo"}:
        return logs
    if normalized_role == "observer":
        masked_logs = []
        for log in logs:
            item = deepcopy(log)
            item["source_ip"] = mask_ip(item.get("source_ip"))
            item["destination_ip"] = mask_ip(item.get("destination_ip"))
            masked_logs.append(item)
        return masked_logs

    effective_depts = compute_effective_departments(normalize_department(user_department), normalized_role, user_id)
    allowed_types = {t for d in effective_depts if (t := log_type_for_department(d))}
    if normalized_role in {"soc", "finance", "hr"} and not allowed_types:
        allowed_types = {normalized_role}

    if allowed_types:
        return [log for log in logs if (log.get("log_type") or "").lower() in allowed_types]
    return []
