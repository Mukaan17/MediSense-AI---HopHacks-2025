#!/usr/bin/env python3
"""Create or update a user in the auth users file.

Usage:
  python3 scripts/create_user.py <username> [--role clinician|admin] [--file config/users.json]

Prompts for the password (not echoed) and writes a bcrypt hash. The users
file is gitignored - distribute it through your secrets channel, never the
repository.
"""

import argparse
import getpass
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import ROLES, hash_password  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update an auth user")
    parser.add_argument("username")
    parser.add_argument("--role", choices=list(ROLES), default="clinician")
    parser.add_argument("--file", default=os.getenv("AUTH_USERS_FILE", os.path.join("config", "users.json")))
    args = parser.parse_args()

    password = getpass.getpass(f"Password for {args.username}: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        sys.exit("Passwords do not match.")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters.")

    users = {}
    if os.path.exists(args.file):
        with open(args.file) as f:
            users = json.load(f) or {}

    users[args.username] = {"password_hash": hash_password(password), "role": args.role}
    os.makedirs(os.path.dirname(args.file) or ".", exist_ok=True)
    with open(args.file, "w") as f:
        json.dump(users, f, indent=2)
    os.chmod(args.file, 0o600)
    print(f"User '{args.username}' ({args.role}) written to {args.file}")


if __name__ == "__main__":
    main()
