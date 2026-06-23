from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import get_session_manager
from .config import DEFAULT_COOKIES_FILE, DEFAULT_USER_PROFILE_FILE
from .year_task import YearTaskRunner


def main() -> None:
    p = argparse.ArgumentParser(description="WLXY year task runner CLI")
    p.add_argument("--user-id", default="default")
    p.add_argument("--cookies", default=str(DEFAULT_COOKIES_FILE))
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--report-mode", default="normal", choices=["normal", "fast"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-chapters", type=int)
    p.add_argument("--max-reports", type=int)
    args = p.parse_args()

    client = get_session_manager().get_client(args.user_id)
    cookies = json.loads(Path(args.cookies).read_text(encoding="utf-8"))
    client.load_cookies(cookies)
    if DEFAULT_USER_PROFILE_FILE.exists():
        client.user_profile = json.loads(DEFAULT_USER_PROFILE_FILE.read_text(encoding="utf-8"))

    runner = YearTaskRunner(client)
    result = runner.run_year_task(
        args.year,
        report_mode=args.report_mode,
        dry_run=args.dry_run,
        max_chapters=args.max_chapters,
        max_reports_per_chapter=args.max_reports,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
