
#app/routes/auth.py
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, login_required, current_user
from flask_login import logout_user as flask_logout_user
from werkzeug.utils import secure_filename
from app import db
from app.models import User, Wallet, WalletHistory, Transaction

auth = Blueprint('auth', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ------------------------
# Register Route
# ------------------------
@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        email = request.form.get('email').strip()
        password = request.form.get('password').strip()
        confirm_password = request.form.get('confirm_password').strip()
        pin = request.form.get('pin').strip()
        location = request.form.get('location').strip()
        phone_no = request.form.get('phone_no').strip()
        middle_name = request.form.get('middle_name').strip()
        role = request.form.get('role').strip()

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.register'))

        if not pin or len(pin) < 4:
            flash("PIN must be at least 4 digits", "danger")
            return redirect(url_for('auth.register'))

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('auth.register'))

        # ----------------- ACTIVE & APPROVAL STATUS -----------------
        # Admins are automatically active & approved
        is_active = True if role == 'admin' else False
        is_approved = True if role == 'admin' else False

        new_user = User(
            username=username,
            email=email,
            middle_name=middle_name,
            location=location,
            phone_no=phone_no,
            role=role,
            active=is_active,
            is_approved=is_approved
        )
        new_user.set_password(password)
        new_user.set_pin(pin)

        db.session.add(new_user)
        db.session.commit()

        # Create wallet automatically
        wallet = Wallet(user_id=new_user.id, balance=0)
        db.session.add(wallet)
        db.session.commit()

        if role == 'admin':
            flash('Admin account created and active!', 'success')
        else:
            flash('Account created! Awaiting admin approval.', 'info')

        return redirect(url_for('auth.login'))

    return render_template('register.html')


# ---------------- PROFILE ----------------
@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        updated = False  # track if any changes were made

        # ----------------- PROFILE IMAGE -----------------
        file = request.files.get('profile_image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_folder = os.path.join(current_app.static_folder, 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            current_user.profile_image = filename
            updated = True

        # ----------------- USERNAME -----------------
        new_username = request.form.get('username', '').strip()
        if new_username and new_username != current_user.username:
            # Check if username already exists
            if User.query.filter(User.username == new_username, User.id != current_user.id).first():
                flash("Username already taken.", "danger")
                return redirect(url_for('auth.profile'))
            current_user.username = new_username
            updated = True

        # ----------------- LOCATION -----------------
        new_location = request.form.get('location', '').strip()
        if new_location != current_user.location:
            current_user.location = new_location
            updated = True

        if updated:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        else:
            flash('No changes made.', 'info')

        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', user=current_user)


# ---------------- LOGIN ----------------
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash("Invalid username or password", "danger")
            return redirect(url_for('auth.login'))

        if not user.active:
            flash("Account is deactivated", "danger")
            return redirect(url_for('auth.login'))

        if not user.is_approved:
            flash("Account pending admin approval.", "warning")
            return redirect(url_for('auth.login'))

        login_user(user)
        flash("Login successful", "success")

        # ROLE-BASED REDIRECT
        if user.role == 'admin':
            return redirect(url_for('admin.analytics'))
        return redirect(url_for('dashboard.dashboard_home'))

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@auth.route('/logout')
@login_required
def logout():
    flask_logout_user()
    flash('Logged out successfully', 'info')
    return redirect(url_for('home'))


# ---------------- FORGOT PASSWORD ----------------
@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        flash('Password reset link sent to your email.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('forgot_password.html')


#app/routes/dashboard.py
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
