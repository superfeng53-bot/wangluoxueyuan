from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .captcha_limiter import is_captcha_rate_limited, report_rate_limited
from .client import HttpClient
from .config import DEFAULT_HIERARCHY, TOKEN_COOKIE_KEY

# 2026 起登录接口升级为国密加密（见 docs/LOGIN_FLOW.md 第 2 节）：
# cipherData = SM2({phone, password: md5大写, isAdmin: 1})，mode=C1C3C2
# signature  = HMAC-SM3(key=SM3_KEY_HEX, msg=phone + md5大写)
SM2_PUBLIC_KEY = (
    "04eea86cf0ed72c612ef945320ac127cb28749c20117ed682c4d1072aaf42ec"
    "a6d8176ce1200cc0f15150c94f97f0160cff62c56d9eb5783a0f4f18042f726bd8f"
)
SM3_HMAC_KEY_HEX = "e29544dd73f460f73611dfbc0bc757dc"


def md5_password(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest().upper()


def _sm3_hex(data: bytes) -> str:
    from gmssl import func
    from gmssl.sm3 import sm3_hash

    return sm3_hash(func.bytes_to_list(data))


def hmac_sm3(key: bytes, msg: bytes) -> str:
    block = 64
    k = key if len(key) <= block else bytes.fromhex(_sm3_hex(key))
    k = k.ljust(block, b"\x00")
    inner = bytes(b ^ 0x36 for b in k)
    outer = bytes(b ^ 0x5C for b in k)
    return _sm3_hex(outer + bytes.fromhex(_sm3_hex(inner + msg)))


def sm2_encrypt_hex(plaintext: bytes) -> str:
    from gmssl import sm2

    crypt = sm2.CryptSM2(private_key="", public_key=SM2_PUBLIC_KEY, mode=1)
    return "04" + crypt.encrypt(plaintext).hex()


def build_login_payload(phone: str, password: str, hierarchy: str) -> dict[str, Any]:
    md5pwd = md5_password(password)
    plain = json.dumps(
        {"phone": phone, "password": md5pwd, "isAdmin": 1},
        separators=(",", ":"),
    )
    return {
        "cipherData": sm2_encrypt_hex(plain.encode("utf-8")),
        "signature": hmac_sm3(
            bytes.fromhex(SM3_HMAC_KEY_HEX), (phone + md5pwd).encode("utf-8")
        ),
        "device": "2",
        "hierarchy": hierarchy,
    }


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
        payload = build_login_payload(
            username, password, self.client.hierarchy or DEFAULT_HIERARCHY
        )
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
