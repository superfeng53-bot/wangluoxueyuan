from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .captcha_limiter import is_captcha_rate_limited, report_rate_limited
from .client import HttpClient
from .config import DEFAULT_HIERARCHY, TOKEN_COOKIE_KEY


def md5_password(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest().upper()


@dataclass
class LoginResult:
    success: bool
    message: str
    session_key: str | None = None
    user_info: dict[str, Any] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict)
    hint: str = ""
    rate_limited: bool = False
    retry_after: float = 0.0


class LoginService:
    LOGIN_PATH = "/user/user/user_login"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    @staticmethod
    def _hint(code_or_msg: str) -> str:
        text = str(code_or_msg or "").strip()
        mapping = {
            "401": "token 已过期，请重新登录",
            "密码错误": "请核对账号与密码",
            "用户不存在": "账号未注册或填写错误",
        }
        return mapping.get(text, "")

    def login(self, username: str, password: str) -> LoginResult:
        payload = {
            "phone": username,
            "password": md5_password(password),
            "device": self.client.device,
            "hierarchy": self.client.hierarchy or DEFAULT_HIERARCHY,
        }
        try:
            resp = self.client.api_form_post_safe(self.LOGIN_PATH, payload)
        except Exception as exc:
            return LoginResult(
                success=False,
                message=str(exc),
                hint="检查网络或 API 是否可达",
            )

        if resp.get("success") and resp.get("code") == 0:
            data = resp.get("data") or {}
            token = str(data.get("token") or "")
            self.client.set_token(token)
            self.client.user_profile = data
            cookies = {TOKEN_COOKIE_KEY: token}
            if data.get("userId"):
                cookies["user_id"] = str(data["userId"])
            return LoginResult(
                success=True,
                message=str(resp.get("msg") or "登录成功"),
                session_key=token,
                user_info=data,
                cookies=cookies,
                raw_response=resp,
            )

        msg = str(resp.get("msg") or "登录失败")
        code = resp.get("code")
        if is_captcha_rate_limited(msg):
            retry_after = report_rate_limited(msg)
            return LoginResult(
                success=False,
                message=msg,
                raw_response=resp,
                hint="登录请求过于频繁，请稍后再试",
                rate_limited=True,
                retry_after=retry_after,
            )
        hint = self._hint(str(code) if code not in (None, 0) else msg)
        return LoginResult(
            success=False,
            message=msg,
            raw_response=resp,
            hint=hint,
        )
