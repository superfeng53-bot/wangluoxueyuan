"""Login CLI for 成都职业培训网络学院."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import get_session_manager
from .config import DEFAULT_ACCOUNT_FILE, DEFAULT_COOKIES_FILE, DEFAULT_USER_PROFILE_FILE


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--user-id", default="default")
    p.add_argument("-u", "--username")
    p.add_argument("-p", "--password")
    p.add_argument("--account", default=str(DEFAULT_ACCOUNT_FILE))
    p.add_argument("-o", "--output", default=str(DEFAULT_COOKIES_FILE))
    p.add_argument("--check", action="store_true", help="check existing cookies only")
    p.add_argument("--cookies", default=str(DEFAULT_COOKIES_FILE))
    args = p.parse_args()

    mgr = get_session_manager()

    if args.check:
        cookies = json.loads(Path(args.cookies).read_text(encoding="utf-8"))
        client = mgr.get_client(args.user_id)
        client.load_cookies(cookies)
        profile_path = DEFAULT_USER_PROFILE_FILE
        if profile_path.exists():
            client.user_profile = json.loads(profile_path.read_text(encoding="utf-8"))
        ok = client.is_logged_in()
        print("session_ok" if ok else "session_expired")
        sys.exit(0 if ok else 2)

    if args.username and args.password:
        username, password = args.username, args.password
    else:
        cfg = json.loads(Path(args.account).read_text(encoding="utf-8"))
        username, password = cfg["username"], cfg["password"]

    result = mgr.login_user(args.user_id, username, password)
    if not result.success:
        print(f"login failed: {result.message} ({result.hint})", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    if result.user_info:
        DEFAULT_USER_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_USER_PROFILE_FILE.write_text(
            json.dumps(result.user_info, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"login ok: {result.user_info.get('name', '')} token saved to {args.output}")


if __name__ == "__main__":
    main()
