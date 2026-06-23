"""
Worker 基类：处理通用状态转换、session 管理、重试矩阵。
复制到 <svc>/worker.py，继承 AccountWorkerBase，实现：
  - run_pipeline(account, session_client) -> PipelineResult
  - fetch_member_profile(client) -> dict  （B 型无姓名时从站点拉取）
  - （B 型）run_year_pipeline(account, session_client, year) -> YearResult

状态机（A 型）：queued → running → [waiting_apply →] completed | failed（瞬态失败回到 queued）
状态机（B 型）：queued → running → completed | failed（无 waiting_apply）
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import MAX_RETRY, RETRY_DELAY_SEC
from .error_log import build_error_log_text
from .session_retry import call_with_session_retry, is_transient_session_error
from .study_hours import (
    format_resume_time,
    is_outside_study_hours_error,
    next_morning_resume_timestamp,
)


# ── 结果数据类 ────────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    success: bool
    final_state: str = "failed"          # completed | waiting_apply | failed
    status_msg: str = ""
    extra_updates: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    logs: list[dict] = field(default_factory=list)
    hard_failure: bool = False           # True → 不重试，直接 failed


# ── Worker 基类 ───────────────────────────────────────────────────────────────

class AccountWorkerBase(ABC):
    """
    子类必须实现 run_pipeline()；B 型须实现 fetch_member_profile()。
    构造时传入 store、session_manager（来自 <pkg>）、site_profile（A/B）。
    """

    MAX_RETRY = MAX_RETRY
    RETRY_DELAY = RETRY_DELAY_SEC
    SESSION_PROBE_TIMEOUT = 10

    def __init__(
        self,
        account: dict,
        store,
        session_manager,
        *,
        site_profile: str = "A",
        cancel_event: threading.Event | None = None,
        has_credit_apply: bool = False,
    ) -> None:
        self._account = account
        self._store = store
        self._sm = session_manager
        self._site_profile = site_profile.upper()
        self._cancel_event = cancel_event
        self._has_credit_apply = has_credit_apply
        self._started_at = time.time()

    # ── 子类必须实现 ──────────────────────────────────────────────────────────

    @abstractmethod
    def run_pipeline(self, account: dict, client) -> PipelineResult:
        """
        A 型：执行登录后全流程（分配/选课 → 日闸门 → 学习 → 考试 → 申请）。
        分配：build_assignment_plan() → ai_subject_map + course_results（预匹配，不重跑）。
        学习：pick_next_learn_course() 或 course_planner.check_learning_gates / pick_next_unit。
        返回 PipelineResult；若学习完成但申请队列有待处理项，设 final_state='waiting_apply'。
        """
        ...

    def run_year_pipeline(self, account: dict, client, year: str) -> PipelineResult:
        """
        B 型：单年度任务（学习 + 考试）。默认未实现，子类覆盖。
        run_once 在 site_profile=B 时按 target_years_json 顺序调用本方法。
        """
        raise NotImplementedError(
            f"site_profile=B 须实现 run_year_pipeline(account, client, year={year!r})"
        )

    def fetch_member_profile(self, client) -> dict[str, Any]:
        """
        B 型：从站点 API 拉取账号资料（姓名、身份证等）。
        子类必须实现；默认返回空 dict。
        期望字段：display_name / real_name / id_card / user_profile
        """
        return {}

    def get_session_probe(self):
        """
        返回一个 callable，用于 ensure_session 探活。
        默认 None（表示每次都重新登录）；子类重写以提供便宜的 API 调用。
        """
        return None

    def _check_cancelled(self) -> bool:
        return bool(self._cancel_event and self._cancel_event.is_set())

    # ── 主入口（由 Orchestrator 线程调用） ───────────────────────────────────

    def run_once(self) -> None:
        if self._check_cancelled():
            return

        account = self._account
        acc_id = account["id"]
        username = account["username"]
        password = account["password"]
        extra = json.loads(account.get("extra_json") or "{}")

        self._set_phase(acc_id, "login")

        # 1. ensure_session
        try:
            client, new_cookies, err = self._ensure_session(
                acc_id, username, password, extra.get("cookies")
            )
        except Exception as exc:
            self._handle_transient_failure(acc_id, f"session 异常: {exc}")
            return

        if self._check_cancelled():
            return

        if err:
            if self._is_hard_auth_error(err):
                self._store.update_account_status(acc_id, "failed", f"认证失败: {err}")
                self._write_run(acc_id, "failed", err)
                self._save_error_log(acc_id)
            else:
                self._handle_transient_failure(acc_id, f"登录失败: {err}")
            return

        if new_cookies:
            extra["cookies"] = new_cookies
            self._store.update_extra(acc_id, extra)

        # 1b. B 型：无展示名时从站点拉取账号信息
        if self._site_profile == "B":
            extra = self._maybe_fetch_b_profile(acc_id, account, client, extra)

        if self._check_cancelled():
            return

        # 2. 执行业务流水线（A 型 run_pipeline / B 型按年 run_year_pipeline）
        self._set_phase(acc_id, "assigning" if self._site_profile == "A" else "course_discover")
        try:
            account = self._store.get_account(acc_id) or account
            if self._site_profile == "B":
                result = self._run_b_year_pipeline(account, client)
            else:
                result = self.run_pipeline(account, client)
        except Exception as exc:
            if self._check_cancelled():
                return
            traceback.print_exc()
            result = PipelineResult(
                success=False, final_state="failed",
                status_msg=f"流水线异常: {exc}", error=str(exc),
            )

        if self._check_cancelled():
            return

        # 3. 持久化结果
        self._persist_result(acc_id, result, extra)

    def _maybe_fetch_b_profile(
        self, acc_id: int, account: dict, client, extra: dict,
    ) -> dict:
        """B 型：display_name 为空或与 username 相同时，登录后从站点获取姓名等信息。"""
        display = (account.get("display_name") or "").strip()
        username = (account.get("username") or "").strip()
        if display and display != username:
            return extra

        try:
            profile = self.fetch_member_profile(client) or {}
        except Exception as exc:
            self._set_phase(acc_id, "profile_fetch_failed")
            raise RuntimeError(f"获取账号信息失败：{exc}") from exc

        if not profile:
            raise RuntimeError("获取账号信息失败：站点未返回姓名等资料")

        updates: dict[str, Any] = {}
        name = (
            profile.get("display_name")
            or profile.get("real_name")
            or profile.get("name")
            or ""
        ).strip()
        if name:
            updates["display_name"] = name
            extra["real_name"] = profile.get("real_name") or name

        if profile.get("id_card"):
            extra["id_card"] = profile["id_card"]
        if profile.get("user_profile"):
            extra["user_profile"] = profile["user_profile"]
        for k, v in profile.items():
            if k not in ("display_name", "real_name", "name", "id_card", "user_profile"):
                extra.setdefault(k, v)

        if updates:
            self._store.update_account(acc_id, **updates)
        self._store.update_extra(acc_id, extra)
        return extra

    # ── session 管理 ──────────────────────────────────────────────────────────

    def call_with_session_retry(self, acc_id: int, username: str, password: str,
                                extra: dict, fn) -> Any:
        """业务 HTTP 包装：会话失效自动 relogin 一次（§5.1.1）。"""

        def _persist(new_cookies: dict, user_info: dict | None) -> None:
            extra["cookies"] = new_cookies
            if user_info:
                extra["user_profile"] = user_info
            self._store.update_extra(acc_id, extra)

        return call_with_session_retry(
            self._sm,
            user_id=str(acc_id),
            username=username,
            password=password,
            cookies=extra.get("cookies"),
            fn=fn,
            on_cookies_updated=_persist,
            probe=self.get_session_probe(),
        )

    def _run_b_year_pipeline(self, account: dict, client) -> PipelineResult:
        """B 型：按 target_years_json 顺序执行每年任务。"""
        acc_id = account["id"]
        years_raw = account.get("target_years_json") or "[]"
        try:
            years = json.loads(years_raw) if isinstance(years_raw, str) else list(years_raw)
        except json.JSONDecodeError:
            years = []
        if not years:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            years = [str(datetime.now(tz=ZoneInfo("Asia/Shanghai")).year)]

        logs: list[dict] = []
        for year in years:
            if self._check_cancelled():
                return PipelineResult(False, final_state="failed", status_msg="已取消")
            self._set_phase(acc_id, "video_play")
            extra = json.loads((self._store.get_account(acc_id) or account).get("extra_json") or "{}")
            extra["current_year"] = year
            self._store.update_extra(acc_id, extra)
            yr = self.run_year_pipeline(self._store.get_account(acc_id) or account, client, year)
            logs.extend(yr.logs or [])
            if not yr.success:
                return PipelineResult(
                    success=False,
                    final_state=yr.final_state or "failed",
                    status_msg=yr.status_msg or yr.error or f"{year} 年任务失败",
                    error=yr.error,
                    logs=logs,
                    hard_failure=yr.hard_failure,
                )
        self._set_phase(acc_id, "done")
        return PipelineResult(success=True, final_state="completed", status_msg="全部目标年度完成", logs=logs)

    def _ensure_session(self, acc_id: int, username: str, password: str,
                        cookies) -> tuple:
        user_id = str(acc_id)
        probe = self.get_session_probe()
        _, new_cookies, _, err = self._sm.ensure_session(
            user_id, username, password,
            cookies=cookies,
            probe=probe,
        )
        client = self._sm.get_client(user_id)
        return client, new_cookies, err

    @staticmethod
    def _is_hard_auth_error(err: str) -> bool:
        hard_keywords = ("密码错误", "账号不存在", "账号已锁定", "credentials",
                         "invalid password", "unauthorized", "403")
        err_lower = err.lower()
        return any(k.lower() in err_lower for k in hard_keywords)

    # ── 状态写入 ──────────────────────────────────────────────────────────────

    def _set_phase(self, acc_id: int, phase: str) -> None:
        account = self._store.get_account(acc_id)
        if not account:
            return
        extra = json.loads(account.get("extra_json") or "{}")
        extra["phase"] = phase
        self._store.update_extra(acc_id, extra)

    def _handle_outside_study_hours(self, acc_id: int, msg: str) -> None:
        """非学习时段：暂挂至次日 8–9 点随机恢复，不计入重试次数。"""
        resume_at = next_morning_resume_timestamp()
        resume_text = format_resume_time(resume_at)
        base = msg.strip().rstrip("！!").strip() or "未到学习时间"
        self._store.update_account(
            acc_id,
            status="queued",
            status_msg=f"{base}，将于 {resume_text} 自动恢复",
            retry_count=0,
            queued_at=resume_at,
        )
        self._save_error_log(acc_id)

    def _handle_session_failure(self, acc_id: int, msg: str) -> None:
        """会话失效：清 cookies + 延迟重排队，不计入 MAX_RETRY（§5.1.1）。"""
        account = self._store.get_account(acc_id)
        retry_count = (account or {}).get("retry_count", 0)
        extra = json.loads((account or {}).get("extra_json") or "{}")
        extra.pop("cookies", None)
        self._store.update_extra(acc_id, extra)
        self._sm.remove(str(acc_id))

        resume_at = time.time() + self.RETRY_DELAY
        base = msg.strip().rstrip("！!").strip() or "会话失效"
        self._store.update_account(
            acc_id,
            status="queued",
            status_msg=f"{base}，{int(self.RETRY_DELAY)} 秒后清会话重试",
            retry_count=retry_count,
            queued_at=resume_at,
        )
        self._save_error_log(acc_id)

    def _handle_transient_failure(self, acc_id: int, msg: str) -> None:
        if is_outside_study_hours_error(msg):
            self._handle_outside_study_hours(acc_id, msg)
            return
        if is_transient_session_error(msg):
            self._handle_session_failure(acc_id, msg)
            return
        account = self._store.get_account(acc_id)
        retry_count = (account or {}).get("retry_count", 0) + 1
        if retry_count >= self.MAX_RETRY:
            self._store.update_account_status(acc_id, "failed", msg)
            self._write_run(acc_id, "failed", msg)
            self._save_error_log(acc_id)
        else:
            now = time.time()
            # B 型年度任务：学完一章后应无缝续下一章，失败时立即重新排队而非冷却等待
            queued_at = now if self._site_profile == "B" else now + self.RETRY_DELAY
            self._store.update_account(
                acc_id,
                status="queued",
                status_msg=msg,
                retry_count=retry_count,
                queued_at=queued_at,
            )
            self._save_error_log(acc_id)

    def _persist_result(self, acc_id: int, result: PipelineResult, extra: dict) -> None:
        account = self._store.get_account(acc_id)
        if account:
            extra = json.loads(account.get("extra_json") or "{}")
        if result.extra_updates:
            extra.update(result.extra_updates)
            if result.success:
                extra.pop("phase", None)
                for key in (
                    "current_course_title",
                    "current_chapter_title",
                    "current_chapter_id",
                    "current_chapter_progress",
                    "year_progress_percent",
                ):
                    extra.pop(key, None)
            self._store.update_extra(acc_id, extra)

        summary = result.status_msg or result.error or ""

        if result.success:
            final = result.final_state
            if final == "waiting_apply" and self._has_credit_apply:
                pending = self._store.pending_apply_count(acc_id)
                if pending > 0:
                    self._store.update_account_status(acc_id, "waiting_apply", summary or "等待申请学分")
                    self._write_run(acc_id, "success", summary, result.logs)
                    return
                final = "completed"
            self._store.update_account_status(acc_id, final, summary)
            self._write_run(acc_id, "success", summary, result.logs)
            extra.pop("error_log_text", None)
            self._store.update_extra(acc_id, extra)
        elif is_outside_study_hours_error(summary):
            self._handle_outside_study_hours(acc_id, summary)
            self._write_run(acc_id, "failed", summary, result.logs)
        elif is_transient_session_error(summary):
            self._handle_session_failure(acc_id, summary)
            self._write_run(acc_id, "failed", summary, result.logs)
        elif result.hard_failure:
            self._store.update_account_status(acc_id, "failed", summary)
            self._write_run(acc_id, "failed", summary, result.logs)
            self._save_error_log(acc_id)
        else:
            self._handle_transient_failure(acc_id, summary)
            self._write_run(acc_id, "failed", summary, result.logs)

    def _save_error_log(self, acc_id: int) -> None:
        account = self._store.get_account(acc_id)
        if not account:
            return
        runs = self._store.get_runs(acc_id, limit=1)
        apply_err = ""
        if self._has_credit_apply:
            apply_err = self._store.latest_apply_error(acc_id)
        text = build_error_log_text(account, runs=runs, apply_last_error=apply_err)
        extra = json.loads(account.get("extra_json") or "{}")
        extra["error_log_text"] = text
        self._store.update_extra(acc_id, extra)

    def _write_run(self, acc_id: int, result: str, summary: str,
                   logs: list | None = None) -> None:
        self._store.add_run(
            acc_id,
            started_at=self._started_at,
            ended_at=time.time(),
            result=result,
            summary=summary,
            logs=logs or [],
        )
