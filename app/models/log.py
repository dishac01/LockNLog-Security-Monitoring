from __future__ import annotations

from sqlalchemy.dialects.sqlite import JSON

from app.extensions import db
from app.utils.helpers import utcnow


class Log(db.Model):
    __tablename__ = "logs"
    __table_args__ = (
        db.Index("ix_logs_timestamp", "timestamp"),
        db.Index("ix_logs_asset_id", "asset_id"),
        db.Index("ix_logs_severity", "severity"),
        db.Index("ix_logs_risk_band", "risk_band"),
    )

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False)
    asset_id = db.Column(db.String(64), db.ForeignKey("assets.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    event_type = db.Column(db.String(128), nullable=False)
    log_type = db.Column(db.String(32), nullable=False, index=True)
    severity = db.Column(db.String(16), nullable=False)
    source_ip = db.Column(db.String(64), nullable=True)
    destination_ip = db.Column(db.String(64), nullable=True)
    action = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(64), nullable=True)
    amount = db.Column(db.Float, nullable=True)
    metadata_json = db.Column("metadata", JSON, nullable=False, default=dict)
    risk_level = db.Column(db.String(32), nullable=True)
    anomaly_score = db.Column(db.Float, nullable=True)
    risk_score = db.Column(db.Float, nullable=True)
    risk_band = db.Column(db.String(16), nullable=True)
    is_temporary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    asset = db.relationship("Asset", lazy="joined")
    user = db.relationship("User", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "asset_id": self.asset_id,
            "asset_name": self.asset.name if self.asset else None,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "event_type": self.event_type,
            "log_type": self.log_type,
            "severity": self.severity,
            "source_ip": self.source_ip,
            "destination_ip": self.destination_ip,
            "action": self.action,
            "status": self.status,
            "amount": self.amount,
            "metadata": self.metadata_json or {},
            "risk_level": self.risk_level,
            "anomaly_score": self.anomaly_score,
            "risk_score": self.risk_score,
            "risk_band": self.risk_band,
            "is_temporary": self.is_temporary,
            "created_at": self.created_at.isoformat(),
        }
