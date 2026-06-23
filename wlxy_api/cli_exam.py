from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import get_session_manager
from .config import DEFAULT_COOKIES_FILE, DEFAULT_USER_PROFILE_FILE
from .exam import ExamService


def _load(mgr, user_id: str, cookies_path: str) -> ExamService:
    client = mgr.get_client(user_id)
    cookies = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
    client.load_cookies(cookies)
    if DEFAULT_USER_PROFILE_FILE.exists():
        client.user_profile = json.loads(DEFAULT_USER_PROFILE_FILE.read_text(encoding="utf-8"))
    return ExamService(client)


def main() -> None:
    p = argparse.ArgumentParser(description="WLXY exam CLI")
    p.add_argument("--user-id", default="default")
    p.add_argument("--cookies", default=str(DEFAULT_COOKIES_FILE))
    sub = p.add_subparsers(dest="cmd", required=True)
    pending = sub.add_parser("pending")
    done = sub.add_parser("done")
    query = sub.add_parser("query")
    query.add_argument("exam_id")
    args = p.parse_args()

    svc = _load(get_session_manager(), args.user_id, args.cookies)
    if args.cmd == "pending":
        print(json.dumps(svc.list_my_exams(exam_type=1), ensure_ascii=False, indent=2))
    elif args.cmd == "done":
        print(json.dumps(svc.list_my_exams(exam_type=2), ensure_ascii=False, indent=2))
    elif args.cmd == "query":
        print(json.dumps(svc.query_exam(args.exam_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
