"""B 型年度进度与 my_train 服务端同步。"""
from __future__ import annotations

import json
from typing import Any

from wlxy_api.train import TrainService, chapter_progress_snapshot


def year_progress_percent(progress: float) -> int:
    return min(100, max(0, int(round(float(progress) * 100))))


def build_year_status_from_server(
    trains: TrainService,
    year: int | str,
    *,
    prev: dict[str, Any] | None = None,
    chapters_done: int | None = None,
    chapters_total: int | None = None,
    message: str = "",
) -> dict[str, Any] | None:
    record = trains.get_year_record(year)
    if record is None:
        return None

    chapters = trains.list_year_chapters(year)
    finished = sum(1 for c in chapters if c.finished)
    pct = year_progress_percent(record.progress)

    entry: dict[str, Any] = {
        "progress_percent": pct,
        "completed": record.completed,
        "server_state": record.state,
        "server_progress": record.progress,
        "chapters_done": chapters_done if chapters_done is not None else finished,
        "chapters_total": chapters_total if chapters_total is not None else len(chapters),
        "message": message or (prev or {}).get("message", ""),
    }

    if record.completed:
        return entry

    pending = [c for c in chapters if not c.finished]
    if pending:
        snap = chapter_progress_snapshot(pending[0])
        entry.update({
            "current_course_title": snap.get("current_course_title"),
            "current_chapter_title": snap.get("current_chapter_title"),
            "current_chapter_progress": snap.get("current_chapter_progress"),
            "server_chapter_progress": snap.get("server_chapter_progress"),
        })
    return entry


def target_years_for_account(account: dict) -> list[str]:
    raw = account.get("target_years_json") or "[]"
    try:
        years = json.loads(raw) if isinstance(raw, str) else list(raw)
    except json.JSONDecodeError:
        years = []
    years = [str(y).strip() for y in years if str(y).strip()]
    if years:
        return years
    extra = json.loads(account.get("extra_json") or "{}")
    return sorted((extra.get("year_status") or {}).keys(), reverse=True)


def sync_years_in_extra(
    extra: dict[str, Any],
    trains: TrainService,
    years: list[str],
    *,
    message_by_year: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """用服务端 my_train 刷新 extra.year_status，返回 (extra, report)。"""
    year_status = dict(extra.get("year_status") or {})
    report: dict[str, Any] = {"years": {}}

    for year_key in years:
        msg = (message_by_year or {}).get(year_key, "")
        prev = dict(year_status.get(year_key) or {})
        entry = build_year_status_from_server(
            trains,
            year_key,
            prev=prev,
            message=msg or prev.get("message", ""),
        )
        if entry is None:
            report["years"][year_key] = {"found": False}
            continue
        year_status[year_key] = entry
        report["years"][year_key] = {
            "found": True,
            "progress_percent": entry["progress_percent"],
            "completed": entry["completed"],
            "server_progress": entry["server_progress"],
            "server_state": entry["server_state"],
        }

    extra["year_status"] = year_status

    current_year = str(extra.get("current_year") or "").strip()
    if current_year and current_year in year_status:
        extra["year_progress_percent"] = year_status[current_year]["progress_percent"]
    elif year_status:
        pcts = [v["progress_percent"] for v in year_status.values()]
        extra["year_progress_percent"] = min(pcts)

    return extra, report


def sync_account_years(
    session_manager,
    account: dict,
    *,
    years: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    acc_id = account["id"]
    extra = json.loads(account.get("extra_json") or "{}")
    year_list = years or target_years_for_account(account)
    if not year_list:
        return extra, {"years": {}, "error": "无目标年度"}

    user_id = str(acc_id)
    _, cookies, _, err = session_manager.ensure_session(
        user_id,
        account["username"],
        account["password"],
        extra.get("cookies"),
    )
    if err:
        raise RuntimeError(err)
    if cookies:
        extra["cookies"] = cookies

    trains = session_manager.get_train_service(user_id)
    return sync_years_in_extra(extra, trains, year_list)
