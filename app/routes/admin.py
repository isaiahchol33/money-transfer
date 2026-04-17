import io
from datetime import datetime

import pandas as pd

from flask import (
    Blueprint, render_template, request,
    abort, send_file, jsonify, redirect, url_for, flash
)

from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import User, Wallet, WalletHistory, Transaction


# =====================================================
# SOCKET SAFE
# =====================================================
try:
    from app.sockets.admin_alerts import send_admin_alert
except Exception:
    def send_admin_alert(message, data=None):
        print("Socket disabled:", message, data)


# =====================================================
# BLUEPRINT
# =====================================================
admin = Blueprint('admin', __name__, url_prefix='/admin')


# =====================================================
# HELPERS
# =====================================================
def is_admin():
    return current_user.is_authenticated and (
        getattr(current_user, "is_admin", False)
        or str(getattr(current_user, "role", "")).lower() == "admin"
    )


def is_manager():
    return str(getattr(current_user, "role", "")).lower() == "manager"


def admin_required():
    if not (is_admin() or is_manager()):
        abort(403)


def ensure_wallet(user):
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet:
        wallet = Wallet(user_id=user.id, balance=0)
        db.session.add(wallet)
        db.session.commit()
    return wallet


def is_ajax():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def json_success(data=None, message="OK"):
    payload = {"success": True, "message": message}
    if data:
        payload["data"] = data
    return jsonify(payload)


def json_error(msg="Error", code=400):
    return jsonify({"success": False, "message": msg}), code


def smart_response(success=True, message="OK", data=None):
    if is_ajax():
        return json_success(data=data, message=message) if success else json_error(message)

    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.users_list"))


# =====================================================
# 🏠 ADMIN DASHBOARD
# =====================================================
@admin.route('/')
@login_required
def admin_dashboard():
    admin_required()

    wallet = ensure_wallet(current_user)
    tx = Transaction.query

    return render_template(
        "admin_dashboard.html",
        wallet=wallet,
        currency="SSP",

        total_transactions=tx.count(),
        total_amount=tx.with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar(),
        total_commission=tx.with_entities(func.coalesce(func.sum(Transaction.commission), 0)).scalar(),

        months=[],
        monthly_amounts=[],
        dates=[],
        counts=[],
        active_names=[],
        active_counts=[],
        locations=[],
        location_counts=[],
        commission_locations=[],
        commission_values=[]
    )


# =====================================================
# USERS
# =====================================================
@admin.route('/users')
@login_required
def users_list():
    admin_required()
    users = User.query.options(joinedload(User.wallet)).all()
    return render_template("users.html", users=users)


@admin.route("/approve/<int:user_id>", methods=["POST"])
@login_required
def approve_user(user_id):
    admin_required()

    user = User.query.get_or_404(user_id)

    try:
        user.is_approved = True
        user.active = True
        db.session.commit()
        return smart_response(True, "User approved")

    except Exception as e:
        db.session.rollback()
        return smart_response(False, str(e))


@admin.route('/users/toggle/<int:user_id>', methods=['POST'])
@login_required
def toggle_user(user_id):
    admin_required()

    user = User.query.get_or_404(user_id)

    try:
        user.active = not bool(user.active)
        db.session.commit()

        status = "activated" if user.active else "deactivated"
        return smart_response(True, f"User {status}")

    except Exception as e:
        db.session.rollback()
        return smart_response(False, str(e))


# =====================================================
# 💰 WALLET TOPUP (LOCKED + SAFE)
# =====================================================
@admin.route('/users/topup/<int:user_id>', methods=['POST'])
@login_required
def topup_wallet(user_id):
    admin_required()

    target_user = User.query.get_or_404(user_id)

    pin = request.form.get("pin", "").strip()

    try:
        amount = float(request.form.get("amount", 0))
    except Exception:
        return json_error("Invalid amount")

    if amount <= 0:
        return json_error("Amount must be greater than 0")

    if not current_user.check_pin(pin):
        return json_error("Invalid PIN", 403)

    try:
        # 🔒 LOCK BOTH WALLETS
        admin_wallet = db.session.query(Wallet)\
            .filter_by(user_id=current_user.id)\
            .with_for_update()\
            .first()

        target_wallet = db.session.query(Wallet)\
            .filter_by(user_id=target_user.id)\
            .with_for_update()\
            .first()

        if not admin_wallet:
            admin_wallet = ensure_wallet(current_user)

        if not target_wallet:
            target_wallet = ensure_wallet(target_user)

        if admin_wallet.balance < amount:
            return json_error("Insufficient admin balance", 403)

        old_balance = float(target_wallet.balance or 0)

        admin_wallet.balance -= amount
        target_wallet.balance += amount

        db.session.add(WalletHistory(
            user_id=target_user.id,
            old_balance=old_balance,
            new_balance=target_wallet.balance,
            amount=amount,
            action="topup",
            changed_by=current_user.id
        ))

        db.session.commit()

        send_admin_alert("Wallet topped up", {"user": target_user.username})

        return json_success({"balance": target_wallet.balance})

    except SQLAlchemyError:
        db.session.rollback()
        return json_error("Database error", 500)


