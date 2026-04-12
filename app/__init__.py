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

    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    # Fix Render PostgreSQL URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ---------------- INIT EXTENSIONS ----------------
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"

    # ---------------- IMPORT MODELS ----------------
    from app.models.user import User

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

    # ---------------- HOME ROUTE ----------------
    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.dashboard_home"))
        return render_template("home.html")

    # ---------------- CONTEXT PROCESSOR ----------------
    @app.context_processor
    def inject_currency():
        return dict(currency="SSP")

    # ---------------- ERROR HANDLERS ----------------
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500

    # ---------------- 🔥 TEMP FIX FOR TABLES ----------------
    # This fixes "no such table: user" on Render
    with app.app_context():
        db.create_all()

    return app