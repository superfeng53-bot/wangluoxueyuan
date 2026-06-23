from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import get_session_manager
from .config import DEFAULT_COOKIES_FILE, DEFAULT_USER_PROFILE_FILE
from .study import StudyService
from .train import TrainService


def _load(mgr, user_id: str, cookies_path: str):
    client = mgr.get_client(user_id)
    cookies = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
    client.load_cookies(cookies)
    if DEFAULT_USER_PROFILE_FILE.exists():
        client.user_profile = json.loads(DEFAULT_USER_PROFILE_FILE.read_text(encoding="utf-8"))
    return StudyService(client), TrainService(client)


def main() -> None:
    p = argparse.ArgumentParser(description="WLXY study progress CLI")
    p.add_argument("--user-id", default="default")
    p.add_argument("--cookies", default=str(DEFAULT_COOKIES_FILE))
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--report-mode", default="normal", choices=["normal", "fast"])
    p.add_argument("--max-reports", type=int, default=1, help="每章节最多上报次数（测试用）")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    study, trains = _load(get_session_manager(), args.user_id, args.cookies)
    record = trains.get_year_record(args.year)
    if record is None:
        raise SystemExit(f"year {args.year} not found")

    pending = [c for c in trains.list_year_chapters(args.year) if not c.finished]
    if args.dry_run:
        print(json.dumps({"pending_chapters": [c.to_dict() for c in pending]}, ensure_ascii=False, indent=2))
        return
    if not pending:
        print(json.dumps({"message": "no pending chapters"}, ensure_ascii=False))
        return

    chapter = pending[0]
    result = study.study_chapter(
        record,
        chapter,
        report_mode=args.report_mode,
        max_reports=args.max_reports,
    )
    print(json.dumps({
        "chapter": chapter.to_dict(),
        "ok": result.ok,
        "message": result.message,
        "study_length": result.study_length,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
