"""Shared pytest fixtures."""

import pytest

from app import create_app
from app.config import Config
from app.extensions import db as _db


class TestConfig(Config):
    TESTING = True
    AUTO_CREATE_TABLES = True
    LOG_LEVEL = "WARNING"
    GIT_SHA = "test-sha"


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "test.db"
    application = create_app(
        TestConfig,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
    )
    yield application
    with application.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample_expense(client):
    response = client.post(
        "/api/expenses",
        json={
            "amount": 249.5,
            "category": "Groceries",
            "description": "Weekly vegetables",
            "spent_on": "2026-11-01",
        },
    )
    assert response.status_code == 201
    return response.get_json()
