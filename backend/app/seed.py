from sqlalchemy import select

from app.auth import password_hasher
from app.config import get_settings
from app.database import SessionLocal
from app.models import User


def seed_users() -> None:
    s = get_settings()
    accounts = [
        (s.admin_username, s.admin_password, "admin"),
        (s.revisor_username, s.revisor_password, "revisor"),
        (s.operador_username, s.operador_password, "operador"),
    ]
    with SessionLocal() as db:
        for username, password, role in accounts:
            if not db.scalar(select(User).where(User.username == username)):
                db.add(User(username=username, password_hash=password_hasher.hash(password), role=role))
        db.commit()


if __name__ == "__main__":
    seed_users()