# =====================================================
# 🧾 RECEIPT
# =====================================================
@admin.route('/receipt/<int:tx_id>')
@login_required
def show_receipt(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    return render_template("receipt.html", transaction=tx)


# =====================================================
# WALLET HISTORY
# =====================================================
@admin.route('/wallet-history')
@login_required
def wallet_history():
    admin_required()
    history = WalletHistory.query.order_by(WalletHistory.id.desc()).all()
    return render_template("wallet_history.html", history=history)


@admin.route('/wallet-history/api')
@login_required
def wallet_history_api():
    admin_required()

    logs = WalletHistory.query.order_by(WalletHistory.id.desc()).limit(50).all()

    return jsonify([
        {
            "id": h.id,
            "user": getattr(h.user, "username", "Unknown"),
            "amount": float(h.amount or 0),
            "action": h.action,
            "old_balance": float(h.old_balance or 0),
            "new_balance": float(h.new_balance or 0),
        }
        for h in logs
    ])


# =====================================================
# 📊 ANALYTICS (CROSS-DB SAFE)
# =====================================================
@admin.route("/analytics")
@login_required
def analytics():
    admin_required()

    query = Transaction.query

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if start_date:
        query = query.filter(Transaction.date >= start_date)

    if end_date:
        query = query.filter(Transaction.date <= end_date)

    total_transactions = query.count()

    total_amount = query.with_entities(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).scalar()

    total_commission = query.with_entities(
        func.coalesce(func.sum(Transaction.commission), 0)
    ).scalar()

    total_wallet_balance = db.session.query(
        func.coalesce(func.sum(Wallet.balance), 0)
    ).scalar() or 0

    # ✅ CROSS-DB FIX (no strftime / to_char)
    transactions = query.all()

    monthly_map = {}
    for t in transactions:
        if t.date:
            key = t.date.strftime("%Y-%m")
            monthly_map[key] = monthly_map.get(key, 0) + float(t.amount or 0)

    months = list(monthly_map.keys())
    monthly_amounts = list(monthly_map.values())

    # DAILY
    daily_map = {}
    for t in transactions:
        if t.date:
            key = t.date.strftime("%Y-%m-%d")
            daily_map[key] = daily_map.get(key, 0) + 1

    dates = list(daily_map.keys())
    counts = list(daily_map.values())

    return render_template(
        "analytics.html",
        total_transactions=total_transactions,
        total_amount=float(total_amount or 0),
        total_commission=float(total_commission or 0),
        total_wallet_balance=round(float(total_wallet_balance), 2),

        months=months,
        monthly_amounts=monthly_amounts,
        dates=dates,
        counts=counts,

        active_names=[],
        active_counts=[],
        locations=[],
        location_counts=[],
        commission_locations=[],
        commission_values=[],

        start_date=start_date,
        end_date=end_date
    )


# =====================================================
# 📤 EXPORT
# =====================================================
@admin.route('/download-excel')
@login_required
def download_excel():
    admin_required()

    tx = Transaction.query.all()

    df = pd.DataFrame([{
        "Sender": t.sender_name,
        "Receiver": t.receiver_name,
        "Amount": float(t.amount or 0),
        "Commission": float(t.commission or 0),
        "Status": t.status,
        "Date": t.date.strftime("%Y-%m-%d") if t.date else ""
    } for t in tx])

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return send_file(output, download_name="transactions.xlsx", as_attachment=True)