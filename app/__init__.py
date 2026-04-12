from flask import Flask, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
import os

# Load env
load_dotenv()

# Extensions
db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)

    # ---------------- CONFIG ----------------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    # Fix Render PostgreSQL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Uploads
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static/uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ---------------- INIT EXTENSIONS ----------------
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # ---------------- IMPORT MODEL ----------------
    from app.models.user import User

    # ---------------- USER LOADER ----------------
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ---------------- BLUEPRINTS ----------------
    from app.routes.auth import auth
    from app.routes.dashboard import dashboard
    from app.routes.transfer import transfer
    from app.routes.admin import admin

    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(transfer)
    app.register_blueprint(admin)

    # ---------------- HOME ----------------
    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.dashboard_home"))
        return render_template("home.html")

    # ---------------- CONTEXT ----------------
    @app.context_processor
    def inject_currency():
        return dict(currency="SSP")

    # ---------------- ADMIN SEED ----------------
    def seed_admin():
        admin_user = User.query.filter_by(username="admin").first()

        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@example.com",
                password=generate_password_hash("admin1234"),
                role="admin",
                is_approved=True,
                active=True,
            )
            db.session.add(admin_user)
            db.session.commit()
            print("✅ Admin created")

    # ---------------- SAFE INIT (IMPORTANT FIX) ----------------
    @app.before_request
    def initialize_once():
        if getattr(app, "_db_ready", False):
            return

        with app.app_context():
            db.create_all()   # ONLY FOR FIRST DEPLOY (no migrations)
            seed_admin()

        app._db_ready = True

    # ---------------- ERRORS ----------------
    @app.errorhandler(404)
    def not_found(error):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template("500.html"), 500

    return app