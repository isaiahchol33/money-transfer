from app import create_app, db
from app.models.user import User
from app.models.wallet import Wallet

app = create_app()

with app.app_context():
    db.create_all()

    if not User.query.filter_by(username="admin").first():
        admin = User(
            username="admin",
            email="admin@example.com",  # required!
            location="Juba",
            role="admin",
            active=True,
            is_approved=True
        )
        admin.set_password("admin123")
        admin.set_pin("1230")

        db.session.add(admin)
        db.session.commit()

        wallet = Wallet(user_id=admin.id, balance=1000)
        db.session.add(wallet)
        db.session.commit()

        print("Admin created successfully")
    else:
        print("Admin already exists")
