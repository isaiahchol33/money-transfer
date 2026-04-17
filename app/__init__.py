import os
import logging
from dotenv import load_dotenv

from flask import Flask, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_mail import Mail
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash

# ================= LOAD ENV =================
load_dotenv()

# ================= EXTENSIONS =================
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()

# ================= SOCKETIO =================
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",   # ✅ safe for Render
    ping_timeout=60,
    ping_interval=25
)

# ================= APP FACTORY =================
def create_app():

    app = Flask(__name__)

    # ================= SECURITY =================
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = False
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # ================= DATABASE =================
    db_url = os.environ.get("DATABASE_URL", "sqlite:///database.db")

    # Fix postgres URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }

    # ================= UPLOAD LIMIT =================
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    # ================= MAIL =================
    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"] = True
    app.config["MAIL_USE_SSL"] = False
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER")

    # ================= INIT EXTENSIONS =================
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    csrf.init_app(app)

    socketio.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    # ================= LOGGING =================
    if not app.debug:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s"
        )

    app.logger.info("🚀 App started")

    # ================= MODEL IMPORT =================
    from app.models.user import User

    # ================= USER LOADER =================
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except Exception as e:
            app.logger.error(f"User load failed: {e}")
            return None

    # ================= GLOBAL CONTEXT =================
    @app.context_processor
    def inject_globals():
        def is_admin():
            return current_user.is_authenticated and (
                getattr(current_user, "is_admin", False)
                or str(getattr(current_user, "role", "")).lower() == "admin"
            )

        return {
            "currency": "SSP",
            "is_admin": is_admin
        }

    # ================= BLUEPRINTS =================
    from app.routes.auth import auth
    from app.routes.dashboard import dashboard
    from app.routes.transfer import transfer
    from app.routes.admin import admin
    from app.routes.manager import manager

    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(transfer)
    app.register_blueprint(admin)
    app.register_blueprint(manager)

    # ================= HOME =================
    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.dashboard_home"))
        return render_template("home.html")

    # ================= SECURITY HEADERS =================
    @app.after_request
    def apply_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # ================= ERROR HANDLERS =================
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f"Server Error: {e}")
        return render_template("500.html"), 500

    # ================= DATABASE INIT + ADMIN SEED =================
    with app.app_context():
        try:
            # ✅ Create tables (Postgres + SQLite)
            db.create_all()
            app.logger.info("📦 Database tables ensured")

            # ✅ Create default admin if not exists
            admin_username = os.environ.get("ADMIN_USERNAME", "Superadmin")
            admin_password = os.environ.get("ADMIN_PASSWORD", "admin1991")

            existing_admin = User.query.filter_by(username=admin_username).first()

            if not existing_admin:
                admin_user = User(
                    username=admin_username,
                    password=generate_password_hash(admin_password),
                    role="admin",
                    is_approved=True,
                    active=True
                )

                db.session.add(admin_user)
                db.session.commit()

                app.logger.info("👑 Default admin created")

            else:
                app.logger.info("✅ Admin already exists")

        except Exception as e:
            app.logger.error(f"❌ DB Init Error: {e}")

    return app