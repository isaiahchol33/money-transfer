#app/models/commission.py
from app import db
from datetime import datetime
from app.models.commission import Commission

class Commission(db.Model):
    __tablename__ = "commission"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    percentage = db.Column(db.Float, nullable=False, default=2.0)
    active = db.Column(db.Boolean, default=True)  # ✅ this was missing
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def get_active():
        """Returns the active commission object"""
        return Commission.query.filter_by(active=True).order_by(Commission.created_at.desc()).first()

    @staticmethod
    def calculate_commission(amount):
        rate = Commission.get_active().percentage / 100 if Commission.get_active() else 0.02
        return round(amount * rate, 2)
