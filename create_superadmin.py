from app import create_app, db
from app.models.user import User
from app.models.wallet import Wallet

app = create_app()

with app.app_context():
    db.create_all()
    if not User.query.filter_by(role='superadmin').first():
        superadmin = User(
            username='superadmin',
            email='superadmin@example.com',
            location="Juba",
            role='superadmin',
            active=True,
            is_approved=True
        )
        superadmin.set_password('supersecret')
        superadmin.set_pin('1234')
        
        db.session.add(superadmin)
        db.session.commit()

        wallet = Wallet(user_id=superadmin.id, balance=0)
        db.session.add(wallet)
        db.session.commit()

        print("Superadmin created")
    else:
        print("Superadmin already exists")
