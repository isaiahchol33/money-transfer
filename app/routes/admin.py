# app/routes/admin.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, abort, send_file, current_app
from flask_login import login_required, current_user
from app import db
from app.models import User, Wallet, WalletHistory, Transaction
from sqlalchemy import func
from datetime import datetime
import pandas as pd
import io

admin = Blueprint('admin', __name__, url_prefix='/admin')


# ================= SECURITY =================
def admin_required():
    if not current_user.is_authenticated or not getattr(current_user, "is_admin", False):
        abort(403)


# ================= AUTO WALLET =================
@admin.before_app_request
def ensure_wallet():
    if current_user.is_authenticated and hasattr(current_user, "get_wallet"):
        current_user.get_wallet()


# ================= DB DATE HELPERS =================
def month_group():
    if current_app.config['SQLALCHEMY_DATABASE_URI'].startswith("sqlite"):
        return func.strftime('%Y-%m', Transaction.date)
    return func.date_trunc('month', Transaction.date)


def day_group():
    if current_app.config['SQLALCHEMY_DATABASE_URI'].startswith("sqlite"):
        return func.strftime('%Y-%m-%d', Transaction.date)
    return func.date_trunc('day', Transaction.date)


# ================= ANALYTICS =================
@admin.route('/analytics')
@login_required
def analytics():
    admin_required()

    total_users = db.session.query(func.count(User.id)).scalar()
    total_transactions = db.session.query(func.count(Transaction.id)).scalar()

    total_amount, total_commission = db.session.query(
        func.coalesce(func.sum(Transaction.amount), 0),
        func.coalesce(func.sum(Transaction.commission), 0)
    ).first()

    total_wallet_balance = db.session.query(
        func.coalesce(func.sum(Wallet.balance), 0)
    ).scalar()

    # MONTHLY
    m_group = month_group()
    monthly_data = db.session.query(
        m_group,
        func.coalesce(func.sum(Transaction.amount), 0)
    ).group_by(m_group).order_by(m_group).all()

    months = [str(m)[:7] for m, _ in monthly_data]
    monthly_amounts = [float(v) for _, v in monthly_data]

    # DAILY
    d_group = day_group()
    daily_data = db.session.query(
        d_group,
        func.count(Transaction.id)
    ).group_by(d_group).order_by(d_group).all()

    dates = [str(d)[:10] for d, _ in daily_data]
    counts = [c for _, c in daily_data]

    # TOP USERS
    active_users = db.session.query(
        User.username,
        func.count(Transaction.id)
    ).join(Transaction, Transaction.sender_cashier_id == User.id)\
     .group_by(User.username)\
     .order_by(func.count(Transaction.id).desc())\
     .limit(5).all()

    active_names = [u for u, _ in active_users]
    active_counts = [c for _, c in active_users]

    # LOCATION
    location_data = db.session.query(
        Transaction.receiver_location,
        func.count(Transaction.id)
    ).group_by(Transaction.receiver_location).all()

    locations = [l or "Unknown" for l, _ in location_data]
    location_counts = [c for _, c in location_data]

    commission_data = db.session.query(
        Transaction.receiver_location,
        func.coalesce(func.sum(Transaction.commission), 0)
    ).group_by(Transaction.receiver_location).all()

    commission_locations = [l or "Unknown" for l, _ in commission_data]
    commission_values = [float(v) for _, v in commission_data]

    return render_template(
        "analytics.html",
        total_users=total_users,
        total_transactions=total_transactions,
        total_amount=float(total_amount),
        total_commission=float(total_commission),
        total_wallet_balance=float(total_wallet_balance),
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
        currency="SSP"
    )


# ================= USERS =================
@admin.route('/users')
@login_required
def users_list():
    admin_required()

    selected_location = request.args.get("location")

    query = User.query.options(db.joinedload(User.wallet))

    if selected_location:
        query = query.filter(User.location == selected_location)

    users = query.order_by(User.active.desc(), User.is_approved.asc()).all()

    locations = [
        l[0] for l in db.session.query(User.location).distinct().all() if l[0]
    ]

    location_stats = dict(
        db.session.query(User.location, func.count(User.id))
        .filter(User.location.isnot(None))
        .group_by(User.location)
        .all()
    )

    return render_template(
        "users.html",
        users=users,
        locations=locations,
        selected_location=selected_location,
        location_stats=location_stats
    )


