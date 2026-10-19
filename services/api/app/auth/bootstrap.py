from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from services.api.app.infra.db import SessionLocal
from services.api.app.infra.settings import settings
from shared.db.models import RegisteredAccount, User
from shared.security import hash_password


def ensure_default_admin_account() -> None:
    with SessionLocal() as db:
        account = db.scalar(select(RegisteredAccount).where(RegisteredAccount.username == "admin"))
        if account is not None:
            if account.id != "admin":
                raise RuntimeError("The reserved username 'admin' belongs to a different account ID")
            return

        now = datetime.now(timezone.utc)
        if db.get(User, "admin") is None:
            db.add(User(id="admin", display_name="Administrator", created_at=now))
            db.flush()
        db.add(
            RegisteredAccount(
                id="admin",
                email=settings.admin_email,
                username="admin",
                password_hash=hash_password(settings.admin_initial_password),
                must_change_password=True,
                email_verified_at=now,
                created_at=now,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            account = db.scalar(select(RegisteredAccount).where(RegisteredAccount.username == "admin"))
            if account is None or account.id != "admin":
                raise