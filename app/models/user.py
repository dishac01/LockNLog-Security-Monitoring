from __future__ import annotations

from app.extensions import db
from app.utils.helpers import utcnow


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, index=True)
    department = db.Column(db.String(32), nullable=True)
    access_level = db.Column(db.String(32), nullable=False, default="read-only")
    status = db.Column(db.String(32), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "department": self.department,
            "access_level": self.access_level,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }
