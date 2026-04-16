
from app import db
from datetime import datetime


class WalletHistory(db.Model):
    __tablename__ = "wallet_history"

    # ================= PRIMARY =================
    id = db.Column(db.Integer, primary_key=True)

    # ================= RELATIONS =================
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False,
        index=True
    )

    changed_by = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=True,
        index=True
    )

    # ================= BALANCE TRACKING =================
    old_balance = db.Column(db.Float, nullable=False, default=0.0)
    new_balance = db.Column(db.Float, nullable=False, default=0.0)
    amount = db.Column(db.Float, nullable=False, default=0.0)

    # ================= ACTION =================
    action = db.Column(db.String(50), nullable=False, index=True)

    # ================= EXTRA INFO =================
    reference = db.Column(db.String(100), nullable=True, index=True)
    description = db.Column(db.String(255), nullable=True)

    # ================= AUDIT CONTROL =================
    is_deleted = db.Column(db.Boolean, default=False, index=True)   # 🆕 TRASH SYSTEM
    is_locked = db.Column(db.Boolean, default=False)                # 🆕 PROTECT IMPORTANT RECORDS

    # ================= TIMESTAMP =================
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )

    # ================= RELATIONSHIPS =================
    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("wallet_histories", lazy="dynamic")
    )

    admin = db.relationship(
        "User",
        foreign_keys=[changed_by]
    )

    # ================= ACTION TYPES =================
    ACTION_TOPUP = "topup"
    ACTION_TRANSFER = "transfer"
    ACTION_EDIT = "edit"
    ACTION_DEDUCTION = "deduction"
    ACTION_WITHDRAW = "withdraw"
    ACTION_CREDIT = "credit"
    ACTION_DEBIT = "debit"
    ACTION_DELETE = "delete"   # 🆕 NEW
    ACTION_RESTORE = "restore" # 🆕 NEW

    # ================= LOG METHOD =================
    @staticmethod
    def log(
        user_id,
        old_balance,
        new_balance,
        amount,
        action,
        changed_by=None,
        reference=None,
        description=None,
        commit=False
    ):
        history = WalletHistory(
            user_id=user_id,
            changed_by=changed_by,
            old_balance=round(float(old_balance or 0), 2),
            new_balance=round(float(new_balance or 0), 2),
            amount=round(float(amount or 0), 2),
            action=action,
            reference=reference,
            description=description
        )

        db.session.add(history)

        if commit:
            db.session.commit()

        return history

    # ================= SOFT DELETE =================
    def soft_delete(self, commit=True):
        """Move record to trash instead of deleting"""
        self.is_deleted = True
        self.action = self.ACTION_DELETE

        if commit:
            db.session.commit()

    # ================= RESTORE =================
    def restore(self, commit=True):
        """Restore from trash"""
        self.is_deleted = False
        self.action = self.ACTION_RESTORE

        if commit:
            db.session.commit()

    # ================= SERIALIZER =================
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "changed_by": self.changed_by,
            "old_balance": round(self.old_balance or 0, 2),
            "new_balance": round(self.new_balance or 0, 2),
            "amount": round(self.amount or 0, 2),
            "action": self.action,
            "reference": self.reference,
            "description": self.description,
            "is_deleted": self.is_deleted,
            "is_locked": self.is_locked,
            "created_at": (
                self.created_at.strftime("%Y-%m-%d %H:%M")
                if self.created_at else None
            )
        }

    # ================= STRING =================
    def __repr__(self):
        return (
            f"<WalletHistory #{self.id} | User:{self.user_id} | "
            f"{self.action} {self.amount} | "
            f"{self.old_balance}->{self.new_balance} | "
            f"deleted={self.is_deleted}>"
        )