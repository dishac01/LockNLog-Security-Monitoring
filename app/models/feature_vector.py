from __future__ import annotations

from sqlalchemy.dialects.sqlite import JSON

from app.extensions import db
from app.utils.helpers import utcnow


class FeatureVector(db.Model):
    """Stores engineered features per log for the intelligence layer."""

    __tablename__ = "feature_vectors"
    __table_args__ = (db.Index("ix_feature_vectors_log_type", "log_type"),)

    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey("logs.id"), nullable=False, unique=True, index=True)
    log_type = db.Column(db.String(32), nullable=False)
    features_json = db.Column("features", JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    log = db.relationship("Log", backref=db.backref("feature_vector", uselist=False))
