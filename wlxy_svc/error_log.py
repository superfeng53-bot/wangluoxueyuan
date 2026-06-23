"""
可复制的账号错误日志（与 excel-spec.md §4、web-ui-spec §6.17 对齐）。
复制到 <svc>/error_log.py，无需修改。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

_STATUS_CN = {
    "queued": "排队",
    "running": "进行中",
    "waiting_apply": "等待申请",
    "completed": "已完成",
    "failed": "失败",
    "paused": "已暂停",
}


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _expand_run_logs(logs_json: str) -> list[str]:
    try:
        logs = json.loads(logs_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    lines: list[str] = []
    if isinstance(logs, list):
        for i, entry in enumerate(logs, start=1):
            if isinstance(entry, dict):
                stage = entry.get("stage", "")
                ok = entry.get("ok", True)
                msg = entry.get("message", "")
                lines.append(f"{i}. [{stage}] {'ok' if ok else 'fail'} {msg}".strip())
            else:
                lines.append(f"{i}. {entry}")
    return lines


def build_error_log_text(
    account: dict[str, Any],
    *,
    runs: list[dict] | None = None,
    apply_last_error: str = "",
) -> str:
    """
    生成 UTF-8 纯文本 error_log_text。
    来源优先级：runs.logs_json → status_msg → extra.phase / apply_queue.last_error
    """
    extra = {}
    try:
        extra = json.loads(account.get("extra_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        pass

    status = account.get("status", "")
    status_cn = _STATUS_CN.get(status, status)
    name = account.get("display_name") or account.get("username") or ""
    username = account.get("username", "")
    status_msg = account.get("status_msg", "")
    phase = extra.get("phase") or extra.get("failed_phase") or ""
    updated = _fmt_ts(account.get("updated_at"))

    latest_run: Optional[dict] = None
    if runs:
        latest_run = runs[0]
    detail_lines: list[str] = []

    if latest_run:
        detail_lines = _expand_run_logs(latest_run.get("logs_json", "[]"))
        if not detail_lines and latest_run.get("summary"):
            detail_lines = [latest_run["summary"]]

    if not detail_lines and status_msg:
        detail_lines = [status_msg]

    if not detail_lines and apply_last_error:
        detail_lines = [f"[apply_queue] {apply_last_error}"]

    if not detail_lines and phase:
        detail_lines = [f"阶段：{phase}"]

    parts = [
        f"【账号】{name} / {username}",
        f"【状态】{status_cn}",
    ]
    if status_msg:
        parts.append(f"【说明】{status_msg}")
    if phase:
        parts.append(f"【阶段】{phase}")
    if updated:
        parts.append(f"【时间】{updated}")
    if latest_run:
        parts.append(
            f"【最近运行】run#{latest_run.get('id', '?')} result={latest_run.get('result', '')}"
        )
    if detail_lines:
        parts.append("--- 明细 ---")
        parts.extend(detail_lines)

    return "\n".join(parts)
