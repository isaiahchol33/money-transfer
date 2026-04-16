
from app import db
from datetime import datetime


class Transaction(db.Model):
    __tablename__ = "transactions"
    __table_args__ = {'extend_existing': True}

    # ---------- PRIMARY KEY ----------
    id = db.Column(db.Integer, primary_key=True)

    # ---------- SENDER INFO ----------
    sender_cashier_id = db.Column(db.Integer, nullable=False)
    sender_cashier_name = db.Column(db.String(100), nullable=False)
    sender_location = db.Column(db.String(100), nullable=True)

    sender_name = db.Column(db.String(100), nullable=False)
    sender_phone = db.Column(db.String(20), nullable=True)

    # ---------- RECEIVER INFO ----------
    receiver_cashier_id = db.Column(db.Integer, nullable=True)
    receiver_cashier_name = db.Column(db.String(100), nullable=True)
    receiver_location = db.Column(db.String(100), nullable=True)

    receiver_name = db.Column(db.String(100), nullable=False)
    receiver_phone = db.Column(db.String(20), nullable=True)

    # ---------- TRANSACTION DETAILS ----------
    amount = db.Column(db.Float, nullable=False)
    commission = db.Column(db.Float, nullable=False, default=0.0)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Pending"
    )  # Pending, Paid, Completed, Failed

    date = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # ---------- CONSTANTS ----------
    STATUS_PENDING = "Pending"
    STATUS_PAID = "Paid"
    STATUS_COMPLETED = "Completed"
    STATUS_FAILED = "Failed"

    # ---------- HELPERS ----------
    @property
    def total_amount(self):
        """Return total (amount + commission)"""
        return round((self.amount or 0) + (self.commission or 0), 2)

    def mark_paid(self, cashier_id=None, cashier_name=None):
        """Mark transaction as Paid"""
        self.status = self.STATUS_PAID
        if cashier_id:
            self.receiver_cashier_id = cashier_id
        if cashier_name:
            self.receiver_cashier_name = cashier_name

    def mark_completed(self):
        """Mark transaction as Completed"""
        self.status = self.STATUS_COMPLETED

    def mark_failed(self):
        """Mark transaction as Failed"""
        self.status = self.STATUS_FAILED

    def is_pending(self):
        return self.status == self.STATUS_PENDING

    def is_paid(self):
        return self.status == self.STATUS_PAID

    def is_completed(self):
        return self.status == self.STATUS_COMPLETED

    def is_failed(self):
        return self.status == self.STATUS_FAILED

    # ---------- SERIALIZER (FOR APIs / AJAX) ----------
    def to_dict(self):
        return {
            "id": self.id,
            "sender_name": self.sender_name,
            "sender_phone": self.sender_phone,
            "sender_location": self.sender_location,
            "receiver_name": self.receiver_name,
            "receiver_phone": self.receiver_phone,
            "receiver_location": self.receiver_location,
            "amount": round(self.amount or 0, 2),
            "commission": round(self.commission or 0, 2),
            "total": self.total_amount,
            "status": self.status,
            "date": self.date.strftime("%Y-%m-%d %H:%M") if self.date else None
        }

    # ---------- DEBUG ----------
    def __repr__(self):
        return (
            f"<Transaction #{self.id} | "
            f"{self.sender_name} -> {self.receiver_name} | "
            f"{self.amount} SSP | {self.status}>"
        )