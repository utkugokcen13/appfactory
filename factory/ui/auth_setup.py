"""CLI to manage `factory/ui/auth_users.yaml` — add, remove, or list users.

Usage:
  python -m factory.ui.auth_setup add-user <username> [--name "Display Name"]
  python -m factory.ui.auth_setup remove-user <username>
  python -m factory.ui.auth_setup list

`add-user` prompts for the password securely (won't echo). Stores a
bcrypt hash, never the raw password — safe to commit the yaml file.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

import bcrypt
import yaml

USERS_PATH = Path(__file__).parent / "auth_users.yaml"


def _load() -> dict:
    if not USERS_PATH.exists():
        return {"credentials": {"usernames": {}}}
    with open(USERS_PATH) as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("credentials", {"usernames": {}})
    return cfg


def _save(cfg: dict) -> None:
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_PATH, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=True, allow_unicode=True)


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def cmd_add(username: str, display_name: str | None) -> None:
    cfg = _load()
    users = cfg["credentials"]["usernames"]
    if username in users:
        ans = input(f"User '{username}' exists. Overwrite password? [y/N] ")
        if ans.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return
    pw1 = getpass.getpass(f"Password for '{username}': ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        print("Passwords don't match. Aborted.", file=sys.stderr)
        sys.exit(1)
    if len(pw1) < 8:
        print("Password must be at least 8 characters. Aborted.", file=sys.stderr)
        sys.exit(1)

    users[username] = {
        "name": display_name or username,
        "password": _hash(pw1),
        "email": f"{username}@local",  # streamlit-authenticator requires this field
        "failed_login_attempts": 0,
        "logged_in": False,
    }
    _save(cfg)
    print(f"✓ User '{username}' saved to {USERS_PATH}")
    print("  Commit & push the yaml so Streamlit Cloud picks it up.")


def cmd_remove(username: str) -> None:
    cfg = _load()
    users = cfg["credentials"]["usernames"]
    if username not in users:
        print(f"User '{username}' not found.", file=sys.stderr)
        sys.exit(1)
    del users[username]
    _save(cfg)
    print(f"✓ User '{username}' removed.")


def cmd_list() -> None:
    cfg = _load()
    users = cfg["credentials"]["usernames"]
    if not users:
        print("(no users yet — add with: add-user <name>)")
        return
    print(f"{len(users)} user(s):")
    for name, meta in sorted(users.items()):
        print(f"  · {name}  ({meta.get('name', name)})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="factory.ui.auth_setup")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add-user", help="Add or update a user")
    p_add.add_argument("username")
    p_add.add_argument("--name", help="Optional display name")

    p_rm = sub.add_parser("remove-user", help="Remove a user")
    p_rm.add_argument("username")

    sub.add_parser("list", help="List existing users")

    args = parser.parse_args()
    if args.cmd == "add-user":
        cmd_add(args.username, args.name)
    elif args.cmd == "remove-user":
        cmd_remove(args.username)
    elif args.cmd == "list":
        cmd_list()


if __name__ == "__main__":
    main()
