"""Database models for the Expense API."""

from datetime import date, datetime, timezone

from .extensions import db


def _utcnow():
    """Naive UTC timestamp (SQLite/MySQL friendly, no deprecation warnings)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    category = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    spent_on = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(
        db.DateTime, nullable=False, default=_utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "amount": round(float(self.amount), 2),
            "currency": self.currency,
            "category": self.category,
            "description": self.description,
            "spent_on": self.spent_on.isoformat(),
            "created_at": self.created_at.isoformat(timespec="seconds"),
        }

    def __repr__(self):
        return f"<Expense {self.id} {self.category} {self.amount}>"
