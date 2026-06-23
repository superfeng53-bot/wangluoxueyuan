from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .client import HttpClient
from .responses import require_data

YEAR_PATTERN = re.compile(r"(20\d{2})")


@dataclass
class YearTrainRecord:
    year: int
    train_id: str
    train_record_id: str
    title: str
    progress: float
    state: int
    length: int
    raw: dict[str, Any] = field(repr=False)

    @property
    def completed(self) -> bool:
        return self.progress >= 1.0 or self.state == 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "train_id": self.train_id,
            "train_record_id": self.train_record_id,
            "title": self.title,
            "progress": self.progress,
            "state": self.state,
            "length": self.length,
            "completed": self.completed,
        }


@dataclass
class TrainChapter:
    chapter_id: str
    course_id: str
    title: str
    total_length: int
    state: int
    progress: float
    resource_id: str
    resource_title: str
    file_id: str = ""
    app_id: str = ""

    @property
    def finished(self) -> bool:
        return self.state == 3 or self.progress >= 1.0

    @property
    def study_seconds(self) -> int:
        """当前已学秒数（由 progress 比例 × total_length 推算）。"""
        if self.finished:
            return self.total_length
        if self.progress <= 0:
            return 0
        if self.progress <= 1.0:
            return int(self.total_length * self.progress)
        return int(self.progress)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "course_id": self.course_id,
            "title": self.title,
            "total_length": self.total_length,
            "state": self.state,
            "progress": self.progress,
            "resource_id": self.resource_id,
            "resource_title": self.resource_title,
            "file_id": self.file_id,
            "app_id": self.app_id,
            "finished": self.finished,
        }


def chapter_progress_snapshot(
    chapter: TrainChapter,
    *,
    study_length: int | None = None,
) -> dict[str, Any]:
    """章节进度快照。

    - 拉取/展示服务端进度：server_chapter_progress、无 study_length 时的 current_chapter_progress
    - 上报过程中可用本地 currentTimes 估算展示进度（study_length 有值时取较大值）
    - 章节是否完成须以服务端课表为准，不由本地进度判定
    """
    total = chapter.total_length or 1
    if chapter.progress <= 1.0:
        server_pct = min(100, max(0, int(round(chapter.progress * 100))))
    else:
        server_pct = min(100, max(0, int(round(100 * chapter.study_seconds / total))))
    if study_length is not None:
        local_pct = min(100, max(0, int(round(100 * study_length / total))))
        display_pct = max(server_pct, local_pct)
    else:
        local_pct = None
        display_pct = server_pct
    course = (chapter.resource_title or chapter.title or "").strip()
    section = (chapter.title or "").strip()
    snap: dict[str, Any] = {
        "current_course_title": course,
        "current_chapter_title": section,
        "current_chapter_id": chapter.chapter_id,
        "server_chapter_progress": server_pct,
        "current_chapter_progress": display_pct,
    }
    if local_pct is not None:
        snap["local_chapter_progress"] = local_pct
    return snap


def extract_year(text: str) -> int | None:
    match = YEAR_PATTERN.search(text or "")
    return int(match.group(1)) if match else None


class TrainService:
    """B 型年度培训：my_train → train_resource_list。"""

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def list_my_trains(
        self,
        *,
        state: int = 1,
        page_num: int = 1,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        data = require_data(
            self.client.api_get_safe(
                "/train/train/my_train",
                {"state": state, "pageNum": page_num, "pageSize": page_size},
            )
        )
        block = data.get("data") if isinstance(data, dict) else {}
        return list(block.get("result") or [])

    def list_yearly_trains(self, *, state: int = 1) -> list[YearTrainRecord]:
        items: list[YearTrainRecord] = []
        for row in self.list_my_trains(state=state):
            year = extract_year(str(row.get("trainTitle") or ""))
            if year is None:
                continue
            items.append(
                YearTrainRecord(
                    year=year,
                    train_id=str(row.get("trainId") or ""),
                    train_record_id=str(row.get("trainRecordId") or ""),
                    title=str(row.get("trainTitle") or ""),
                    progress=float(row.get("progress") or 0),
                    state=int(row.get("state") or 0),
                    length=int(row.get("length") or 0),
                    raw=row,
                )
            )
        items.sort(key=lambda x: x.year, reverse=True)
        return items

    def get_year_record(self, year: int | str, *, state: int = 1) -> YearTrainRecord | None:
        year_value = int(str(year).strip())
        for item in self.list_yearly_trains(state=state):
            if item.year == year_value:
                return item
        return None

    def get_train_detail(self, train_id: str) -> dict[str, Any]:
        return require_data(
            self.client.api_get_safe("/train/train/query_train", {"trainId": train_id})
        )

    def list_train_resources(
        self,
        train_id: str,
        *,
        page_num: int = 1,
        page_size: int = 99,
    ) -> list[dict[str, Any]]:
        data = require_data(
            self.client.api_get_safe(
                "/train/train/train_resource_list",
                {
                    "trainId": train_id,
                    "pageNum": page_num,
                    "pageSize": page_size,
                    "sortBy": "true",
                    "sortField": "sort",
                    "isXcx": 0,
                },
            )
        )
        return list(data.get("result") or [])

    def list_year_chapters(self, year: int | str) -> list[TrainChapter]:
        record = self.get_year_record(year)
        if record is None:
            raise RuntimeError(f"未找到 {year} 年度培训报名记录")
        chapters: list[TrainChapter] = []
        for resource in self.list_train_resources(record.train_id):
            if str(resource.get("type")) != "1":
                continue
            resource_id = str(resource.get("trainResourceId") or resource.get("resourceId") or "")
            resource_title = str(resource.get("trainResourceTitle") or "")
            for ch in resource.get("listChapter") or []:
                chapters.append(
                    TrainChapter(
                        chapter_id=str(ch.get("courseChapterId") or ""),
                        course_id=str(ch.get("courseId") or resource.get("resourceId") or ""),
                        title=str(ch.get("courseChapterTitle") or ""),
                        total_length=int(ch.get("totalLength") or 0),
                        state=int(ch.get("state") or 0),
                        progress=float(ch.get("progress") or 0),
                        resource_id=resource_id,
                        resource_title=resource_title,
                        file_id=str(ch.get("fileId") or ""),
                        app_id=str(resource.get("appId") or ""),
                    )
                )
        return chapters

    def is_year_completed(self, year: int | str) -> bool:
        record = self.get_year_record(year)
        return bool(record and record.completed)

    def find_chapter(self, year: int | str, chapter_id: str) -> TrainChapter | None:
        target = str(chapter_id)
        for chapter in self.list_year_chapters(year):
            if chapter.chapter_id == target:
                return chapter
        return None

    def start_training(self, train_id: str, train_record_id: str) -> dict[str, Any]:
        return require_data(
            self.client.api_form_post(
                "/train/train/start_training",
                {"trainId": train_id, "trainRecordId": train_record_id},
            )
        )
