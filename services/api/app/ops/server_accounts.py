from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from getpass import getpass
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.init_db import ALLOWED_USER_ROLES, hash_password
from app.db.models import AuthSession, UserAccount
from app.db.session import Database

ACCOUNT_STATUSES = ("ACTIVE", "LOCKED", "DISABLED")
MIN_PASSWORD_LENGTH = 8


class AccountOperationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AccountOperationResult:
    action: str
    username: str
    user_id: str
    revoked_sessions: int


PasswordProvider = Callable[[str], str]


def create_account(
    database_url: str,
    *,
    username: str,
    display_name: str,
    role: str,
    password_provider: PasswordProvider = getpass,
    login_id: str | None = None,
) -> AccountOperationResult:
    username = _normalize_required(username, "username")
    login_id = _normalize_required(login_id or username, "login_id")
    display_name = _normalize_required(display_name, "display_name")
    _validate_role(role)
    password = _read_new_password(password_provider)

    database = Database(database_url)
    try:
        with database.session() as session:
            existing_account = _find_account(session, username, login_id=login_id)
            if existing_account is not None:
                raise AccountOperationError(f"account already exists: {username}")

            user_id = f"user-{uuid4().hex}"
            account = UserAccount(
                user_id=user_id,
                username=username,
                login_id=login_id,
                display_name=display_name,
                role=role,
                password_hash=hash_password(password),
                is_active=True,
                status="ACTIVE",
            )
            session.add(account)
            session.commit()
            return AccountOperationResult(
                action="created",
                username=account.username,
                user_id=account.user_id,
                revoked_sessions=0,
            )
    finally:
        database.dispose()


def reset_password(
    database_url: str,
    *,
    username: str,
    password_provider: PasswordProvider = getpass,
    activate: bool = False,
) -> AccountOperationResult:
    username = _normalize_required(username, "username")
    password = _read_new_password(password_provider)

    database = Database(database_url)
    try:
        with database.session() as session:
            account = _require_account(session, username)
            account.password_hash = hash_password(password)
            if activate:
                account.is_active = True
                account.status = "ACTIVE"

            revoked_sessions = _revoke_active_sessions(
                session,
                account.user_id,
                "password_reset",
            )
            session.add(account)
            session.commit()
            return AccountOperationResult(
                action="password_reset",
                username=account.username,
                user_id=account.user_id,
                revoked_sessions=revoked_sessions,
            )
    finally:
        database.dispose()


def set_status(database_url: str, *, username: str, status: str) -> AccountOperationResult:
    username = _normalize_required(username, "username")
    status = status.strip().upper()
    if status not in ACCOUNT_STATUSES:
        raise AccountOperationError(f"status must be one of: {', '.join(ACCOUNT_STATUSES)}")

    database = Database(database_url)
    try:
        with database.session() as session:
            account = _require_account(session, username)
            account.status = status
            account.is_active = status == "ACTIVE"
            revoked_sessions = _revoke_active_sessions(
                session,
                account.user_id,
                _status_revocation_reason(status),
            )
            session.add(account)
            session.commit()
            return AccountOperationResult(
                action=f"status_{status.lower()}",
                username=account.username,
                user_id=account.user_id,
                revoked_sessions=revoked_sessions,
            )
    finally:
        database.dispose()


def set_role(database_url: str, *, username: str, role: str) -> AccountOperationResult:
    username = _normalize_required(username, "username")
    _validate_role(role)

    database = Database(database_url)
    try:
        with database.session() as session:
            account = _require_account(session, username)
            account.role = role
            revoked_sessions = _revoke_active_sessions(session, account.user_id, "role_changed")
            session.add(account)
            session.commit()
            return AccountOperationResult(
                action="role_changed",
                username=account.username,
                user_id=account.user_id,
                revoked_sessions=revoked_sessions,
            )
    finally:
        database.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    database_url = args.database_url or Settings().database_url

    try:
        result = _run_command(args, database_url)
    except AccountOperationError as error:
        parser.exit(2, f"error: {error}\n")

    print(
        f"{result.action}: username={result.username} "
        f"user_id={result.user_id} revoked_sessions={result.revoked_sessions}"
    )
    return 0


