"""
One-off script to create the first super admin.

Run once after setting up the database:
    python seed.py

It reads FIRST_SUPERADMIN_EMAIL / FIRST_SUPERADMIN_PASSWORD from your .env.
If a super admin with that email already exists, it does nothing.
"""
from sqlmodel import Session, select

from app.config import settings
from app.database import engine, init_db
from app.models import Role, User
from app.security import hash_password


def main() -> None:
    init_db()
    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.email == settings.FIRST_SUPERADMIN_EMAIL)
        ).first()
        if existing:
            print(f"Super admin already exists: {existing.email}")
            return

        admin = User(
            email=settings.FIRST_SUPERADMIN_EMAIL,
            full_name="Super Admin",
            hashed_password=hash_password(settings.FIRST_SUPERADMIN_PASSWORD),
            role=Role.super_admin,
        )
        session.add(admin)
        session.commit()
        print(f"Created super admin: {admin.email}")
        print("Log in at POST /auth/login, then change this password.")


if __name__ == "__main__":
    main()
