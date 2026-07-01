from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .client import HttpClient
from .exam import ExamService
from .session_retry import call_with_session_retry
from .study import StudyService
from .train import TrainChapter, TrainService, YearTrainRecord, chapter_progress_snapshot


@dataclass
class StageLog:
    stage: str
    ok: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProgressProbeResult:
    ok: bool
    year: int
    chapter_id: str = ""
    study_seconds_before: int = 0
    study_seconds_after: int = 0
    delta: float = 0
    probe_seconds: int = 60
    error: str | None = None
    logs: list[StageLog] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "year": self.year,
            "chapter_id": self.chapter_id,
            "study_seconds_before": self.study_seconds_before,
            "study_seconds_after": self.study_seconds_after,
            "delta": self.delta,
            "probe_seconds": self.probe_seconds,
            "error": self.error,
            "logs": [log.__dict__ for log in self.logs],
        }


@dataclass
class YearTaskResult:
    ok: bool
    year: int
    message: str
    chapters_total: int = 0
    chapters_done: int = 0
    year_completed: bool = False
    exam_required: bool = False
    exam_cleared: bool = True
    skipped: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)
    logs: list[StageLog] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "year": self.year,
            "message": self.message,
            "chapters_total": self.chapters_total,
            "chapters_done": self.chapters_done,
            "year_completed": self.year_completed,
            "exam_required": self.exam_required,
            "exam_cleared": self.exam_cleared,
            "skipped": self.skipped,
            "details": self.details,
            "logs": [log.__dict__ for log in self.logs],
            "error": self.error,
        }


