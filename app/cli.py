"""One-time administrator provisioning.

Usage (inside the app container or a local venv):

    python -m app.cli create-admin

Credentials are supplied interactively (recommended) or via environment
variables ADMIN_EMAIL / ADMIN_FULL_NAME / ADMIN_PASSWORD. There are no
built-in default credentials.
"""
import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models.user import Role, User
from app.security import hash_password, password_policy_errors


def create_admin(args: argparse.Namespace) -> int:
    email = args.email or os.environ.get("ADMIN_EMAIL") or input("Admin email: ").strip().lower()
    full_name = (
        args.full_name
        or os.environ.get("ADMIN_FULL_NAME")
        or input("Admin full name: ").strip()
    )
    password = args.password or os.environ.get("ADMIN_PASSWORD") or getpass.getpass(
        "Admin password: "
    )
    confirm = password if args.password or os.environ.get("ADMIN_PASSWORD") else getpass.getpass(
        "Confirm password: "
    )

    errors: list[str] = []
    if not email or "@" not in email:
        errors.append("A valid email address is required.")
    if not full_name:
        errors.append("Full name is required.")
    errors.extend(password_policy_errors(password))
    if password != confirm:
        errors.append("Passwords do not match.")
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == email)) is not None:
            print(f"error: a user with email {email} already exists.", file=sys.stderr)
            return 1
        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role=Role.admin,
            is_active=True,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()
    print(f"Administrator account created for {email}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p_create = sub.add_parser("create-admin", help="Create an administrator account (one-time).")
    p_create.add_argument("--email", help="Admin email (or ADMIN_EMAIL env).")
    p_create.add_argument("--full-name", dest="full_name", help="Admin full name.")
    p_create.add_argument(
        "--password",
        help="Admin password (prefer interactive input or ADMIN_PASSWORD env to avoid shell history).",
    )
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
