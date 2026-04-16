from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class User(db.Model, UserMixin):
    __tablename__ = "user"

    # ================= PRIMARY =================
    id = db.Column(db.Integer, primary_key=True)

    # ================= BASIC INFO =================
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    middle_name = db.Column(db.String(100))
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)

    phone_no = db.Column(db.String(20), index=True)
    location = db.Column(db.String(100), index=True)

    profile_image = db.Column(db.String(120), default="avatar.png")

    # ================= AUTH =================
    password = db.Column(db.String(255), nullable=False)
    pin = db.Column(db.String(255))  # hashed PIN

    # ================= SYSTEM =================
    role = db.Column(db.String(20), nullable=False, default="user", index=True)
    active = db.Column(db.Boolean, default=True, index=True)
    is_approved = db.Column(db.Boolean, default=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ================= RELATIONSHIPS =================
    wallet = db.relationship(
        "Wallet",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined"
    )

    # ================= PASSWORD =================
    def set_password(self, password: str):
        if not password:
            raise ValueError("Password cannot be empty")
        self.password = generate_password_hash(password.strip())

    def check_password(self, password: str) -> bool:
        if not self.password:
            return False
        return check_password_hash(self.password, password.strip())

    # ================= PIN =================
    def set_pin(self, pin: str):
        if not pin:
            raise ValueError("PIN is required")

        pin = pin.strip()

        if not pin.isdigit():
            raise ValueError("PIN must contain only digits")

        if not (4 <= len(pin) <= 6):
            raise ValueError("PIN must be 4–6 digits")

        self.pin = generate_password_hash(pin)

    def check_pin(self, pin: str) -> bool:
        if not self.pin or not pin:
            return False
        return check_password_hash(self.pin, pin.strip())

    # ================= ROLE HELPERS =================
    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_manager(self):
        return self.role == "manager"

    @property
    def is_supervisor(self):
        return self.role == "supervisor"

    @property
    def is_user(self):
        return self.role == "user"

    # ================= WALLET (SAFE ACCESS ONLY) =================
    def get_wallet(self):
        """
        SAFE: only returns wallet, does NOT create or commit.
        Wallet creation must be handled in service layer or registration.
        """
        return self.wallet

    # ================= SERIALIZATION =================
    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "phone": self.phone_no,
            "location": self.location,
            "role": self.role,
            "active": self.active,
            "approved": self.is_approved,
            "balance": self.wallet.balance if self.wallet else 0
        }

    # ================= DEBUG =================
    def __repr__(self):
        return f"<User {self.username} ({self.role})>"