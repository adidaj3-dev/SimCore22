"""
Admin tasks from the command line, for when the web page can't do them (no browser on the PC,
or the only admin is locked out).

    python -m simcore22.league create-admin --email you@venue.com --name "Your Name"
    python -m simcore22.league reset-password --email someone@venue.com
    python -m simcore22.league list-users

The password is asked for here, never put on the command line. By default this works on the
same database the web UI uses (data/simcore22.db); --db picks another file.
"""
import argparse
import getpass
import sys
from pathlib import Path
from typing import Optional

from simcore22.engine import round_log
from simcore22.league import accounts, security
from simcore22.league.db import Database, audit
from simcore22.league.errors import LeagueError


def _ask_password() -> str:
    first = getpass.getpass("Password (at least 8 characters): ")
    if first != getpass.getpass("Again: "):
        raise LeagueError("The two passwords don't match.")
    return first


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="SimCore22 account tasks")
    parser.add_argument("--db", type=Path, default=Path(round_log.DEFAULT_PATH).parent / "simcore22.db", help="database file (default: data/simcore22.db)")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help="make a venue admin account")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    reset = sub.add_parser("reset-password", help="set a new password for an existing account")
    reset.add_argument("--email", required=True)
    sub.add_parser("list-users", help="show every account")
    args = parser.parse_args(argv)

    db = Database(args.db)
    try:
        with db.connect() as conn:
            if args.command == "create-admin":
                user = accounts.create_user(conn, email=args.email, password=_ask_password(), display_name=args.name, role="admin")
                print(f"Created admin {user['display_name']} <{user['email']}>.")
            elif args.command == "reset-password":
                row = conn.execute("SELECT id FROM users WHERE email = ?", (accounts.clean_email(args.email),)).fetchone()
                if row is None:
                    raise LeagueError("No account has that email.")
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(accounts.clean_password(_ask_password())), row["id"]))
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
                audit(conn, None, "password_reset_cli", f"user {row['id']}")
                print("Password changed. They've been logged out everywhere.")
            else:
                for u in accounts.list_users(conn):
                    flags = ", ".join(f for f in (u["role"], "disabled" if u["disabled"] else "") if f)
                    print(f"{u['id']:>4}  {u['display_name']:<28} {u['email']:<34} {flags}")
    except LeagueError as exc:
        print(f"Couldn't do that: {exc.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
