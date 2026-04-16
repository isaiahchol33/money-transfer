import io
from datetime import datetime

import pandas as pd
from xhtml2pdf import pisa

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, send_file, abort, jsonify
)
from flask_login import login_required, current_user
from sqlalchemy import desc, or_, case
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Transaction, User, WalletHistory
from app.models.wallet import Wallet


# =====================================================
# BLUEPRINT
# =====================================================
transfer = Blueprint('transfer', __name__, url_prefix="/transfer")


# =====================================================
# CONFIG
# =====================================================
COMMISSION_RATE = 0.02
STATUS_PENDING = "Pending"
STATUS_PAID = "Paid"


# =====================================================
# HELPERS
# =====================================================
def calculate_commission(amount: float) -> float:
    return round(float(amount) * COMMISSION_RATE, 2)


def ensure_wallet(user):
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet:
        wallet = Wallet(user_id=user.id, balance=0)
        db.session.add(wallet)
        db.session.commit()
    if wallet.balance is None:
        wallet.balance = 0
    return wallet


def log_wallet(user_id, old_balance, new_balance, amount, action):
    try:
        WalletHistory.log(
            user_id=user_id,
            old_balance=old_balance,
            new_balance=new_balance,
            amount=amount,
            action=action,
            changed_by=current_user.id if current_user.is_authenticated else None,
            commit=False
        )
    except Exception:
        pass


def is_valid_name(name: str) -> bool:
    return bool(name) and 2 <= len(name) <= 50 and name.replace(" ", "").isalpha()


def is_valid_phone(phone: str) -> bool:
    return phone.isdigit() and 7 <= len(phone) <= 15


def wants_json():
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
    )


def error_response(message, code=400):
    if wants_json():
        return jsonify({"success": False, "message": message}), code
    flash(message, "danger")
    return redirect(url_for("transfer.transfer_money"))


# =====================================================
# TRANSFER MONEY
# =====================================================
@transfer.route('/', methods=['GET', 'POST'])
@login_required
def transfer_money():

    wallet = ensure_wallet(current_user)

    locations = [
        l[0] for l in db.session.query(User.location).distinct().all()
        if l[0]
    ]

    if request.method == 'POST':
        try:
            if not current_user.check_pin(request.form.get("pin", "")):
                return error_response("Invalid PIN")

            sender_name = request.form.get('sender_name', '').strip()
            sender_phone = request.form.get('sender_phone', '').strip()
            receiver_name = request.form.get('receiver_name', '').strip()
            receiver_phone = request.form.get('receiver_phone', '').strip()
            receiver_location = request.form.get('receiver_location', '').strip()

            try:
                amount = float(request.form.get('amount', 0))
            except:
                return error_response("Invalid amount")

            if not all([
                is_valid_name(sender_name),
                is_valid_name(receiver_name),
                is_valid_phone(sender_phone),
                is_valid_phone(receiver_phone)
            ]):
                return error_response("Invalid input data")

            if amount <= 0:
                return error_response("Amount must be greater than 0")

            commission = calculate_commission(amount)
            total = amount + commission

            wallet = Wallet.query.filter_by(user_id=current_user.id).with_for_update().first()

            if wallet.balance < total:
                return error_response("Insufficient balance")

            old_balance = wallet.balance
            wallet.balance -= total

            tx = Transaction(
                sender_cashier_id=current_user.id,
                sender_cashier_name=current_user.username,
                sender_location=current_user.location,

                sender_name=sender_name,
                sender_phone=sender_phone,

                receiver_name=receiver_name,
                receiver_phone=receiver_phone,
                receiver_location=receiver_location,

                amount=amount,
                commission=commission,
                status=STATUS_PENDING,
                date=datetime.utcnow()
            )

            db.session.add(tx)
            log_wallet(current_user.id, old_balance, wallet.balance, total, "debit")

            db.session.commit()

            flash("Transfer successful", "success")
            return redirect(url_for("transfer.recent_transactions_view"))

        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    return render_template("transfer.html", wallet=wallet, locations=locations)


