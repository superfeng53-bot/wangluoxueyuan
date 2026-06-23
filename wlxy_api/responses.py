from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SessionExpiredError(PermissionError):
    """业务 API 返回 token 失效或未登录。"""


_SESSION_KEYWORDS = (
    "未登录",
    "nologin",
    "会话已失效",
    "cookie 无效",
    "session expired",
    "登录超时",
    "token验证过期",
    "token 失效",
    "请重新登录",
)


def is_session_expired(exc_or_msg: Any) -> bool:
    if isinstance(exc_or_msg, (PermissionError, SessionExpiredError)):
        return True
    if isinstance(exc_or_msg, ApiResponse):
        if exc_or_msg.code in (401, "401"):
            return True
        return is_session_expired(exc_or_msg.message)
    if isinstance(exc_or_msg, dict):
        code = exc_or_msg.get("code")
        if code in (401, "401"):
            return True
        return is_session_expired(exc_or_msg.get("msg"))
    text = str(exc_or_msg or "").lower()
    return any(m.lower() in text for m in _SESSION_KEYWORDS)


_TRANSIENT_SESSION_MARKERS = (
    "重登后仍会话失效",
    "重登后探活失败",
    "自动重登失败",
)


def is_transient_session_error(msg: Any) -> bool:
    """Worker 层可重试的会话失效（含一次业务内重登仍失败）。"""
    if not msg:
        return False
    if is_session_expired(msg):
        return True
    text = str(msg)
    return any(m in text for m in _TRANSIENT_SESSION_MARKERS)


@dataclass
class ApiResponse:
    ok: bool
    raw: dict[str, Any]
    message: str
    code: str | int | None = None
    hint: str = ""


LOGIN_CODE_HINTS: dict[str | int, str] = {
    401: "token 失效，请重新登录",
    -997: "需要短信验证码",
    -998: "需要绑定手机号",
}

TRAIN_CODE_HINTS: dict[str | int, str] = {
    3338: "培训 id 不能为空",
    3353: "资源已下线或删除",
}

EXAM_CODE_HINTS: dict[str | int, str] = {
    3353: "考试资源已下线或删除",
}


def _as_code(value: Any) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, (int, str)):
        return value
    return str(value)


def is_api_success(data: dict[str, Any]) -> bool:
    return bool(data.get("success")) and data.get("code") == 0


def parse_cdwork_response(
    data: dict[str, Any],
    *,
    ok_msg: str = "成功",
    hints: dict[str | int, str] | None = None,
) -> ApiResponse:
    code = _as_code(data.get("code"))
    msg = str(data.get("msg") or "")
    ok = is_api_success(data)
    hint = ""
    if hints and code is not None:
        hint = hints.get(code, hints.get(str(code), ""))
    return ApiResponse(
        ok=ok,
        raw=data,
        message=msg or (ok_msg if ok else "请求失败"),
        code=code,
        hint=hint,
    )


def parse_member_response(data: dict[str, Any], *, ok_msg: str = "成功") -> ApiResponse:
    return parse_cdwork_response(data, ok_msg=ok_msg, hints=LOGIN_CODE_HINTS)


def parse_train_response(data: dict[str, Any], *, ok_msg: str = "成功") -> ApiResponse:
    return parse_cdwork_response(data, ok_msg=ok_msg, hints=TRAIN_CODE_HINTS)


def parse_exam_response(data: dict[str, Any], *, ok_msg: str = "成功") -> ApiResponse:
    return parse_cdwork_response(data, ok_msg=ok_msg, hints=EXAM_CODE_HINTS)


def require_data(data: dict[str, Any]) -> Any:
    parsed = parse_cdwork_response(data)
    if not parsed.ok:
        if is_session_expired(parsed) or is_session_expired(data):
            raise SessionExpiredError(parsed.message or "会话已失效，请重新登录")
        raise RuntimeError(parsed.message or "API 请求失败")
    return data.get("data")
