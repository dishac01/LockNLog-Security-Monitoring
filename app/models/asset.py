from __future__ import annotations

from sqlalchemy.dialects.sqlite import JSON

from app.extensions import db


class Asset(db.Model):
    __tablename__ = "assets"

    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    department = db.Column(db.String(32), nullable=False, index=True)
    asset_type = db.Column(db.String(64), nullable=True)
    business_value = db.Column(db.Float, nullable=False, default=1.0)
    criticality = db.Column(db.Integer, nullable=False, default=1)
    sensitivity = db.Column(db.String(32), nullable=False, default="internal")
    exposure = db.Column(db.String(32), nullable=False, default="internal")

    # Finance-specific inventory
    transaction_volume = db.Column(db.Float, nullable=True)
    avg_transaction_amount = db.Column(db.Float, nullable=True)

    # HR-specific inventory
    data_types_json = db.Column("data_types", JSON, nullable=True)
    employee_count = db.Column(db.Integer, nullable=True)

    # SOC-specific inventory
    ip_address = db.Column(db.String(64), nullable=True)
    exposed_ports_json = db.Column("exposed_ports", JSON, nullable=True)

    # Common computed
    risk_score = db.Column(db.Float, nullable=True)
    last_activity = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "department": self.department,
            "asset_type": self.asset_type,
            "business_value": self.business_value,
            "criticality": self.criticality,
            "sensitivity": self.sensitivity,
            "exposure": self.exposure,
            "transaction_volume": self.transaction_volume,
            "avg_transaction_amount": self.avg_transaction_amount,
            "data_types": self.data_types_json,
            "employee_count": self.employee_count,
            "ip_address": self.ip_address,
            "exposed_ports": self.exposed_ports_json,
            "risk_score": self.risk_score,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
        }