class YearTaskRunner:
    """B 型公需年度单账号流水线。"""

    def __init__(self, client: HttpClient) -> None:
        self.client = client
        self.trains = TrainService(client)
        self.study = StudyService(client)
        self.exams = ExamService(client)

    def _first_pending_chapter(self, year: int) -> tuple[YearTrainRecord, TrainChapter] | None:
        record = self.trains.get_year_record(year)
        if record is None:
            return None
        for chapter in self.trains.list_year_chapters(year):
            if not chapter.finished:
                return record, chapter
        return None

    def probe_progress(
        self,
        year: int | str,
        *,
        probe_seconds: int = 60,
        min_delta: float = 1,
        report_mode: str = "normal",
    ) -> ProgressProbeResult:
        year_value = int(str(year).strip())
        result = ProgressProbeResult(ok=False, year=year_value, probe_seconds=probe_seconds)
        pair = self._first_pending_chapter(year_value)
        if pair is None:
            record = self.trains.get_year_record(year_value)
            if record is None:
                result.error = f"未报名 {year_value} 年度培训"
            elif record.completed:
                result.ok = True
                result.logs.append(StageLog("probe", True, f"{year_value} 年度已完成，跳过探针"))
            else:
                result.error = f"{year_value} 年度无待学章节"
            return result

        record, chapter = pair
        result.chapter_id = chapter.chapter_id
        probe = self.study.probe_chapter_progress(
            record,
            chapter,
            probe_seconds=probe_seconds,
            min_delta=min_delta,
            report_mode=report_mode,
        )
        result.study_seconds_before = probe.study_seconds_before
        result.study_seconds_after = probe.study_seconds_after
        result.delta = probe.delta
        result.ok = probe.ok
        result.error = probe.error
        result.logs.append(StageLog("probe", probe.ok, probe.message))
        return result

    def run_year_task(
        self,
        year: int | str,
        *,
        report_mode: str = "normal",
        dry_run: bool = False,
        max_chapters: int | None = None,
        max_reports_per_chapter: int | None = None,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> YearTaskResult:
        year_value = int(str(year).strip())
        record = self.trains.get_year_record(year_value)
        if record is None:
            return YearTaskResult(
                ok=False,
                year=year_value,
                message=f"未报名 {year_value} 年度培训（不在 my_train 列表）",
                error=f"未报名 {year_value} 年度培训",
            )
        if record.completed:
            return YearTaskResult(
                ok=True,
                year=year_value,
                message=f"{year_value} 年度已完成",
                skipped=True,
                year_completed=True,
                logs=[StageLog("year_check", True, "年度进度已达标")],
            )

        chapters = [c for c in self.trains.list_year_chapters(year_value) if not c.finished]
        if max_chapters is not None:
            chapters = chapters[: max_chapters]

        if dry_run:
            return YearTaskResult(
                ok=True,
                year=year_value,
                message=f"dry_run: {len(chapters)} 个待学章节",
                chapters_total=len(chapters),
                logs=[StageLog("dry_run", True, f"待学 {len(chapters)} 章")],
            )

        details: list[dict[str, Any]] = []
        logs: list[StageLog] = []
        done = 0

        def _emit_progress(chapter: TrainChapter) -> None:
            if not on_progress:
                return
            snap = chapter_progress_snapshot(chapter)
            record_now = self.trains.get_year_record(year_value)
            if record_now:
                snap["year_progress_percent"] = min(
                    100, max(0, int(round(record_now.progress * 100))),
                )
            on_progress(snap)

        for chapter in chapters:
            _emit_progress(chapter)

            def _on_report(result) -> None:
                refreshed = self.trains.find_chapter(year_value, chapter.chapter_id)
                base = refreshed or chapter
                snap = chapter_progress_snapshot(
                    base,
                    study_length=result.study_length if result.ok else None,
                )
                record_now = self.trains.get_year_record(year_value)
                if record_now:
                    snap["year_progress_percent"] = min(
                        100, max(0, int(round(record_now.progress * 100))),
                    )
                if on_progress:
                    on_progress(snap)

            result = self.study.study_chapter(
                record,
                chapter,
                report_mode=report_mode,
                max_reports=max_reports_per_chapter,
                on_report=_on_report,
            )
            entry = {
                "chapter": chapter.to_dict(),
                "report_ok": result.ok,
                "study_length": result.study_length,
                "msg": result.message,
            }
            details.append(entry)
            logs.append(StageLog(f"chapter:{chapter.chapter_id}", result.ok, result.message))
            if not result.ok:
                return YearTaskResult(
                    ok=False,
                    year=year_value,
                    message=result.message,
                    chapters_total=len(chapters),
                    chapters_done=done,
                    details=details,
                    logs=logs,
                    error=result.message,
                )
            done += 1

        pending_exams = self.exams.list_my_exams(exam_type=1)
        exam_required = bool(pending_exams)
        if exam_required:
            logs.append(StageLog("exam", False, f"仍有 {len(pending_exams)} 场待考"))
            return YearTaskResult(
                ok=False,
                year=year_value,
                message=f"仍有 {len(pending_exams)} 场待考，需实现交卷流程",
                chapters_total=len(chapters),
                chapters_done=done,
                exam_required=True,
                exam_cleared=False,
                details=details,
                logs=logs,
                error="待考未处理",
            )
        logs.append(StageLog("exam", True, "site has no exam flow"))

        year_completed = self.trains.is_year_completed(year_value)
        refreshed = self.trains.get_year_record(year_value)
        progress = refreshed.progress if refreshed else 0.0
        pending = [c for c in self.trains.list_year_chapters(year_value) if not c.finished]
        if not year_completed:
            return YearTaskResult(
                ok=False,
                year=year_value,
                message=f"{year_value} 年度未完成（进度 {progress:.0%}，剩余 {len(pending)} 章）",
                chapters_total=len(chapters),
                chapters_done=done,
                year_completed=False,
                exam_required=False,
                exam_cleared=True,
                details=details,
                logs=logs,
                error=f"剩余 {len(pending)} 章待学",
            )
        return YearTaskResult(
            ok=True,
            year=year_value,
            message=f"{year_value} 年度已完成（进度 {progress:.0%}）",
            chapters_total=len(chapters),
            chapters_done=done,
            year_completed=True,
            exam_required=False,
            exam_cleared=True,
            details=details,
            logs=logs,
        )

    def run_year_task_with_retry(
        self,
        session_manager,
        *,
        user_id: str,
        username: str,
        password: str,
        cookies: dict[str, str] | None,
        on_cookies_updated: Callable[[dict[str, str], dict | None], None] | None = None,
        **kwargs: Any,
    ) -> YearTaskResult:
        """带会话失效自动重登的年度任务执行。"""

        def _run(client: HttpClient) -> YearTaskResult:
            return YearTaskRunner(client).run_year_task(**kwargs)

        year = kwargs.get("year")
        if year is None:
            raise ValueError("run_year_task_with_retry 需要 year 参数")

        try:
            return call_with_session_retry(
                session_manager,
                user_id=user_id,
                username=username,
                password=password,
                cookies=cookies,
                fn=lambda _client: _run(_client),
                on_cookies_updated=on_cookies_updated,
            )
        except Exception as exc:
            year_value = int(str(year).strip())
            return YearTaskResult(
                ok=False,
                year=year_value,
                message=str(exc),
                error=str(exc),
                logs=[StageLog("runner", False, str(exc))],
            )

    def probe_progress_with_retry(
        self,
        session_manager,
        *,
        user_id: str,
        username: str,
        password: str,
        cookies: dict[str, str] | None,
        on_cookies_updated: Callable[[dict[str, str], dict | None], None] | None = None,
        year: int | str,
        probe_seconds: int = 60,
        min_delta: float = 1,
        report_mode: str = "normal",
    ) -> ProgressProbeResult:
        def _run(client: HttpClient) -> ProgressProbeResult:
            return YearTaskRunner(client).probe_progress(
                year,
                probe_seconds=probe_seconds,
                min_delta=min_delta,
                report_mode=report_mode,
            )

        try:
            return call_with_session_retry(
                session_manager,
                user_id=user_id,
                username=username,
                password=password,
                cookies=cookies,
                fn=lambda _client: _run(_client),
                on_cookies_updated=on_cookies_updated,
            )
        except Exception as exc:
            year_value = int(str(year).strip())
            result = ProgressProbeResult(ok=False, year=year_value, error=str(exc))
            result.logs.append(StageLog("probe", False, str(exc)))
            return result
