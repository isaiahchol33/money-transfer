# app/models/commission.py

from app import db
from datetime import datetime


class Commission(db.Model):
    __tablename__ = "commissions"

    id = db.Column(db.Integer, primary_key=True)

    # Store as percentage (e.g. 2.0 = 2%)
    percentage = db.Column(db.Float, nullable=False, default=2.0)

    active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # -------------------------------
    # GET ACTIVE COMMISSION
    # -------------------------------
    @staticmethod
    def get_active():
        """Return the current active commission"""
        return Commission.query.filter_by(active=True)\
            .order_by(Commission.created_at.desc())\
            .first()

    # -------------------------------
    # CALCULATE COMMISSION
    # -------------------------------
    @staticmethod
    def calculate_commission(amount):
        if not amount or amount <= 0:
            return 0.0
        commission_obj = Commission.get_active()
        DEFAULT_COMMISSION = 2.0
        percentage = commission_obj.percentage if commission_obj else DEFAULT_COMMISSION
        return round(amount * (percentage / 100), 2)

    # -------------------------------
    # SET ACTIVE (IMPORTANT)
    # -------------------------------
    def set_active(self):
        """
        Make this commission the only active one
        """
        # Deactivate all others
        Commission.query.update({Commission.active: False})

        self.active = True
        db.session.commit()

    # -------------------------------
    # VALIDATION (OPTIONAL BUT GOOD)
    # -------------------------------
    def is_valid(self):
        """Basic validation"""
        return 0 <= self.percentage <= 100

    # -------------------------------
    # STRING REPRESENTATION
    # -------------------------------
    def __repr__(self):
        return f"<Commission {self.percentage}% | Active={self.active}>"