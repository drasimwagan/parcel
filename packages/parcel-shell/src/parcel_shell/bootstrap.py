from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.hashing import hash_password
from parcel_shell.config import get_settings
from parcel_shell.db import create_engine, create_sessionmaker
from parcel_shell.rbac import service
from parcel_shell.rbac.models import Role, User


async def _get_admin_role(db: AsyncSession) -> Role:
    role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
    if role is None:
        raise RuntimeError(
            "built-in admin role missing — run 'alembic upgrade head' first"
        )
    return role


async def create_admin_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    force: bool = False,
) -> User:
    if len(password) < service.MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"password must be at least {service.MIN_PASSWORD_LENGTH} characters"
        )
    lowered = email.lower()
    existing = (
        await db.execute(select(User).where(User.email == lowered))
    ).scalar_one_or_none()
    admin_role = await _get_admin_role(db)

    if existing is not None:
        if not force:
            raise RuntimeError(f"user {lowered!r} already exists; use --force to rehash")
        await db.refresh(existing, ["roles"])
        existing.password_hash = hash_password(password)
        existing.updated_at = datetime.now(timezone.utc)
        if not any(r.id == admin_role.id for r in existing.roles):
            existing.roles.append(admin_role)
        await db.flush()
        return existing

    user = User(
        email=lowered,
        password_hash=hash_password(password),
        is_active=True,
    )
    user.roles = [admin_role]
    db.add(user)
    await db.flush()
    return user


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m parcel_shell.bootstrap")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create-admin", help="Create the first admin user")
    create.add_argument("--email", required=True)
    create.add_argument("--password", default=None, help="prompts if omitted")
    create.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    password = args.password
    if password is None:
        password = getpass.getpass("Password: ")

    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as db:
            try:
                user = await create_admin_user(
                    db, email=args.email, password=password, force=args.force
                )
            except (ValueError, RuntimeError) as e:
                await db.rollback()
                sys.stderr.write(f"error: {e}\n")
                return 1
            await db.commit()
            sys.stdout.write(f"created admin user: {user.id} <{user.email}>\n")
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
