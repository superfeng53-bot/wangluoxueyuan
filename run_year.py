#!/usr/bin/env python3
"""B 型公需年度单账号 runner CLI。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wlxy_api import get_session_manager
from wlxy_api.config import DEFAULT_ACCOUNT_FILE, DEFAULT_COOKIES_FILE, DEFAULT_USER_PROFILE_FILE
from wlxy_api.year_task import YearTaskRunner


def _save_cookies(cookies: dict[str, str], profile: dict | None) -> None:
    DEFAULT_COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    if profile:
        DEFAULT_USER_PROFILE_FILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_years(raw: str) -> list[int]:
    years: list[int] = []
    for part in raw.replace("，", ",").split(","):
        part = part.strip()
        if part:
            years.append(int(part))
    if not years:
        raise SystemExit("需要至少一个年度，例如 --years 2026,2025")
    return years


def _resolve_auth(args: argparse.Namespace) -> tuple[str, str, dict[str, str] | None]:
    username = password = ""
    cookies: dict[str, str] | None = None

    if args.cookies:
        cookies = json.loads(Path(args.cookies).read_text(encoding="utf-8"))
    elif args.account:
        cfg = json.loads(Path(args.account).read_text(encoding="utf-8"))
        username, password = cfg["username"], cfg["password"]
        if DEFAULT_COOKIES_FILE.exists():
            try:
                cookies = json.loads(DEFAULT_COOKIES_FILE.read_text(encoding="utf-8"))
            except Exception:
                cookies = None
    elif args.username and args.password:
        username, password = args.username, args.password
    else:
        sys.exit("需要 --cookies / --account / -u 与 -p 之一")

    return username, password, cookies


def main() -> None:
    p = argparse.ArgumentParser(description="成都职业培训网络学院 — 公需年度学习 runner")
    p.add_argument("--cookies", help="cookies JSON 路径")
    p.add_argument("--account", default=str(DEFAULT_ACCOUNT_FILE), help="账号 JSON（含 username/password）")
    p.add_argument("-u", "--username")
    p.add_argument("-p", "--password")
    p.add_argument("--user-id", default="default")
    p.add_argument("--years", required=True, help="目标年度，逗号分隔，按列表顺序执行")
    p.add_argument("--probe-progress", action="store_true", help="仅跑进度增量探针（约 60s），不跑完整年度")
    p.add_argument("--probe-seconds", type=int, default=60)
    p.add_argument("--report-mode", default="normal", choices=["normal", "fast"])
    p.add_argument("--dry-run", action="store_true", help="只列出待学章节")
    p.add_argument("--max-chapters", type=int, help="最多处理章节数（冒烟用）")
    p.add_argument("--max-reports", type=int, help="每章节最多上报次数（冒烟用）")
    args = p.parse_args()

    years = _parse_years(args.years)
    username, password, cookies = _resolve_auth(args)
    mgr = get_session_manager()

    if username:
        reused, cookies, _info, err = mgr.ensure_session_with_member_probe(
            args.user_id, username, password, cookies,
        )
        if err:
            sys.exit(f"登录失败: {err}")
        if cookies:
            _save_cookies(cookies, mgr.get_client(args.user_id).user_profile)
    elif cookies:
        client = mgr.get_client(args.user_id)
        client.load_cookies(cookies)
        if DEFAULT_USER_PROFILE_FILE.exists():
            client.user_profile = json.loads(DEFAULT_USER_PROFILE_FILE.read_text(encoding="utf-8"))
        if not client.is_logged_in():
            sys.exit("cookies 无效或已过期，请使用 --account 重新登录")

    runner = mgr.get_year_task_runner(args.user_id)
    on_update = _save_cookies if username else None

    if args.probe_progress:
        year = years[0]
        if username:
            result = runner.probe_progress_with_retry(
                mgr,
                user_id=args.user_id,
                username=username,
                password=password,
                cookies=cookies,
                on_cookies_updated=on_update,
                year=year,
                probe_seconds=args.probe_seconds,
                report_mode=args.report_mode,
            )
        else:
            result = runner.probe_progress(
                year,
                probe_seconds=args.probe_seconds,
                report_mode=args.report_mode,
            )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        sys.exit(0 if result.ok else 1)

    results = []
    for year in years:
        if username:
            outcome = runner.run_year_task_with_retry(
                mgr,
                user_id=args.user_id,
                username=username,
                password=password,
                cookies=cookies,
                on_cookies_updated=on_update,
                year=year,
                report_mode=args.report_mode,
                dry_run=args.dry_run,
                max_chapters=args.max_chapters,
                max_reports_per_chapter=args.max_reports,
            )
        else:
            outcome = YearTaskRunner(mgr.get_client(args.user_id)).run_year_task(
                year,
                report_mode=args.report_mode,
                dry_run=args.dry_run,
                max_chapters=args.max_chapters,
                max_reports_per_chapter=args.max_reports,
            )
        results.append(outcome.to_dict())
        if not outcome.ok and not args.dry_run:
            print(json.dumps({"years": results}, ensure_ascii=False, indent=2))
            sys.exit(1)

    print(json.dumps({"years": results}, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