# =====================================================
# RECENT TRANSACTIONS
# =====================================================
@transfer.route('/transactions')
@login_required
def recent_transactions_view():

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()

    query = Transaction.query.order_by(
        case((Transaction.status == STATUS_PENDING, 0), else_=1),
        desc(Transaction.date)
    )

    if search:
        query = query.filter(
            or_(
                Transaction.sender_name.ilike(f"%{search}%"),
                Transaction.receiver_name.ilike(f"%{search}%"),
                Transaction.receiver_phone.ilike(f"%{search}%")
            )
        )

    transactions = query.paginate(page=page, per_page=10, error_out=False)

    return render_template("recent_transactions.html",
                           transactions=transactions,
                           search=search)


# =====================================================
# EDIT TRANSACTION (FINAL FIX)
# =====================================================
@transfer.route('/edit/<int:transaction_id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(transaction_id):

    tx = Transaction.query.get_or_404(transaction_id)

    role = str(getattr(current_user, "role", "")).lower()

    is_admin = role == "admin"
    is_manager = role == "manager"
    is_sender = current_user.id == tx.sender_cashier_id
    is_receiver = current_user.id == getattr(tx, "receiver_cashier_id", None)

    # ❌ BLOCK receiver
    if is_receiver:
        abort(403)

    if not (is_admin or is_manager or is_sender):
        abort(403)

    if tx.status == STATUS_PAID:
        flash("Cannot edit paid transaction", "warning")
        return redirect(url_for("transfer.recent_transactions_view"))

    if request.method == 'POST':
        try:
            tx.receiver_name = request.form.get('receiver_name', '').strip()
            tx.receiver_phone = request.form.get('receiver_phone', '').strip()
            tx.amount = float(request.form.get('amount', 0))
            tx.commission = calculate_commission(tx.amount)

            db.session.commit()
            flash("Transaction updated", "success")

        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")

        return redirect(url_for("transfer.recent_transactions_view"))

    return render_template("edit_transaction.html", tx=tx)


# =====================================================
# PAY TRANSACTION
# =====================================================
@transfer.route('/pay/<int:transaction_id>', methods=['POST'])
@login_required
def pay_transaction(transaction_id):

    tx = Transaction.query.get_or_404(transaction_id)

    if tx.receiver_location != current_user.location:
        abort(403)

    if tx.status == STATUS_PAID:
        flash("Already paid", "warning")
        return redirect(url_for("transfer.recent_transactions_view"))

    wallet = Wallet.query.filter_by(user_id=current_user.id).with_for_update().first()
    wallet = wallet or ensure_wallet(current_user)

    try:
        old_balance = wallet.balance

        wallet.balance += tx.amount
        tx.status = STATUS_PAID

        log_wallet(current_user.id, old_balance, wallet.balance, tx.amount, "credit")

        db.session.commit()
        flash("Payment successful", "success")

    except Exception:
        db.session.rollback()
        flash("Payment failed", "danger")

    return redirect(url_for("transfer.recent_transactions_view"))


# =====================================================
# EXPORT
# =====================================================
@transfer.route('/export/<file_type>')
@login_required
def export_transactions(file_type):

    transactions = Transaction.query.order_by(desc(Transaction.date)).all()

    if file_type == 'excel':
        df = pd.DataFrame([{
            "Sender": t.sender_name,
            "Receiver": t.receiver_name,
            "Amount": float(t.amount or 0),
            "Commission": float(t.commission or 0),
            "Status": t.status,
            "Date": t.date.strftime("%Y-%m-%d") if t.date else ""
        } for t in transactions])

        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)

        output.seek(0)

        return send_file(output,
                         download_name="transactions.xlsx",
                         as_attachment=True)

    html = render_template("transaction_pd.html", transactions=transactions)

    pdf = io.BytesIO()
    pisa.CreatePDF(html, dest=pdf)

    pdf.seek(0)

    return send_file(pdf,
                     download_name="transactions.pdf",
                     as_attachment=True)