# ================= APPROVE =================
@admin.route('/users/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    admin_required()

    user = User.query.get_or_404(user_id)

    if user.is_admin:
        return redirect(url_for('admin.users_list'))

    user.is_approved = True
    user.active = True
    db.session.commit()

    flash(f"{user.username} approved", "success")
    return redirect(url_for('admin.users_list'))


# ================= TOGGLE =================
@admin.route('/users/toggle/<int:user_id>', methods=['POST'])
@login_required
def toggle_user(user_id):
    admin_required()

    user = User.query.get_or_404(user_id)

    if user.is_admin and not current_user.is_admin:
        flash("Cannot modify admin", "danger")
        return redirect(url_for('admin.users_list'))

    user.active = not user.active
    db.session.commit()

    flash("User status updated", "success")
    return redirect(url_for('admin.users_list'))


# ================= TOPUP =================
@admin.route('/users/topup/<int:user_id>', methods=['POST'])
@login_required
def topup_wallet(user_id):
    admin_required()

    user = User.query.get_or_404(user_id)

    try:
        amount = float(request.form.get("amount", 0))
        if amount <= 0:
            raise ValueError
    except:
        return jsonify({"success": False, "error": "Invalid amount"}), 400

    try:
        admin_wallet = current_user.get_wallet()
        target_wallet = user.get_wallet()

        if user.id == current_user.id:
            admin_wallet.balance += amount
        else:
            if admin_wallet.balance < amount:
                return jsonify({"success": False, "error": "Insufficient balance"}), 400

            admin_wallet.balance -= amount
            target_wallet.balance += amount

        db.session.add(WalletHistory(
            user_id=user.id,
            changed_by=current_user.id,
            amount=amount,
            action="topup",
            created_at=datetime.utcnow()
        ))

        db.session.commit()

        return jsonify({
            "success": True,
            "user_balance": target_wallet.balance,
            "admin_balance": admin_wallet.balance
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# ================= WALLET HISTORY =================
@admin.route('/wallet-history')
@login_required
def wallet_history():
    admin_required()

    search = request.args.get("user")

    query = WalletHistory.query

    if search:
        query = query.join(User).filter(User.username.ilike(f"%{search}%"))

    history = query.order_by(WalletHistory.id.desc()).all()

    return render_template("wallet_history.html", history=history)


# ================= DELETE HISTORY =================
@admin.route('/wallet-history/delete/<int:id>', methods=['POST'])
@login_required
def delete_wallet_history(id):
    admin_required()

    history = WalletHistory.query.get_or_404(id)

    if history.action == "transfer":
        flash("Protected record cannot be deleted", "danger")
        return redirect(url_for("admin.wallet_history"))

    db.session.delete(history)
    db.session.commit()

    flash("Record deleted", "success")
    return redirect(url_for("admin.wallet_history"))


# ================= EXPORT =================
@admin.route('/download-excel')
@login_required
def download_excel():
    admin_required()

    transactions = Transaction.query.all()

    data = [{
        "Sender": t.sender_name,
        "Receiver": t.receiver_name,
        "Amount": float(t.amount or 0),
        "Commission": float(t.commission or 0),
        "Status": t.status,
        "Date": t.date.strftime("%Y-%m-%d") if t.date else ""
    } for t in transactions]

    df = pd.DataFrame(data)

    output = io.BytesIO()
    df.to_excel(output, index=False, engine="openpyxl")
    output.seek(0)

    return send_file(output, download_name="transactions.xlsx", as_attachment=True)


# ================= RECEIPT =================
@admin.route('/receipt/<int:tx_id>')
@login_required
def show_receipt(tx_id):
    admin_required()

    t = Transaction.query.get_or_404(tx_id)

    return render_template("receipt.html", transaction=t, currency="SSP")