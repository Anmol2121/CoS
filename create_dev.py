# create_dev.py
from app import create_app, db
from models import User
from werkzeug.security import generate_password_hash

def create_developer():
    app = create_app()
    with app.app_context():
        # Check if developer exists
        dev = User.query.filter_by(email='dev@coaching.com').first()
        
        if dev:
            print(f"✅ Developer already exists!")
            print(f"   Email: {dev.email}")
            print("   Password: (the one you set earlier)")
            return
        
        # Create new developer
        dev = User(
            email='dev@coaching.com',
            password_hash=generate_password_hash('devpass123'),
            role='developer',
            is_active=True
        )
        db.session.add(dev)
        db.session.commit()
        
        print("✅ Developer created successfully!")
        print("=" * 40)
        print("Developer Login Credentials:")
        print(f"   Email: dev@coaching.com")
        print(f"   Password: devpass123")
        print("=" * 40)
        print("\n⚠️  IMPORTANT: Change this password after first login!")

if __name__ == '__main__':
    create_developer()