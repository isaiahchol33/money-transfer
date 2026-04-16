import io
from datetime import datetime

from flask import (
    Blueprint, render_template, request,
    flash, redirect, url_for, abort
)

from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import User, Transaction, Wallet


# ================= BLUEPRINT =================
manager = Blueprint('manager', __name__, url_prefix='/manager')


# ================= SECURITY =================
def manager_required():
    if not current_user.is_authenticated:
        abort(403)

    if getattr(current_user, "role", "").lower() != "manager":
        abort(403)


def location_guard(user):
    if not current_user.location or not user.location:
        abort(403)

    if user.location != current_user.location:
        abort(403)


def get_wallet(user):
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet:
        wallet = Wallet(user_id=user.id, balance=0.0)
        db.session.add(wallet)
        db.session.flush()
    return wallet


# ================= DASHBOARD =================
@manager.route('/dashboard')
@login_required
def manager_dashboard():
    manager_required()

    search = request.args.get("search", "").strip()

    query = User.query.filter(
        User.location == current_user.location,
        User.id != current_user.id
    )

    if search:
        query = query.filter(User.username.ilike(f"%{search}%"))

    users = query.order_by(User.id.desc()).all()

    return render_template(
        "manager_panel.html",
        users=users,
        search=search
    )


# ================= TOGGLE USER =================
@manager.route('/user/toggle/<int:user_id>', methods=['POST'])
@login_required
def toggle_user(user_id):
    manager_required()

    user = User.query.get_or_404(user_id)
    location_guard(user)

    if user.role == "admin":
        flash("Cannot modify admin user", "danger")
        return redirect(url_for('manager.manager_dashboard'))

    user.active = not bool(user.active)
    db.session.commit()

    flash("User status updated", "success")
    return redirect(url_for('manager.manager_dashboard'))


# ================= APPROVE USER =================
@manager.route('/user/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    manager_required()

    user = User.query.get_or_404(user_id)
    location_guard(user)

    if user.role == "admin":
        flash("Cannot approve admin", "danger")
        return redirect(url_for('manager.manager_dashboard'))

    user.is_approved = True
    user.active = True

    db.session.commit()

    flash(f"{user.username} approved successfully", "success")
    return redirect(url_for('manager.manager_dashboard'))


# ================= CHANGE ROLE =================
@manager.route('/user/role/<int:user_id>', methods=['POST'])
@login_required
def change_user_role(user_id):
    manager_required()

    user = User.query.get_or_404(user_id)
    location_guard(user)

    new_role = (request.form.get("role") or "").strip().lower()

    ALLOWED_ROLES = {"user", "supervisor"}

    if new_role not in ALLOWED_ROLES:
        flash("Invalid role selected", "danger")
        return redirect(url_for('manager.manager_dashboard'))

    if user.role == "admin":
        flash("Cannot modify admin role", "danger")
        return redirect(url_for('manager.manager_dashboard'))

    user.role = new_role
    db.session.commit()

    flash(f"Role updated to {new_role}", "success")
    return redirect(url_for('manager.manager_dashboard'))


# ================= WALLET TOP-UP (MANAGER TRANSFER) =================
@manager.route('/user/topup/<int:user_id>', methods=['POST'])
@login_required
def manager_topup(user_id):
    manager_required()

    user = User.query.get_or_404(user_id)
    location_guard(user)

    pin = (request.form.get("pin") or "").strip()

    try:
        amount = float(request.form.get("amount", 0))
    except ValueError:
        flash("Invalid amount", "danger")
        return redirect(url_for('manager.manager_dashboard'))

    if amount <= 0:
        flash("Amount must be greater than 0", "danger")
        return redirect(url_for('manager.manager_dashboard'))

    if not current_user.check_pin(pin):
        flash("Invalid PIN", "danger")
        return redirect(url_for('manager.manager_dashboard'))

    try:
        # ================= LOCK WALLETS =================
        manager_wallet = db.session.query(Wallet).filter_by(
            user_id=current_user.id
        ).with_for_update().first()

        receiver_wallet = db.session.query(Wallet).filter_by(
            user_id=user.id
        ).with_for_update().first()

        if not manager_wallet:
            manager_wallet = get_wallet(current_user)

        if not receiver_wallet:
            receiver_wallet = get_wallet(user)

        if manager_wallet.balance < amount:
            flash("Insufficient balance", "danger")
            return redirect(url_for('manager.manager_dashboard'))

        # ================= TRANSFER =================
        old_manager_balance = manager_wallet.balance

        manager_wallet.balance -= amount
        receiver_wallet.balance += amount

        tx = Transaction(
            sender_cashier_id=current_user.id,
            sender_cashier_name=current_user.username,
            sender_location=current_user.location,

            sender_name=current_user.username,
            sender_phone=getattr(current_user, "phone_no", ""),

            receiver_cashier_id=user.id,
            receiver_cashier_name=user.username,
            receiver_location=user.location,

            receiver_name=user.username,
            receiver_phone=getattr(user, "phone_no", ""),

            amount=amount,
            commission=0,
            status="Completed",
            date=datetime.utcnow()
        )

        db.session.add(tx)

        db.session.commit()

        flash(f"Successfully sent {amount:.2f} SSP to {user.username}", "success")
        return redirect(url_for('manager.manager_dashboard'))

    except SQLAlchemyError as e:
        db.session.rollback()
        flash("Database error occurred", "danger")
        return redirect(url_for('manager.manager_dashboard'))

    except Exception as e:
        db.session.rollback()
        flash("Unexpected error occurred", "danger")
        return redirect(url_for('manager.manager_dashboard'))