#app/models/transaction.py
from app import db
from datetime import datetime

class Transaction(db.Model):
    __tablename__ = "transaction"

    id = db.Column(db.Integer, primary_key=True)

    # ---------- Sender Info ----------
    sender_cashier_id = db.Column(db.Integer, nullable=False)
    sender_cashier_name = db.Column(db.String(100), nullable=False)
    sender_location = db.Column(db.String(100), nullable=True)
    sender_name = db.Column(db.String(100), nullable=False)
    sender_phone = db.Column(db.String(20), nullable=True)




    # ---------- Receiver Info ----------
    
    receiver_cashier_id = db.Column(db.Integer, nullable=True)
    receiver_cashier_name = db.Column(db.String(100), nullable=True)
    receiver_location = db.Column(db.String(100), nullable=True)
    receiver_name = db.Column(db.String(100), nullable=False)
    receiver_phone = db.Column(db.String(20), nullable=True)

    # ---------- Transaction Details ----------
    amount = db.Column(db.Float, nullable=False)
    commission = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='Pending')  # Pending, Completed, Failed
    date = db.Column(db.DateTime, default=datetime.utcnow)

    # ---------- Helper ----------
    def __repr__(self):
        return f"<Transaction {self.id} | {self.sender_name} -> {self.receiver_name} | {self.amount} SSP>"