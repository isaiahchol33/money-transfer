from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort
from flask_login import login_required, current_user
from sqlalchemy import desc, or_, distinct
from app import db
from app.models import Transaction, User, Wallet, WalletHistory
from datetime import datetime
import io
import pandas as pd
from xhtml2pdf import pisa

transfer = Blueprint('transfer', __name__)

# =========================
# CONFIG
# =========================
COMMISSION_RATE = 0.02


# =========================
# HELPERS
# =========================
def calculate_commission(amount: float) -> float:
    return round(amount * COMMISSION_RATE, 2)


def ensure_wallet(user):
    """Ensure wallet exists"""
    if not user.wallet:
        wallet = Wallet(user_id=user.id, balance=0)
        db.session.add(wallet)
        db.session.commit()
        return wallet
    return user.wallet

def commit_wallet_history(user_id, amount, action):
    db.session.add(WalletHistory(
        user_id=user_id,
        changed_by=current_user.id if current_user.is_authenticated else 0,
        amount=amount,
        action=action,
        created_at=datetime.utcnow()
    ))


# =========================
# TRANSFER MONEY
# =========================
@transfer.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer_money():
    wallet = ensure_wallet(current_user)

    locations = [
        loc[0] for loc in db.session.query(distinct(User.location))
        .filter(User.location.isnot(None)).all()
    ]

    form_data = request.form if request.method == 'POST' else None

    if request.method == 'POST':
        try:
            sender_name = request.form.get('sender_name', '').strip()
            sender_phone = request.form.get('sender_phone', '').strip()
            receiver_name = request.form.get('receiver_name', '').strip()
            receiver_phone = request.form.get('receiver_phone', '').strip()
            receiver_location = request.form.get('receiver_location', '').strip()
            amount = float(request.form.get('amount', 0))

            # VALIDATION
            if not sender_name.replace(' ', '').isalpha():
                raise ValueError("Invalid sender name")

            if not receiver_name.replace(' ', '').isalpha():
                raise ValueError("Invalid receiver name")

            if not sender_phone.isdigit() or not receiver_phone.isdigit():
                raise ValueError("Invalid phone number")

            if not receiver_location:
                raise ValueError("Receiver location required")

            if amount <= 0:
                raise ValueError("Amount must be greater than 0")

            commission = calculate_commission(amount)
            total = amount + commission

            if wallet.balance < total:
                raise ValueError("Insufficient balance")

            # TRANSACTION
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
                status="Pending",
                date=datetime.utcnow()
            )

            db.session.add(tx)
            commit_wallet_history(current_user.id, total, "Debit")

            db.session.commit()

            flash("Transfer successful", "success")
            return redirect(url_for('transfer.recent_transactions_view'))

        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")

    return render_template(
        "transfer.html",
        wallet=wallet,
        locations=locations,
        form_data=form_data
    )


# =========================
# RECENT TRANSACTIONS
# =========================
@transfer.route('/transactions')
@login_required
def recent_transactions_view():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()

    query = Transaction.query.order_by(desc(Transaction.date))

    if search:
        query = query.filter(
            or_(
                Transaction.sender_name.ilike(f"%{search}%"),
                Transaction.receiver_name.ilike(f"%{search}%"),
                Transaction.receiver_phone.ilike(f"%{search}%")
            )
        )

    transactions = query.paginate(page=page, per_page=10)

    return render_template(
        'recent_transactions.html',
        transactions=transactions,
        search=search
    )


# =========================
# PAY TRANSACTION
# =========================
@transfer.route('/pay/<int:transaction_id>', methods=['POST'])
@login_required
def pay_transaction(transaction_id):
    tx = Transaction.query.get_or_404(transaction_id)

    if tx.receiver_location != current_user.location:
        abort(403)

    if tx.status == "Paid":
        flash("Already paid", "warning")
        return redirect(url_for('transfer.recent_transactions_view'))

    try:
        wallet = ensure_wallet(current_user)

        wallet.balance += tx.amount
        tx.status = "Paid"

        commit_wallet_history(current_user.id, tx.amount, "Credit")

        db.session.commit()

        flash("Payment completed", "success")

    except Exception:
        db.session.rollback()
        flash("Payment failed", "danger")

    return redirect(url_for('transfer.recent_transactions_view'))


