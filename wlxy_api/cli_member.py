from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import get_session_manager
from .config import DEFAULT_COOKIES_FILE, DEFAULT_USER_PROFILE_FILE
from .member import MemberService


def _load_session(mgr, user_id: str, cookies_path: str):
    client = mgr.get_client(user_id)
    cookies = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
    client.load_cookies(cookies)
    if DEFAULT_USER_PROFILE_FILE.exists():
        client.user_profile = json.loads(DEFAULT_USER_PROFILE_FILE.read_text(encoding="utf-8"))
    return MemberService(client)


def main() -> None:
    p = argparse.ArgumentParser(description="WLXY member/profile CLI")
    p.add_argument("--user-id", default="default")
    p.add_argument("--cookies", default=str(DEFAULT_COOKIES_FILE))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("profile")
    sub.add_parser("progress")
    sub.add_parser("probe")
    args = p.parse_args()

    mgr = get_session_manager()
    svc = _load_session(mgr, args.user_id, args.cookies)

    if args.cmd == "profile":
        print(json.dumps(svc.get_profile_by_token(), ensure_ascii=False, indent=2))
    elif args.cmd == "progress":
        print(json.dumps(svc.query_userinfo_progress(), ensure_ascii=False, indent=2))
    elif args.cmd == "probe":
        ok = svc.probe_session()
        print("session_ok" if ok else "session_expired")
        sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
