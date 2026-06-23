from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import urlencode

import requests

from .config import (
    API_BASE_URL,
    BASE_URL,
    DEFAULT_DEVICE,
    DEFAULT_HIERARCHY,
    DEFAULT_USER_AGENT,
    TOKEN_COOKIE_KEY,
)


class HttpClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        api_base_url: str = API_BASE_URL,
        user_id: str | None = None,
        *,
        device: str = DEFAULT_DEVICE,
        hierarchy: str = DEFAULT_HIERARCHY,
    ) -> None:
        self.user_id = user_id or str(id(self))
        self.base_url = base_url.rstrip("/")
        self.api_base_url = api_base_url.rstrip("/")
        self.device = device
        self.hierarchy = hierarchy
        self.token: str | None = None
        self.user_profile: dict[str, Any] | None = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": f"{self.base_url}/",
        })

    def set_token(self, token: str | None) -> None:
        self.token = token or None

    def load_cookies(self, cookies: dict[str, str]) -> None:
        self.session.cookies.clear()
        for k, v in cookies.items():
            if k == TOKEN_COOKIE_KEY:
                self.set_token(v)
            else:
                self.session.cookies.set(k, v)
        if TOKEN_COOKIE_KEY in cookies:
            self.set_token(cookies[TOKEN_COOKIE_KEY])

    def export_cookies(self) -> dict[str, str]:
        out = self.session.cookies.get_dict()
        if self.token:
            out[TOKEN_COOKIE_KEY] = self.token
        if self.user_profile and self.user_profile.get("userId"):
            out["user_id"] = str(self.user_profile["userId"])
        return out

    def _common_params(self) -> dict[str, str]:
        params: dict[str, str] = {
            "device": self.device,
            "hierarchy": self.hierarchy,
        }
        if self.token:
            params["token"] = self.token
        return params

    @staticmethod
    def _should_retry_request(exc: Exception) -> bool:
        if isinstance(exc, requests.HTTPError):
            resp = exc.response
            if resp is not None and 400 <= resp.status_code < 500:
                return False
        return isinstance(exc, requests.RequestException)

    @staticmethod
    def _backoff_sleep(attempt_index: int, *, jitter: bool = False) -> None:
        delay = 2.0 * (2 ** attempt_index)
        if jitter:
            delay += random.uniform(0.0, 0.5)
        time.sleep(delay)

    def api_form_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {**payload, **self._common_params()}
        r = self.session.post(
            f"{self.api_base_url}{path}",
            data=urlencode(body),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def socket_form_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """播放进度 socket 接口：仅发送前端 FormData 字段，不可附带 device/hierarchy。"""
        if not self.token and "token" not in payload:
            raise RuntimeError("缺少 token，无法上报播放进度")
        body = dict(payload)
        body.setdefault("token", self.token or "")
        r = self.session.post(
            f"{self.api_base_url}{path}",
            data=body,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def api_form_post_safe(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        attempts: int = 3,
    ) -> dict[str, Any]:
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self.api_form_post(path, payload)
            except requests.RequestException as exc:
                last = exc
                if not self._should_retry_request(exc) or i + 1 == attempts:
                    break
                self._backoff_sleep(i)
        raise last  # type: ignore[misc]

    def api_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = {**(params or {}), **self._common_params()}
        r = self.session.get(
            f"{self.api_base_url}{path}",
            params=merged,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def api_get_safe(self, path: str, params: dict[str, Any] | None = None, *, attempts: int = 4) -> dict[str, Any]:
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self.api_get(path, params)
            except requests.RequestException as exc:
                last = exc
                if not self._should_retry_request(exc) or i + 1 == attempts:
                    break
                self._backoff_sleep(i, jitter=True)
        raise last  # type: ignore[misc]

    def json_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self.session.post(
            f"{self.base_url}{path}",
            json=payload,
            headers={"Content-Type": "application/json;charset=UTF-8"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def json_post_safe(self, path: str, payload: dict[str, Any], *, attempts: int = 3) -> dict[str, Any]:
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self.json_post(path, payload)
            except requests.RequestException as exc:
                last = exc
                if not self._should_retry_request(exc) or i + 1 == attempts:
                    break
                self._backoff_sleep(i)
        raise last  # type: ignore[misc]

    def form_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self.session.post(f"{self.base_url}{path}", data=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def form_post_safe(self, path: str, payload: dict[str, Any], *, attempts: int = 3) -> dict[str, Any]:
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self.form_post(path, payload)
            except requests.RequestException as exc:
                last = exc
                if not self._should_retry_request(exc) or i + 1 == attempts:
                    break
                self._backoff_sleep(i)
        raise last  # type: ignore[misc]

    def form_get_html(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        attempts: int = 4,
    ) -> str:
        last: Exception | None = None
        for i in range(attempts):
            try:
                r = self.session.get(
                    f"{self.base_url}{path}",
                    params=params,
                    timeout=30,
                )
                r.raise_for_status()
                return r.text
            except requests.RequestException as exc:
                last = exc
                if not self._should_retry_request(exc) or i + 1 == attempts:
                    break
                self._backoff_sleep(i, jitter=True)
        raise last  # type: ignore[misc]

    def is_logged_in(self) -> bool:
        if not self.token:
            return False
        try:
            resp = self.api_get_safe("/user/user/get_userByToken")
        except requests.RequestException:
            return False
        return bool(resp.get("success") and resp.get("code") == 0)
