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

    wallet = Wallet.query.filter_by(user_id=current_user.id).first()
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
# WALLET TOPUP
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
        target_wallet = Wallet.query.filter_by(user_id=target_user.id).first()
        admin_wallet = Wallet.query.filter_by(user_id=current_user.id).first()

        if not target_wallet or not admin_wallet:
            return json_error("Wallet not found", 404)

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
# 🧾 RECEIPT (UPDATED: ALL USERS ALLOWED)
# =====================================================
@admin.route('/receipt/<int:tx_id>')
@login_required
def show_receipt(tx_id):

    tx = Transaction.query.get_or_404(tx_id)

    # ✅ Allow ALL authenticated users
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
# ANALYTICS
# =====================================================
@admin.route("/analytics")
@login_required
def analytics():
    admin_required()

    query = Transaction.query

    # ================= DATE FILTER =================
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if start_date:
        query = query.filter(Transaction.date >= start_date)

    if end_date:
        query = query.filter(Transaction.date <= end_date)

    # ================= TOTALS =================
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

    # ================= MONTHLY =================
    monthly = query.with_entities(
        func.strftime("%Y-%m", Transaction.date),
        func.sum(Transaction.amount)
    ).group_by(func.strftime("%Y-%m", Transaction.date)).all()

    months = [m[0] for m in monthly]
    monthly_amounts = [float(m[1]) for m in monthly]

    # ================= DAILY =================
    daily = query.with_entities(
        func.date(Transaction.date),
        func.count(Transaction.id)
    ).group_by(func.date(Transaction.date)).all()

    dates = [str(d[0]) for d in daily]
    counts = [d[1] for d in daily]

    # ================= TOP USERS =================
    users = query.with_entities(
        Transaction.sender_cashier_name,
        func.count(Transaction.id)
    ).group_by(Transaction.sender_cashier_name)\
     .order_by(func.count(Transaction.id).desc())\
     .limit(5).all()

    active_names = [u[0] for u in users]
    active_counts = [u[1] for u in users]

    # ================= LOCATIONS =================
    locs = query.with_entities(
        Transaction.receiver_location,
        func.count(Transaction.id)
    ).group_by(Transaction.receiver_location).all()

    locations = [l[0] for l in locs]
    location_counts = [l[1] for l in locs]

    # ================= COMMISSION =================
    comm = query.with_entities(
        Transaction.receiver_location,
        func.sum(Transaction.commission)
    ).group_by(Transaction.receiver_location).all()

    commission_locations = [c[0] for c in comm]
    commission_values = [float(c[1] or 0) for c in comm]

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
        active_names=active_names,
        active_counts=active_counts,
        locations=locations,
        location_counts=location_counts,
        commission_locations=commission_locations,
        commission_values=commission_values,

        start_date=start_date,
        end_date=end_date
    )


# =====================================================
# EXPORT
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