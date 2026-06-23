from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .client import HttpClient
from .responses import require_data, SessionExpiredError, is_session_expired
from .train import TrainChapter, TrainService, YearTrainRecord

# 前端播放页 setInterval(..., 2e4)
SOCKET_REPORT_INTERVAL_NORMAL = 20.0
SOCKET_REPORT_INTERVAL_FAST = 20.0
SOCKET_STEP_NORMAL = 20
SOCKET_STEP_FAST = 20
AUTH_CODE = "Z"
WATCH_THRESHOLD = 0.95
# 本地上报结束后，等待服务端课表同步的最长时间
SERVER_SYNC_MAX_WAIT = 120.0
SERVER_SYNC_POLL_INTERVAL = 3.0
SERVER_SYNC_REEND_INTERVAL = 20.0


@dataclass
class StudyReportResult:
    ok: bool
    study_length: int
    message: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChapterProbeResult:
    ok: bool
    year: int
    chapter_id: str
    study_seconds_before: int = 0
    study_seconds_after: int = 0
    delta: float = 0
    probe_seconds: int = 60
    error: str | None = None
    message: str = ""

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
            "message": self.message,
        }


class StudyService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client
        self.trains = TrainService(client)

    def _interval_and_step(self, report_mode: str) -> tuple[float, int]:
        if report_mode == "fast":
            return SOCKET_REPORT_INTERVAL_FAST, SOCKET_STEP_FAST
        return SOCKET_REPORT_INTERVAL_NORMAL, SOCKET_STEP_NORMAL

    def _resolve_org_id(self, record: YearTrainRecord, session: dict[str, Any]) -> str:
        org_id = session.get("orgId")
        if org_id:
            return str(org_id)
        detail = self.trains.get_train_detail(record.train_id)
        return str(detail.get("orgId") or "")

    def _resolve_current_times(self, session: dict[str, Any], chapter: TrainChapter) -> int:
        """以课表断点作为 socket 上报起点。

        start_training 的 currentTimes / studyLength 为全局播放计数，切换章节时
        会返回其他章节的值，不可用于断点或完成判定。
        """
        duration = chapter.total_length or 1
        if chapter.finished:
            return duration
        return min(max(chapter.study_seconds, 0), duration)

    def _chapter_meets_threshold(self, chapter: TrainChapter | None) -> bool:
        """仅以课表 train_resource_list 的 progress/state 判定章节是否达标。"""
        if chapter is None:
            return False
        if chapter.finished:
            return True
        duration = chapter.total_length or 1
        return chapter.study_seconds >= max(int(duration * WATCH_THRESHOLD), 1)

    def _refresh_chapter(
        self,
        record: YearTrainRecord,
        chapter: TrainChapter,
    ) -> TrainChapter | None:
        """刷新课表上该章节的 progress/state。"""
        return self.trains.find_chapter(record.year, chapter.chapter_id)

    def _wait_server_chapter_complete(
        self,
        record: YearTrainRecord,
        chapter_id: str,
        *,
        chapter: TrainChapter,
        org_id: str,
        current: int,
        last: StudyReportResult,
        max_wait: float = SERVER_SYNC_MAX_WAIT,
    ) -> tuple[TrainChapter | None, StudyReportResult]:
        """本地上报已结束后轮询服务端；完成判定不以本地进度为准。"""
        deadline = time.monotonic() + max(0.0, max_wait)
        next_reend = time.monotonic()
        refreshed: TrainChapter | None = None
        while time.monotonic() < deadline:
            refreshed = self._refresh_chapter(record, chapter)
            if self._chapter_meets_threshold(refreshed):
                return refreshed, last
            now = time.monotonic()
            if now >= next_reend:
                end = self.report_socket_progress(
                    chapter, org_id, current, play_status="end",
                )
                self._raise_if_session_expired(end)
                if end.ok:
                    last = end
                next_reend = now + SERVER_SYNC_REEND_INTERVAL
            time.sleep(SERVER_SYNC_POLL_INTERVAL)
        if refreshed is None:
            refreshed = self.trains.find_chapter(record.year, chapter_id)
        return refreshed, last

    def begin_chapter_session(
        self,
        record: YearTrainRecord,
        chapter: TrainChapter,
    ) -> tuple[dict[str, Any], str, int]:
        """与前端一致：start_training → start_learning → 返回 currentTimes。"""
        session = require_data(
            self.client.api_form_post(
                "/train/train/start_training",
                {"trainId": record.train_id, "trainRecordId": record.train_record_id},
            )
        )
        org_id = self._resolve_org_id(record, session)
        require_data(
            self.client.api_form_post(
                "/train/course/start_learning",
                {
                    "courseId": chapter.course_id,
                    "orgId": org_id,
                    "courseChapterId": chapter.chapter_id,
                },
            )
        )
        current = self._resolve_current_times(session, chapter)
        return session, org_id, current

    def report_socket_progress(
        self,
        chapter: TrainChapter,
        org_id: str,
        current_times: int,
        *,
        play_status: str = "play",
    ) -> StudyReportResult:
        data = self.client.socket_form_post(
            "/train/socket/start_learning_socket",
            {
                "courseChapterId": chapter.chapter_id,
                "orgId": org_id,
                "authCode": AUTH_CODE,
                "currentTimes": int(current_times),
                "playStatus": play_status,
            },
        )
        ok = bool(data.get("success")) and data.get("code") == 0
        if not ok:
            code = data.get("code")
            msg = str(data.get("msg") or "socket 上报失败")
            if code == 512:
                msg = "缺少必传参数（socket 上报）"
            elif code == 511:
                msg = "已在其他客户端观看视频"
            return StudyReportResult(ok=False, study_length=int(current_times), message=msg, raw=data)
        return StudyReportResult(
            ok=True,
            study_length=int(current_times),
            message=str(data.get("msg") or "成功"),
            raw=data,
        )

    def _raise_if_session_expired(self, result: StudyReportResult) -> None:
        if result.ok:
            return
        if is_session_expired(result.message) or is_session_expired(result.raw):
            raise SessionExpiredError(result.message)

    def study_chapter(
        self,
        record: YearTrainRecord,
        chapter: TrainChapter,
        *,
        report_mode: str = "normal",
        report_interval: float | None = None,
        max_reports: int | None = None,
        on_report: Callable[[StudyReportResult], None] | None = None,
    ) -> StudyReportResult:
        if chapter.finished:
            return StudyReportResult(ok=True, study_length=chapter.total_length, message="章节已完成，跳过")

        interval, step = self._interval_and_step(report_mode)
        if report_interval is not None:
            interval = report_interval

        duration = chapter.total_length or 1
        _, org_id, current = self.begin_chapter_session(record, chapter)
        refreshed = self._refresh_chapter(record, chapter)
        if self._chapter_meets_threshold(refreshed or chapter):
            return StudyReportResult(
                ok=True,
                study_length=(refreshed or chapter).study_seconds,
                message="章节已完成，跳过",
            )

        sent = 0
        last = self.report_socket_progress(chapter, org_id, current, play_status="play")
        if on_report:
            on_report(last)
        self._raise_if_session_expired(last)
        if not last.ok:
            return last

        while True:
            refreshed = self._refresh_chapter(record, chapter)
            if self._chapter_meets_threshold(refreshed):
                end = self.report_socket_progress(
                    chapter,
                    org_id,
                    max(current, (refreshed or chapter).study_seconds),
                    play_status="end",
                )
                return end if end.ok else last

            if current >= duration:
                end = self.report_socket_progress(chapter, org_id, current, play_status="end")
                if not end.ok:
                    return end
                last = end
                refreshed, last = self._wait_server_chapter_complete(
                    record,
                    chapter.chapter_id,
                    chapter=chapter,
                    org_id=org_id,
                    current=current,
                    last=last,
                )
                if self._chapter_meets_threshold(refreshed):
                    return last
                progress = refreshed.progress if refreshed else 0.0
                return StudyReportResult(
                    ok=False,
                    study_length=current,
                    message=(
                        f"章节未完成（课表进度 {progress:.0%}，需 ≥{WATCH_THRESHOLD:.0%}；"
                        "以服务端课表为准，将自动重试）"
                    ),
                    raw=last.raw,
                )

            time.sleep(interval)
            current = min(current + step, duration)
            last = self.report_socket_progress(chapter, org_id, current, play_status="play")
            if on_report:
                on_report(last)
            self._raise_if_session_expired(last)
            if not last.ok:
                return last
            sent += 1
            if max_reports is not None and sent >= max_reports:
                refreshed = self._refresh_chapter(record, chapter)
                if self._chapter_meets_threshold(refreshed):
                    return last
                progress = refreshed.progress if refreshed else 0.0
                return StudyReportResult(
                    ok=False,
                    study_length=current,
                    message=f"上报次数已达上限，课表进度 {progress:.0%}",
                    raw=last.raw,
                )

    def probe_chapter_progress(
        self,
        record: YearTrainRecord,
        chapter: TrainChapter,
        *,
        probe_seconds: int = 60,
        min_delta: float = 1,
        report_mode: str = "normal",
    ) -> ChapterProbeResult:
        """进度门禁：socket 上报后以课表列表 progress 增量为准（与页面一致）。"""
        result = ChapterProbeResult(
            ok=False,
            year=record.year,
            chapter_id=chapter.chapter_id,
            probe_seconds=probe_seconds,
        )
        if chapter.finished:
            result.error = "章节已完成，无可探针"
            return result

        interval, step = self._interval_and_step(report_mode)
        before = chapter.study_seconds
        result.study_seconds_before = before

        _, org_id, current = self.begin_chapter_session(record, chapter)
        first = self.report_socket_progress(chapter, org_id, current, play_status="play")
        if not first.ok:
            result.error = first.message
            return result

        deadline = time.monotonic() + max(1, probe_seconds)
        cap = max(int(chapter.total_length * WATCH_THRESHOLD), before + step)
        while time.monotonic() < deadline:
            if time.monotonic() + interval > deadline:
                break
            time.sleep(interval)
            current = min(current + step, cap)
            report = self.report_socket_progress(chapter, org_id, current, play_status="play")
            if not report.ok:
                result.error = report.message or "socket 上报失败"
                return result

        refreshed = self._refresh_chapter(record, chapter)
        after = refreshed.study_seconds if refreshed else current
        result.study_seconds_after = after
        result.delta = after - before
        result.ok = result.delta >= min_delta
        result.message = (
            f"delta={result.delta:.1f}s (before={before}, after={after})"
            if result.ok
            else f"进度增量不足: delta={result.delta} < min_delta={min_delta}"
        )
        if not result.ok:
            result.error = result.message
        return result
