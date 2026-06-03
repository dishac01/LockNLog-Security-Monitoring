"""Browser-facing pages (login form, post-login home)."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models.user import User
from app.services.auth_service import authenticate_user

web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def index():
    """Send users to landing or home if signed in."""
    if session.get("user_id"):
        return redirect(url_for("web.home"))
    return redirect(url_for("web.landing"))


@web_bp.get("/landing")
def landing():
    if session.get("user_id"):
        return redirect(url_for("web.console"))
    return render_template("landing.html")


@web_bp.get("/login")
def login_get():
    """Render the sign-in page."""
    if session.get("user_id"):
        return redirect(url_for("web.home"))
    return render_template("login.html", error=None)


@web_bp.post("/login")
def login_post():
    """Process HTML form login; sets session and redirects to home."""
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    if not username or not password:
        return (
            render_template("login.html", error="Username and password are required."),
            400,
        )

    user = authenticate_user(username=username, password=password)
    if not user:
        return render_template("login.html", error="Invalid username or password."), 401

    session.clear()
    session["user_id"] = user.id
    session["role"] = user.role
    # Land users on the SIEM console where charts live.
    return redirect(url_for("web.console"))


@web_bp.get("/home")
def home():
    """Simple landing page after login."""
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("web.login_get"))
    user = db.session.get(User, uid)
    if not user:
        session.clear()
        return redirect(url_for("web.login_get"))
    # Keep /home for compatibility, but default to console for the full dashboard experience.
    return redirect(url_for("web.console"))


@web_bp.get("/console")
def console():
    """Interactive log explorer (uses session; calls existing JSON APIs in the browser)."""
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("web.login_get"))
    user = db.session.get(User, uid)
    if not user:
        session.clear()
        return redirect(url_for("web.login_get"))
    return render_template("console.html", user=user)


@web_bp.get("/assets")
def assets_page():
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("web.login_get"))
    user = db.session.get(User, uid)
    if not user:
        session.clear()
        return redirect(url_for("web.login_get"))
    return render_template("assets.html", user=user)


@web_bp.get("/admin/requests")
def admin_requests_page():
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("web.login_get"))
    user = db.session.get(User, uid)
    if not user:
        session.clear()
        return redirect(url_for("web.login_get"))
    if (user.role or "").lower() != "admin":
        return redirect(url_for("web.home"))
    return render_template("admin_requests.html", user=user)


@web_bp.get("/logout")
def logout():
    """Clear session and return to login."""
    session.clear()
    return redirect(url_for("web.login_get"))
