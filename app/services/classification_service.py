from __future__ import annotations


SEVERITY_ORDER = ("low", "medium", "high", "critical")


def classify_log(log: dict) -> dict:
    text_blob = " ".join(
        str(log.get(key, "")) for key in ("event_type", "action", "status", "message")
    ).lower()

    if "transaction" in text_blob or log.get("amount") is not None:
        log_type = "finance"
    elif "employee" in text_blob or "export" in text_blob:
        log_type = "hr"
    else:
        log_type = "soc"

    severity = "low"
    amount = float(log.get("amount") or 0)
    status = str(log.get("status", "")).lower()

    if log_type == "finance":
        if amount >= 100000 or status in {"failed", "unauthorized"}:
            severity = "high"
        if amount >= 250000:
            severity = "critical"
    elif log_type == "hr":
        if "export" in text_blob or "modify" in text_blob:
            severity = "medium"
        if "salary" in text_blob or status == "denied":
            severity = "high"
    else:
        if "port scan" in text_blob or "scan" in text_blob:
            severity = "high"
        if "failed" in text_blob or "denied" in text_blob:
            severity = "medium"
        if "malware" in text_blob or "bruteforce" in text_blob:
            severity = "critical"

    log["log_type"] = log_type
    log["event_type"] = log.get("event_type") or f"{log_type}_event"
    log["severity"] = log.get("severity") or severity
    return log
