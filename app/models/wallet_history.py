
from app import db
from datetime import datetime

class WalletHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    old_balance = db.Column(db.Float, default=0)
    new_balance = db.Column(db.Float, default=0)
    amount = db.Column(db.Float, default=0)

    action = db.Column(db.String(50))  # topup / edit / deduction

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    admin = db.relationship('User', foreign_keys=[changed_by])
    def __repr__(self):
        return f"<WalletHistory {self.id} | User {self.user_id} | {self.action} {self.amount} SSP>"

