from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import get_session_manager
from .config import DEFAULT_COOKIES_FILE, DEFAULT_USER_PROFILE_FILE
from .train import TrainService


def _load_train(mgr, user_id: str, cookies_path: str) -> TrainService:
    client = mgr.get_client(user_id)
    cookies = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
    client.load_cookies(cookies)
    if DEFAULT_USER_PROFILE_FILE.exists():
        client.user_profile = json.loads(DEFAULT_USER_PROFILE_FILE.read_text(encoding="utf-8"))
    return TrainService(client)


def main() -> None:
    p = argparse.ArgumentParser(description="WLXY train/year CLI")
    p.add_argument("--user-id", default="default")
    p.add_argument("--cookies", default=str(DEFAULT_COOKIES_FILE))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("years")
    year = sub.add_parser("year")
    year.add_argument("year", type=int)
    year.add_argument("--chapters", action="store_true")
    detail = sub.add_parser("detail")
    detail.add_argument("--train-id", required=True)
    args = p.parse_args()

    svc = _load_train(get_session_manager(), args.user_id, args.cookies)

    if args.cmd == "years":
        print(json.dumps([x.to_dict() for x in svc.list_yearly_trains()], ensure_ascii=False, indent=2))
    elif args.cmd == "year":
        record = svc.get_year_record(args.year)
        if record is None:
            raise SystemExit(f"year {args.year} not found")
        out: dict = record.to_dict()
        if args.chapters:
            out["chapters"] = [c.to_dict() for c in svc.list_year_chapters(args.year)]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif args.cmd == "detail":
        print(json.dumps(svc.get_train_detail(args.train_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
