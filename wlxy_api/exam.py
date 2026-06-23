from __future__ import annotations

from typing import Any

from .client import HttpClient
from .responses import parse_exam_response, require_data


class ExamService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def list_my_exams(
        self,
        *,
        exam_type: int = 1,
        page_num: int = 1,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        """type: 1=未考, 2=已考"""
        data = require_data(
            self.client.api_get_safe(
                "/train/exam/my_exam_list",
                {"type": exam_type, "pageNum": page_num, "pageSize": page_size},
            )
        )
        block = data.get("data") if isinstance(data, dict) else {}
        return list(block.get("result") or [])

    def query_exam(self, exam_id: str) -> dict[str, Any]:
        data = self.client.api_get_safe("/train/exam/query_exam", {"examId": exam_id})
        parsed = parse_exam_response(data)
        if not parsed.ok:
            raise RuntimeError(parsed.message)
        return require_data(data)
