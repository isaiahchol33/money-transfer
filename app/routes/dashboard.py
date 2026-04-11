from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Wallet, Transaction, WalletHistory
from sqlalchemy import func
from datetime import datetime, timedelta

dashboard = Blueprint('dashboard', __name__)


# ================= DASHBOARD HOME =================
@dashboard.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard_home():

    # ---------------- GET OR CREATE WALLET ----------------
    wallet = current_user.get_wallet()

    # ---------------- HANDLE ADMIN TOP-UP ----------------
    if request.method == 'POST' and current_user.role == 'admin':
        topup_amount = request.form.get('topup_amount')

        try:
            amount = float(topup_amount)
            if amount <= 0:
                flash("Enter a valid amount", "danger")
            else:
                old_balance = wallet.balance or 0
                wallet.balance = old_balance + amount

                # SAVE HISTORY
                history = WalletHistory(
                    user_id=current_user.id,
                    changed_by=current_user.id,
                    old_balance=old_balance,
                    new_balance=wallet.balance,
                    amount=amount,
                    action="topup"
                )

                db.session.add(history)
                db.session.commit()

                flash(f"Wallet topped up by {amount:.2f}", "success")
                return redirect(url_for('dashboard.dashboard_home'))

        except (ValueError, TypeError):
            flash("Invalid amount", "danger")
            return redirect(url_for('dashboard.dashboard_home'))

    # ---------------- DATE FILTER ----------------
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') if end_date_str else None

        # include full end day
        if end_date:
            end_date = end_date + timedelta(days=1)

    except ValueError:
        start_date = None
        end_date = None

    # ---------------- BASE QUERY ----------------
    query = Transaction.query

    # Non-admin restriction
    if current_user.role != 'admin':
        query = query.filter(
            (Transaction.sender_cashier_id == current_user.id) |
            (Transaction.receiver_cashier_id == current_user.id)
        )

    # Apply date filters
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date < end_date)

    # ---------------- RECENT TRANSACTIONS ----------------
    transactions = query.order_by(Transaction.date.desc()) \
        .limit(20 if current_user.role == 'admin' else 10) \
        .all()

    # ---------------- AGGREGATE STATS ----------------
    total_transactions = query.count()

    total_amount = query.with_entities(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).scalar()

    total_commission = query.with_entities(
        func.coalesce(func.sum(Transaction.commission), 0)
    ).scalar()

    # ---------------- DASHBOARD RENDER ----------------
    return render_template(
        'dashboard.html',
        wallet=wallet,
        transactions=transactions,
        total_transactions=total_transactions,
        total_amount=round(total_amount or 0, 2),
        total_commission=round(total_commission or 0, 2),
        start_date=start_date_str,
        end_date=end_date_str,
        currency="SSP"
    )


# ================= ANALYTICS (MONTHLY REVENUE) =================
@dashboard.route('/analytics')
@login_required
def analytics():

    query = db.session.query(
        func.strftime('%Y-%m', Transaction.date).label('month'),
        func.sum(func.coalesce(Transaction.amount, 0)).label('total'),
        func.sum(func.coalesce(Transaction.commission, 0)).label('commission')
    )

    # Restrict non-admin users
    if current_user.role != 'admin':
        query = query.filter(
            (Transaction.sender_cashier_id == current_user.id) |
            (Transaction.receiver_cashier_id == current_user.id)
        )

    monthly_data = query.group_by(
        func.strftime('%Y-%m', Transaction.date)
    ).order_by(
        func.strftime('%Y-%m', Transaction.date)
    ).all()

    # Prepare chart data
    months = [m[0] for m in monthly_data]
    totals = [float(m[1] or 0) for m in monthly_data]
    commissions = [float(m[2] or 0) for m in monthly_data]

    return render_template(
        'analytics.html',
        months=months,
        totals=totals,
        commissions=commissions,
        currency="SSP"
    )