# =========================
# EDIT TRANSACTION
# =========================
@transfer.route('/edit-transaction/<int:transaction_id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(transaction_id):
    tx = Transaction.query.get_or_404(transaction_id)

    if current_user.id != tx.sender_cashier_id and current_user.role != 'admin':
        abort(403)

    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount'))

            if amount <= 0:
                raise ValueError("Invalid amount")

            tx.receiver_name = request.form.get('receiver_name', '').strip()
            tx.receiver_phone = request.form.get('receiver_phone', '').strip()

            tx.amount = amount
            tx.commission = calculate_commission(amount)

            db.session.commit()
            flash("Transaction updated", "success")

        except Exception as e:
            flash(str(e), "danger")

        return redirect(url_for('transfer.recent_transactions_view'))

    return render_template("edit_transaction.html", transaction=tx)


# =========================
# MANAGER DASHBOARD
# =========================
@transfer.route('/manager-dashboard')
@login_required
def manager_dashboard():
    if not current_user.is_manager:
        abort(403)

    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)

    users_query = User.query.filter(User.location == current_user.location)

    if search:
        users_query = users_query.filter(
            or_(
                User.username.ilike(f"%{search}%"),
                User.phone_no.ilike(f"%{search}%")
            )
        )

    users = users_query.order_by(User.username).all()

    tx_query = Transaction.query.filter(
        Transaction.receiver_location == current_user.location
    )

    if search:
        tx_query = tx_query.filter(
            or_(
                Transaction.sender_name.ilike(f"%{search}%"),
                Transaction.receiver_name.ilike(f"%{search}%"),
                Transaction.receiver_phone.ilike(f"%{search}%")
            )
        )

    transactions = tx_query.order_by(desc(Transaction.date)).paginate(
        page=page,
        per_page=10
    )

    return render_template(
        'manager_dashboard.html',
        users=users,
        transactions=transactions,
        search=search
    )


# =========================
# TOPUP WALLET
# =========================
@transfer.route('/topup-wallet/<int:user_id>', methods=['POST'])
@login_required
def topup_wallet(user_id):
    if not current_user.is_manager:
        abort(403)

    if user_id == current_user.id:
        flash("Not allowed", "danger")
        return redirect(url_for('transfer.manager_dashboard'))

    user = User.query.get_or_404(user_id)
    wallet = ensure_wallet(user)

    try:
        amount = float(request.form.get('amount', 0))

        if amount <= 0:
            raise ValueError("Invalid amount")

        wallet.balance += amount
        commit_wallet_history(user.id, amount, "Credit")

        db.session.commit()

        flash("Wallet topped up successfully", "success")

    except Exception as e:
        db.session.rollback()
        flash(str(e), "danger")

    return redirect(url_for('transfer.manager_dashboard'))


# =========================
# USER MANAGEMENT
# =========================
@transfer.route('/approve-user/<int:user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    if not current_user.is_manager:
        abort(403)

    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()

    flash("User approved", "success")
    return redirect(url_for('transfer.manager_dashboard'))


@transfer.route('/activate-user/<int:user_id>', methods=['POST'])
@login_required
def activate_user(user_id):
    if not current_user.is_manager:
        abort(403)

    user = User.query.get_or_404(user_id)
    user.active = True
    db.session.commit()

    flash("User activated", "success")
    return redirect(url_for('transfer.manager_dashboard'))


@transfer.route('/deactivate-user/<int:user_id>', methods=['POST'])
@login_required
def deactivate_user(user_id):
    if not current_user.is_manager:
        abort(403)

    user = User.query.get_or_404(user_id)
    user.active = False
    db.session.commit()

    flash("User deactivated", "success")
    return redirect(url_for('transfer.manager_dashboard'))


# =========================
# EXPORT
# =========================
@transfer.route('/export-transactions/<file_type>')
@login_required
def export_transactions(file_type):
    if file_type not in ['excel', 'pdf']:
        abort(400)

    transactions = Transaction.query.order_by(desc(Transaction.date)).all()

    if file_type == 'excel':
        df = pd.DataFrame([{
            "Sender": t.sender_name,
            "Receiver": t.receiver_name,
            "Amount": t.amount,
            "Status": t.status
        } for t in transactions])

        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)

        output.seek(0)

        return send_file(output, download_name="transactions.xlsx", as_attachment=True)

    html = render_template('transactions_pdf.html', transactions=transactions)
    pdf = io.BytesIO()

    pisa.CreatePDF(io.StringIO(html), dest=pdf)

    pdf.seek(0)

    return send_file(pdf, download_name="transactions.pdf", as_attachment=True)


