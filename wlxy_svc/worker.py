"""B 型账号 Worker：按目标年度调用 YearTaskRunner。"""
from __future__ import annotations

import json
from typing import Any

from wlxy_api.member import MemberService
from wlxy_api.train import TrainService
from wlxy_api.responses import is_transient_session_error
from wlxy_api.year_task import YearTaskRunner

from .worker_base import AccountWorkerBase, PipelineResult
from .year_sync import build_year_status_from_server


def _learning_status_msg(snapshot: dict[str, Any]) -> str:
    course = (snapshot.get("current_course_title") or "").strip()
    chapter = (snapshot.get("current_chapter_title") or "").strip()
    pct = snapshot.get("current_chapter_progress")
    if not course and chapter:
        course = chapter
        chapter = ""
    if not course:
        return "视频学习中"
    msg = f"学习中：{course}"
    if chapter and chapter != course:
        msg += f" / {chapter}"
    if pct is not None:
        msg += f"（{pct}%）"
    return msg


class AccountWorker(AccountWorkerBase):
    def run_pipeline(self, account: dict, client) -> PipelineResult:
        raise NotImplementedError("B 型使用 run_year_pipeline")

    def get_session_probe(self):
        acc_id = self._account["id"]

        def _probe() -> None:
            self._sm.get_member_service(str(acc_id)).get_profile_by_token()

        return _probe

    def fetch_member_profile(self, client) -> dict[str, Any]:
        member = MemberService(client)
        profile = member.get_profile_by_token()
        detail: dict[str, Any] = {}
        try:
            detail = member.query_user()
        except Exception:
            pass
        name = (
            profile.get("userName")
            or profile.get("realName")
            or profile.get("name")
            or detail.get("userName")
            or detail.get("realName")
            or ""
        ).strip()
        id_card = (
            profile.get("idCard")
            or profile.get("idcard")
            or detail.get("idCard")
            or detail.get("idcard")
            or ""
        ).strip()
        return {
            "display_name": name,
            "real_name": name,
            "id_card": id_card,
            "user_profile": profile,
        }

    def run_year_pipeline(self, account: dict, client, year: str) -> PipelineResult:
        acc_id = account["id"]
        username = account["username"]
        password = account["password"]
        extra = json.loads(account.get("extra_json") or "{}")
        report_mode = extra.get("report_mode") or "normal"
        year_key = str(year).strip()

        extra["current_year"] = year_key
        extra["phase"] = "video_play"
        self._store.update_extra(acc_id, extra)

        def _on_progress(snapshot: dict[str, Any]) -> None:
            cur = json.loads(
                (self._store.get_account(acc_id) or account).get("extra_json") or "{}",
            )
            cur.update(snapshot)
            cur["phase"] = "video_play"
            cur["current_year"] = year_key
            year_status = dict(cur.get("year_status") or {})
            ys = dict(year_status.get(year_key) or {})
            ys.update({
                "current_course_title": snapshot.get("current_course_title"),
                "current_chapter_title": snapshot.get("current_chapter_title"),
                "current_chapter_progress": snapshot.get("current_chapter_progress"),
                "server_chapter_progress": snapshot.get("server_chapter_progress"),
            })
            year_pct = snapshot.get("year_progress_percent")
            if year_pct is not None:
                ys["progress_percent"] = year_pct
                cur["year_progress_percent"] = year_pct
            year_status[year_key] = ys
            cur["year_status"] = year_status
            msg = _learning_status_msg(snapshot)
            self._store.update_account(
                acc_id,
                extra_json=json.dumps(cur, ensure_ascii=False),
                status_msg=msg,
            )

        def _run(_client) -> Any:
            return YearTaskRunner(_client).run_year_task(
                year_key,
                report_mode=report_mode,
                on_progress=_on_progress,
            )

        try:
            result = self.call_with_session_retry(
                acc_id, username, password, extra, _run,
            )
        except Exception as exc:
            err_text = str(exc)
            return PipelineResult(
                success=False,
                final_state="failed",
                status_msg=err_text,
                error=err_text,
                hard_failure=(
                    self._is_hard_auth_error(err_text)
                    and not is_transient_session_error(err_text)
                ),
            )

        logs = [
            {"stage": log.stage, "ok": log.ok, "message": log.message}
            for log in (result.logs or [])
        ]
        extra = json.loads(
            (self._store.get_account(acc_id) or account).get("extra_json") or "{}",
        )
        year_status = dict(extra.get("year_status") or {})
        prev = dict(year_status.get(year_key) or {})
        trains = TrainService(client)
        server_entry = build_year_status_from_server(
            trains,
            year_key,
            prev=prev,
            chapters_done=result.chapters_done,
            chapters_total=result.chapters_total,
            message=result.message,
        )
        if server_entry is not None:
            server_entry["completed"] = bool(
                result.year_completed or result.skipped or server_entry.get("completed"),
            )
            year_entry = server_entry
        else:
            year_entry = {
                "completed": bool(result.year_completed or result.skipped),
                "chapters_done": result.chapters_done,
                "chapters_total": result.chapters_total,
                "message": result.message,
            }
            if prev.get("progress_percent") is not None:
                year_entry["progress_percent"] = prev["progress_percent"]
        year_status[year_key] = year_entry
        extra_updates = {
            "year_status": year_status,
            "current_year": year_key,
            "report_mode": report_mode,
            "year_progress_percent": year_entry.get("progress_percent"),
        }

        if result.ok and (result.year_completed or result.skipped):
            return PipelineResult(
                success=True,
                final_state="completed",
                status_msg=result.message,
                extra_updates=extra_updates,
                logs=logs,
            )
        if result.ok:
            err_text = result.message or f"{year_key} 年度未完成"
            return PipelineResult(
                success=False,
                final_state="failed",
                status_msg=err_text,
                error=result.error or err_text,
                extra_updates=extra_updates,
                logs=logs,
            )

        err_text = result.error or result.message or "年度任务失败"
        return PipelineResult(
            success=False,
            final_state="failed",
            status_msg=err_text,
            error=err_text,
            extra_updates=extra_updates,
            logs=logs,
            hard_failure=self._is_year_hard_failure(err_text),
        )

    @staticmethod
    def _is_year_hard_failure(err: str) -> bool:
        hard_markers = (
            "未报名",
            "不在 my_train",
            "待考未处理",
            "账号不存在",
            "密码错误",
        )
        return any(m in err for m in hard_markers)