def _run_command(args: argparse.Namespace, database_url: str) -> AccountOperationResult:
    if args.command == "create":
        return create_account(
            database_url,
            username=args.username,
            login_id=args.login_id,
            display_name=args.display_name,
            role=args.role,
        )
    if args.command == "reset-password":
        return reset_password(database_url, username=args.username, activate=args.activate)
    if args.command == "set-status":
        return set_status(database_url, username=args.username, status=args.status)
    if args.command == "set-role":
        return set_role(database_url, username=args.username, role=args.role)
    raise AccountOperationError(f"unknown command: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage FlowNote FastAPI server accounts in the server database."
    )
    parser.add_argument(
        "--database-url",
        help="SQLAlchemy database URL. Defaults to FLOWNOTE_DATABASE_URL or .env.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create an active server account.")
    create_parser.add_argument("--username", required=True)
    create_parser.add_argument("--login-id")
    create_parser.add_argument("--display-name", required=True)
    create_parser.add_argument("--role", required=True, choices=ALLOWED_USER_ROLES)

    reset_parser = subparsers.add_parser(
        "reset-password",
        help="Reset a server account password and revoke active sessions.",
    )
    reset_parser.add_argument("--username", required=True)
    reset_parser.add_argument(
        "--activate",
        action="store_true",
        help="Also set the account to ACTIVE. Use only after operational approval.",
    )

    status_parser = subparsers.add_parser(
        "set-status",
        help="Set ACTIVE, LOCKED, or DISABLED and revoke active sessions.",
    )
    status_parser.add_argument("--username", required=True)
    status_parser.add_argument("--status", required=True, choices=ACCOUNT_STATUSES)

    role_parser = subparsers.add_parser(
        "set-role",
        help="Change a server account role and revoke active sessions.",
    )
    role_parser.add_argument("--username", required=True)
    role_parser.add_argument("--role", required=True, choices=ALLOWED_USER_ROLES)
    return parser


def _find_account(
    session: Session,
    username: str,
    *,
    login_id: str | None = None,
) -> UserAccount | None:
    identifiers = [username]
    if login_id is not None and login_id != username:
        identifiers.append(login_id)
    return session.scalar(
        select(UserAccount).where(
            or_(UserAccount.username.in_(identifiers), UserAccount.login_id.in_(identifiers))
        )
    )


def _require_account(session: Session, username: str) -> UserAccount:
    account = _find_account(session, username)
    if account is None:
        raise AccountOperationError(f"user not found: {username}")
    return account


def _read_new_password(password_provider: PasswordProvider) -> str:
    password = password_provider("new password: ")
    confirm = password_provider("confirm password: ")
    if password != confirm:
        raise AccountOperationError("passwords do not match")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountOperationError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    return password


def _revoke_active_sessions(session: Session, user_id: str, reason: str) -> int:
    result = session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.status == "ACTIVE")
        .values(
            status="REVOKED",
            revoked_at=datetime.now(timezone.utc),
            revoked_reason=reason,
        )
    )
    return int(result.rowcount or 0)


def _validate_role(role: str) -> None:
    if role not in ALLOWED_USER_ROLES:
        raise AccountOperationError(f"role must be one of: {', '.join(ALLOWED_USER_ROLES)}")


def _normalize_required(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise AccountOperationError(f"{field_name} is required")
    return normalized


def _status_revocation_reason(status: str) -> str:
    return {
        "ACTIVE": "account_activated",
        "LOCKED": "account_locked",
        "DISABLED": "account_disabled",
    }[status]


if __name__ == "__main__":
    raise SystemExit(main())
