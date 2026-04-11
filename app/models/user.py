from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .wallet import Wallet
from .transaction import Transaction
from .currency import Currency


class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    middle_name = db.Column(db.String(100))
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    pin = db.Column(db.String(200))
    location = db.Column(db.String(100))
    phone_no = db.Column(db.String(20))

    # Role and active status
    role = db.Column(db.String(20), nullable=False, default='user')  # admin, manager, supervisor, user
    active = db.Column(db.Boolean, default=True)  # active/inactive
    is_approved = db.Column(db.Boolean, default=False)  # approval required
    profile_image = db.Column(db.String(120), default='avatar.png')

    # One-to-one relationship with Wallet
    wallet = db.relationship('Wallet', backref='user', uselist=False)

    # ---------- PASSWORD ----------
    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    # ---------- PIN ----------
    def set_pin(self, pin):
        self.pin = generate_password_hash(pin)

    def check_pin(self, pin):
        return check_password_hash(self.pin, pin)

    # ---------- ROLE PROPERTIES ----------
    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_manager(self):
        return self.role == 'manager'

    @property
    def is_supervisor(self):
        return self.role == 'supervisor'

    @property
    def is_user(self):
        return self.role == 'user'

    @property
    def is_active(self):
        return self.active

    # ---------- APPROVAL HELPER ----------
    def can_approve(self, other_user):
        """
        Returns True if this user can approve the given other_user.
        """
        if self.is_admin:
            return True
        if self.is_manager and other_user.role in ['supervisor', 'user']:
            return True
        return False

    # ---------- WALLET HELPER ----------
    def get_wallet(self):
        """
        Returns the user's wallet. Creates one if it doesn't exist.
        """
        if not self.wallet:
            self.wallet = Wallet(user_id=self.id, balance=0)
            db.session.add(self.wallet)
            db.session.commit()
        return self.wallet

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
