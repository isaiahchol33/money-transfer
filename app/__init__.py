from flask import Flask, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from dotenv import load_dotenv
import os

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def create_app():
    app = Flask(__name__)

    # ---------------- CONFIG ----------------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")

    db_url = os.environ.get("DATABASE_URL")

    # ✅ LOCAL fallback
    if not db_url:
        db_url = "sqlite:///database.db"

    # Fix postgres URL (Render)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ✅ DATABASE PERFORMANCE
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True
    }

    # ---------------- INIT ----------------
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"

    # ---------------- IMPORT MODELS ----------------
    from app.models.user import User

    # ---------------- SAFE DB INIT ----------------
    def initialize_database():
        with app.app_context():
            db.create_all()

    # Run once at startup
    initialize_database()

    # ---------------- USER LOADER ----------------
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ---------------- BLUEPRINTS ----------------
    from app.routes.auth import auth
    from app.routes.dashboard import dashboard
    from app.routes.transfer import transfer

    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(transfer)

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

    # ---------------- ERRORS ----------------
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500

    return app