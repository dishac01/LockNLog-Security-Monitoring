from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.user import User


def create_user(
    username: str,
    email: str,
    password: str,
    role: str,
    department: str | None,
    access_level: str = "read-only",
    status: str = "active",
) -> User:
    password_hash = generate_password_hash(password)
    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        role=role,
        department=department,
        access_level=access_level,
        status=status,
    )
    db.session.add(user)
    db.session.commit()
    return user


def authenticate_user(username: str, password: str) -> User | None:
    user = User.query.filter_by(username=username).first()
    if not user:
        return None
    if user.status != "active":
        return None
    if not check_password_hash(user.password_hash, password):
        return None
    return user

