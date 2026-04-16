
from app import db
from datetime import datetime

class Wallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Float, default=0)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)

    user = db.relationship(
        "User",
        back_populates="wallet"
    )