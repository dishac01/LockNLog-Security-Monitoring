import os


class Config:
    SECRET_KEY = os.environ.get("LOCKNLOG_SECRET_KEY", "locknlog-dev-key")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///locknlog.db",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
    "connect_args": {
        "check_same_thread": False
        }
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BACKGROUND_INGESTION_INTERVAL = int(
        os.environ.get("BACKGROUND_INGESTION_INTERVAL", "7")
    )
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
