from __future__ import annotations

from app.extensions import db
from app.utils.helpers import utcnow


class AccessRequest(db.Model):
    __tablename__ = "access_requests"

    id = db.Column(db.Integer, primary_key=True)
    requester_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    requester_department = db.Column(db.String(32), nullable=True)
    target_department = db.Column(db.String(32), nullable=False)
    reason = db.Column(db.String(1000), nullable=False, default="")
    status = db.Column(db.String(16), nullable=False, default="pending")  # pending/approved/denied
    requested_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)

    requester = db.relationship("User", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "requester_user_id": self.requester_user_id,
            "requester_username": self.requester.username if self.requester else None,
            "requester_department": self.requester_department,
            "target_department": self.target_department,
            "reason": self.reason,
            "status": self.status,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

