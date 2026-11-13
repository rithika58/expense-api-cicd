"""REST routes for the Expense API.

Endpoints
---------
GET    /health                     liveness/readiness probe (used by CI/CD)
GET    /version                    build metadata (git SHA + environment)
GET    /api/expenses               list expenses (filter: category, month)
POST   /api/expenses               create an expense
GET    /api/expenses/<id>          read one expense
PATCH  /api/expenses/<id>          partially update an expense
DELETE /api/expenses/<id>          delete an expense
GET    /api/expenses/summary       totals grouped by category
"""

from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, text

from .extensions import db
from .models import Expense

bp = Blueprint("api", __name__)

MAX_AMOUNT = 10_000_000
ALLOWED_FIELDS = {"amount", "currency", "category", "description", "spent_on"}


# --------------------------------------------------------------- helpers ----
def _error(message, field=None, status=400):
    payload = {"error": "validation_error", "message": message}
    if field:
        payload["field"] = field
    return jsonify(payload), status


def _clean_payload(payload, partial=False):
    """Validate an incoming expense body. Returns (data, error_response)."""
    if not isinstance(payload, dict):
        return None, _error("Request body must be a JSON object.")

    unknown = set(payload) - ALLOWED_FIELDS
    if unknown:
        return None, _error(f"Unknown field(s): {', '.join(sorted(unknown))}")

    if not partial:
        missing = [f for f in ("amount", "category") if f not in payload]
        if missing:
            return None, _error(f"Missing required field(s): {', '.join(missing)}")

    data = {}

    if "amount" in payload:
        try:
            amount = float(payload["amount"])
        except (TypeError, ValueError):
            return None, _error("amount must be a number.", "amount")
        if not 0 < amount <= MAX_AMOUNT:
            return None, _error(
                f"amount must be greater than 0 and at most {MAX_AMOUNT}.",
                "amount",
            )
        data["amount"] = round(amount, 2)

    if "currency" in payload:
        currency = str(payload["currency"]).upper()
        if len(currency) != 3 or not currency.isalpha():
            return None, _error("currency must be a 3-letter code.", "currency")
        data["currency"] = currency

    if "category" in payload:
        category = str(payload["category"]).strip()
        if not category:
            return None, _error("category cannot be empty.", "category")
        if len(category) > 50:
            return None, _error("category must be 50 characters or fewer.",
                                "category")
        data["category"] = category

    if "description" in payload:
        description = payload["description"]
        if description is not None:
            description = str(description).strip()
            if len(description) > 255:
                return None, _error("description must be 255 characters or fewer.",
                                    "description")
        data["description"] = description

    if "spent_on" in payload:
        try:
            data["spent_on"] = datetime.strptime(
                str(payload["spent_on"]), "%Y-%m-%d"
            ).date()
        except ValueError:
            return None, _error("spent_on must be an ISO date (YYYY-MM-DD).",
                                "spent_on")

    if partial and not data:
        return None, _error("No updatable fields supplied.")

    return data, None


# ---------------------------------------------------------------- routes ----
@bp.get("/health")
def health():
    """Used by the Docker HEALTHCHECK, nginx, and the deploy gate."""
    db_status = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB failure means "not ready"
        db_status = "unavailable"
    code = 200 if db_status == "ok" else 503
    return jsonify(
        status="ok" if code == 200 else "degraded",
        database=db_status,
        version=current_app.config["GIT_SHA"],
    ), code


@bp.get("/version")
def version():
    return jsonify(
        git_sha=current_app.config["GIT_SHA"],
        environment=current_app.config["APP_ENV"],
    )


@bp.get("/api/expenses")
def list_expenses():
    query = Expense.query

    category = request.args.get("category")
    if category:
        query = query.filter(Expense.category.ilike(category))

    month = request.args.get("month")
    if month:
        try:
            start = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            return _error("month must be in YYYY-MM format.", "month")
        end = date(start.year + start.month // 12,
                   1 if start.month == 12 else start.month + 1, 1)
        query = query.filter(Expense.spent_on >= start,
                             Expense.spent_on < end)

    try:
        limit = min(int(request.args.get("limit", 100)), 500)
    except ValueError:
        return _error("limit must be an integer.", "limit")

    items = query.order_by(Expense.spent_on.desc(), Expense.id.desc()) \
                 .limit(limit).all()
    return jsonify(count=len(items), items=[e.to_dict() for e in items])


@bp.post("/api/expenses")
def create_expense():
    data, err = _clean_payload(request.get_json(silent=True))
    if err:
        return err

    expense = Expense(**data)
    db.session.add(expense)
    db.session.commit()
    return jsonify(expense.to_dict()), 201


@bp.get("/api/expenses/<int:expense_id>")
def get_expense(expense_id):
    expense = db.session.get(Expense, expense_id)
    if expense is None:
        return jsonify(error="not_found", message="Expense not found"), 404
    return jsonify(expense.to_dict())


@bp.patch("/api/expenses/<int:expense_id>")
def update_expense(expense_id):
    expense = db.session.get(Expense, expense_id)
    if expense is None:
        return jsonify(error="not_found", message="Expense not found"), 404

    data, err = _clean_payload(request.get_json(silent=True), partial=True)
    if err:
        return err

    for field, value in data.items():
        setattr(expense, field, value)
    db.session.commit()
    return jsonify(expense.to_dict())


@bp.delete("/api/expenses/<int:expense_id>")
def delete_expense(expense_id):
    expense = db.session.get(Expense, expense_id)
    if expense is None:
        return jsonify(error="not_found", message="Expense not found"), 404
    db.session.delete(expense)
    db.session.commit()
    return "", 204


@bp.get("/api/expenses/summary")
def summary():
    rows = (
        db.session.query(
            Expense.category,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    by_category = [
        {"category": r.category, "total": round(float(r.total), 2),
         "count": r.count}
        for r in rows
    ]
    return jsonify(
        total=round(sum(item["total"] for item in by_category), 2),
        by_category=by_category,
    )
