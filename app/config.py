"""Configuration loaded from environment variables (12-factor style)."""

import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///expenses.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Tables are created on boot for the scaffold. A real deployment moves
    # this to `flask db upgrade` (Alembic migrations) instead.
    AUTO_CREATE_TABLES = os.getenv("AUTO_CREATE_TABLES", "true").lower() in {
        "1", "true", "yes", "on"
    }

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    GIT_SHA = os.getenv("GIT_SHA", "dev")
    APP_ENV = os.getenv("APP_ENV", "development")
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # reject bodies larger than 1 MB
