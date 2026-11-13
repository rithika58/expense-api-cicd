"""Flask application factory for the Expense API."""

import logging
import os
import time
import uuid

from flask import Flask, g, jsonify, request

from .config import Config
from .extensions import db
from .logging_conf import configure_logging
from .routes import bp


def create_app(config_object=Config, **overrides):
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.config.update(overrides)

    configure_logging(app.config["LOG_LEVEL"])
    log = logging.getLogger("expense_api")

    db.init_app(app)
    app.register_blueprint(bp)

    @app.before_request
    def _start_timer():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        g.started_at = time.perf_counter()

    @app.after_request
    def _log_request(response):
        duration_ms = round((time.perf_counter() - g.started_at) * 1000, 2)
        response.headers["X-Request-ID"] = g.request_id
        # Structured, single-line logs: easy to grep/journalctl later.
        log.info(
            "request",
            extra={
                "request_id": g.request_id,
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @app.errorhandler(404)
    def _not_found(_err):
        return jsonify(error="not_found", message="Resource does not exist"), 404

    @app.errorhandler(405)
    def _not_allowed(_err):
        return jsonify(error="method_not_allowed",
                       message="HTTP method not allowed for this route"), 405

    @app.errorhandler(500)
    def _server_error(_err):
        db.session.rollback()
        log.exception("unhandled_error")
        return jsonify(error="internal_error", message="Unexpected server error"), 500

    if app.config.get("AUTO_CREATE_TABLES"):
        with app.app_context():
            db.create_all()
            log.info("database_ready", extra={"uri": _safe_uri(app)})

    return app


def _safe_uri(app):
    """Hide passwords before logging a database URI."""
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if "@" in uri:
        head, tail = uri.split("@", 1)
        return head.split("://")[0] + "://***@" + tail
    return uri


def _bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}
