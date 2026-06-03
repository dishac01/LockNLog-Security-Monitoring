from __future__ import annotations

from flask import Flask, jsonify

from app.routes.admin_routes import admin_bp
from app.routes.access_routes import access_bp
from app.routes.asset_routes import asset_bp
from app.routes.auth_routes import auth_bp
from app.routes.ceo_routes import ceo_bp
from app.routes.dashboard_routes import dashboard_bp
from app.routes.ingestion_routes import ingestion_bp
from app.routes.web_routes import web_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(web_bp)
    app.register_blueprint(ingestion_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(access_bp)
    app.register_blueprint(asset_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(ceo_bp)

    @app.get("/api/v1/health")
    def health():
        return jsonify({"status": "ok", "service": "locknlog"})
