"""CRUD and validation tests for the Expense API."""

import pytest


def test_create_expense(client):
    response = client.post(
        "/api/expenses",
        json={"amount": 499.99, "category": "Travel",
              "description": "Cab to office", "spent_on": "2026-10-14"},
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["amount"] == 499.99
    assert body["category"] == "Travel"
    assert body["currency"] == "INR"
    assert body["id"] > 0


def test_create_defaults_currency_and_date(client):
    body = client.post(
        "/api/expenses", json={"amount": 100, "category": "Food"}
    ).get_json()
    assert body["currency"] == "INR"
    assert len(body["spent_on"]) == 10


@pytest.mark.parametrize("payload", [
    {},
    {"category": "Food"},
    {"amount": 10},
    {"amount": -5, "category": "Food"},
    {"amount": 0, "category": "Food"},
    {"amount": 10, "category": ""},
    {"amount": "abc", "category": "Food"},
    {"amount": 10, "category": "Food", "spent_on": "14-10-2026"},
    {"amount": 10, "category": "Food", "currency": "RUPEE"},
    {"amount": 10, "category": "x" * 51},
    {"amount": 10, "category": "Food", "unexpected": True},
])
def test_validation_rejects_bad_input(client, payload):
    response = client.post("/api/expenses", json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"] == "validation_error"


def test_validation_rejects_non_object_body(client):
    response = client.post("/api/expenses", json=["not", "an", "object"])
    assert response.status_code == 400


def test_list_expenses(client, sample_expense):
    client.post("/api/expenses", json={"amount": 20, "category": "Travel"})
    body = client.get("/api/expenses").get_json()
    assert body["count"] == 2
    assert len(body["items"]) == 2


def test_filter_by_category(client):
    client.post("/api/expenses", json={"amount": 20, "category": "Travel"})
    client.post("/api/expenses", json={"amount": 30, "category": "Food"})
    body = client.get("/api/expenses?category=travel").get_json()
    assert body["count"] == 1
    assert body["items"][0]["category"] == "Travel"


def test_filter_by_month(client):
    client.post("/api/expenses",
                json={"amount": 10, "category": "Food", "spent_on": "2026-09-05"})
    client.post("/api/expenses",
                json={"amount": 15, "category": "Food", "spent_on": "2026-10-05"})
    body = client.get("/api/expenses?month=2026-10").get_json()
    assert body["count"] == 1
    assert body["items"][0]["amount"] == 15


def test_invalid_month_returns_400(client):
    response = client.get("/api/expenses?month=October")
    assert response.status_code == 400


def test_get_single_expense(client, sample_expense):
    response = client.get(f"/api/expenses/{sample_expense['id']}")
    assert response.status_code == 200
    assert response.get_json()["id"] == sample_expense["id"]


def test_get_missing_expense_returns_404(client):
    assert client.get("/api/expenses/9999").status_code == 404


def test_patch_expense(client, sample_expense):
    response = client.patch(
        f"/api/expenses/{sample_expense['id']}", json={"amount": 300}
    )
    assert response.status_code == 200
    assert response.get_json()["amount"] == 300
    # untouched fields survive a partial update
    assert response.get_json()["category"] == "Groceries"


def test_patch_with_no_fields_returns_400(client, sample_expense):
    response = client.patch(f"/api/expenses/{sample_expense['id']}", json={})
    assert response.status_code == 400


def test_patch_missing_expense_returns_404(client):
    assert client.patch("/api/expenses/4242", json={"amount": 1}).status_code == 404


def test_delete_expense(client, sample_expense):
    url = f"/api/expenses/{sample_expense['id']}"
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


def test_summary_groups_by_category(client):
    client.post("/api/expenses", json={"amount": 100, "category": "Food"})
    client.post("/api/expenses", json={"amount": 250, "category": "Food"})
    client.post("/api/expenses", json={"amount": 50, "category": "Travel"})

    body = client.get("/api/expenses/summary").get_json()
    assert body["total"] == 400
    by_category = {row["category"]: row for row in body["by_category"]}
    assert by_category["Food"]["total"] == 350
    assert by_category["Food"]["count"] == 2
    assert body["by_category"][0]["category"] == "Food"
