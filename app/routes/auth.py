import os
import uuid
import random
import time

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app, session
)

from flask_login import login_user, login_required, current_user, logout_user as flask_logout_user

from app import db
from app.models import User, Wallet


auth = Blueprint('auth', __name__)

# ================= ROLE SECURITY =================
VALID_ROLES = {"user", "supervisor", "manager", "admin"}


def admin_count():
    return User.query.filter_by(role="admin").count()


# =====================================================
# REGISTER
# =====================================================
@auth.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = (request.form.get('username') or "").strip()
        email = (request.form.get('email') or "").strip().lower()
        password = (request.form.get('password') or "").strip()
        confirm_password = (request.form.get('confirm_password') or "").strip()
        pin = (request.form.get('pin') or "").strip()
        location = (request.form.get('location') or "").strip()
        phone_no = (request.form.get('phone_no') or "").strip()
        middle_name = (request.form.get('middle_name') or "").strip()
        role = (request.form.get('role') or "user").strip().lower()

        if not username or not email:
            flash("Username and email are required", "danger")
            return redirect(url_for('auth.register'))

        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return redirect(url_for('auth.register'))

        if not pin.isdigit() or not (4 <= len(pin) <= 6):
            flash("PIN must be 4–6 digits", "danger")
            return redirect(url_for('auth.register'))

        if role not in VALID_ROLES:
            role = "user"

        if role == "admin" and admin_count() >= 2:
            flash("Admin limit reached. Registered as user.", "warning")
            role = "user"

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or email already exists", "danger")
            return redirect(url_for('auth.register'))

        is_approved = role == "admin"
        is_active = role == "admin"

        try:
            user = User(
                username=username,
                email=email,
                middle_name=middle_name,
                location=location,
                phone_no=phone_no,
                role=role,
                active=is_active,
                is_approved=is_approved
            )

            user.set_password(password)
            user.set_pin(pin)

            db.session.add(user)
            db.session.flush()

            db.session.add(Wallet(user_id=user.id, balance=0.0))

            db.session.commit()

            flash(
                "Admin account created" if role == "admin"
                else "Account created. Awaiting approval.",
                "success"
            )

            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Register error: {e}")
            flash("Error creating account", "danger")

    return render_template('register.html')


# =====================================================
# LOGIN (UPDATED SECTION)
# =====================================================
@auth.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = (request.form.get('username') or "").strip()
        password = (request.form.get('password') or "").strip()

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash("Invalid credentials", "danger")
            return redirect(url_for('auth.login'))

        if not user.active:
            flash("Account deactivated", "danger")
            return redirect(url_for('auth.login'))

        if not user.is_approved:
            flash("Account pending approval", "warning")
            return redirect(url_for('auth.login'))

        # ================= LOGIN SUCCESS =================
        login_user(user)
        flash("Login successful", "success")

        # ================= ROLE REDIRECT =================
        if user.role == "admin":
            return redirect(url_for('admin.analytics'))

        elif user.role == "manager":
            return redirect(url_for('manager.manager_dashboard'))

        else:
            return redirect(url_for('dashboard.dashboard_home'))

    return render_template("login.html")


# =====================================================
# LOGOUT
# =====================================================
@auth.route('/logout')
@login_required
def logout():
    flask_logout_user()
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for('home'))


# =====================================================
# PROFILE
# =====================================================
@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():

    if request.method == 'POST':

        current_user.username = (request.form.get('username') or "").strip()
        current_user.location = (request.form.get('location') or "").strip()
        current_user.phone_no = (request.form.get('phone') or "").strip()

        file = request.files.get('profile_image')

        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"

            upload_path = os.path.join(current_app.root_path, 'static/uploads')
            os.makedirs(upload_path, exist_ok=True)

            file.save(os.path.join(upload_path, filename))
            current_user.profile_image = filename

        db.session.commit()
        flash("Profile updated successfully", "success")
        return redirect(url_for("auth.profile"))

    return render_template("edit_profile.html")


# =====================================================
# PIN RESET FLOW (OTP)
# =====================================================
@auth.route('/request-pin-reset', methods=['POST'])
@login_required
def request_pin_reset():

    otp = str(random.randint(100000, 999999))

    session["pin_otp"] = otp
    session["pin_otp_time"] = time.time()

    flash("OTP generated successfully", "success")
    return redirect(url_for("auth.verify_pin_reset"))


@auth.route('/verify-pin-reset', methods=['GET', 'POST'])
@login_required
def verify_pin_reset():

    if request.method == 'POST':

        otp = request.form.get("otp", "").strip()

        if time.time() - session.get("pin_otp_time", 0) > 300:
            flash("OTP expired", "danger")
            return redirect(url_for("auth.request_pin_reset"))

        if session.get("pin_otp") == otp:
            session["pin_verified"] = True
            return redirect(url_for("auth.reset_pin"))

        flash("Invalid OTP", "danger")

    return render_template("verify_pin_reset.html")


@auth.route('/reset-pin', methods=['GET', 'POST'])
@login_required
def reset_pin():

    if not session.get("pin_verified"):
        flash("Unauthorized access", "danger")
        return redirect(url_for("auth.request_pin_reset"))

    if request.method == 'POST':

        new_pin = (request.form.get("pin") or "").strip()

        if not new_pin.isdigit() or not (4 <= len(new_pin) <= 6):
            flash("Invalid PIN format", "danger")
            return redirect(url_for("auth.reset_pin"))

        current_user.set_pin(new_pin)
        db.session.commit()

        session.clear()

        flash("PIN reset successful", "success")
        return redirect(url_for("dashboard.dashboard_home"))

    return render_template("reset_pin.html")


# =====================================================
# FORGOT PASSWORD
# =====================================================
@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():

    if request.method == 'POST':
        flash("Password reset sent (demo only)", "success")
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html')