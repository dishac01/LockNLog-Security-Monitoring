"""CEO-only mitigation chat API (uses curated dataset + TF-IDF + live assets/logs)."""

from __future__ import annotations

from functools import wraps
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file, session

from app.models.log import Log
from app.services.ceo_chat_service import chat as ceo_chat
from app.services.ceo_daily_report_pdf import build_daily_pdf_bytes
from app.utils.decorators import login_required

ceo_bp = Blueprint("ceo", __name__, url_prefix="/api/v1/ceo")


def ceo_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if (session.get("role") or "").lower() != "ceo":
            return jsonify({"error": "CEO role required", "status": 403}), 403
        return fn(*args, **kwargs)

    return wrapper


@ceo_bp.get("/logs")
@login_required
@ceo_required
def ceo_logs():
    """Full log listing for the CEO console (same shape as /api/v1/logs)."""
    rows = [log.to_dict() for log in Log.query.order_by(Log.timestamp.desc()).all()]
    return jsonify({"count": len(rows), "logs": rows})


@ceo_bp.post("/chat")
@login_required
@ceo_required
def post_chat():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message") or ""
    history = payload.get("history") or []
    if not str(message).strip():
        return jsonify({"error": "message is required", "status": 400}), 400
    result = ceo_chat(message, history)
    return jsonify(result)


@ceo_bp.get("/report/daily.pdf")
@login_required
@ceo_required
def daily_report_pdf():
    """Downloadable daily CEO report (PDF)."""
    try:
        pdf_bytes = build_daily_pdf_bytes()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"pdf generation failed: {exc}", "status": 500}), 500
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="locknlog-ceo-daily-report.pdf",
    )


@ceo_bp.get("/chat/bootstrap")
@login_required
@ceo_required
def chat_bootstrap():
    """Opening assistant message (no retrieval yet)."""
    text = (
        "I'm your **LockNLog executive mitigation assistant**. I'm trained on a **curated playbook** "
        "(TF-IDF index over local JSONL) and, on each reply, I also read your **registered asset archive** "
        "and **recent high-risk logs** from this deployment.\n\n"
        "Ask things like: *“What should we do about internet-facing assets with high anomaly?”* or "
        "*“Summarize mitigations for finance CRITICAL events.”*"
    )
    return jsonify({"message": text})
