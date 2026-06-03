from __future__ import annotations

import logging
from http import HTTPStatus
from sqlalchemy.exc import OperationalError
from sqlalchemy import text

from flask import Flask, jsonify, request

from app.config import Config
from app.extensions import db
from app.models import AccessRequest, FeatureVector  # noqa: F401  # register models for create_all
from app.routes import register_blueprints
from app.utils.db_schema import (
    ensure_access_request_schema,
    ensure_asset_inventory_schema,
    ensure_intelligence_schema,
)
from app.services.mock_data_service import seed_base_data
from app.utils.logger import configure_logging

background_logger = logging.getLogger(__name__)


def _cleanup_temporary_logs():
    try:
        from app.models.log import Log
        Log.query.filter_by(is_temporary=True).delete()
        db.session.commit()
    except Exception as e:
        background_logger.exception(f"failed to cleanup temporary logs: {e}")


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config["TESTING"] = testing

    configure_logging(app.config["LOG_LEVEL"])
    db.init_app(app)
    register_blueprints(app)

    with app.app_context():
        try:
            db.create_all()
        except OperationalError:
            print("⚠️ DB locked, skipping create_all")

        # ✅ ENABLE WAL MODE (fix concurrency)
        db.session.execute(text("PRAGMA journal_mode=WAL;"))
        db.session.commit()

        ensure_intelligence_schema()
        ensure_asset_inventory_schema()
        ensure_access_request_schema()

        _cleanup_temporary_logs()
        seed_base_data()

    @app.before_request
    def log_request() -> None:
        app.logger.info("%s %s", request.method, request.path)

    @app.errorhandler(Exception)
    def handle_error(error: Exception):
        status_code = getattr(error, "code", HTTPStatus.INTERNAL_SERVER_ERROR)
        app.logger.exception("request failed")
        return (
            jsonify({"error": str(error), "status": getattr(error, "code", 500)})
        )

    if not app.debug and not app.testing:
        pass

    return app
