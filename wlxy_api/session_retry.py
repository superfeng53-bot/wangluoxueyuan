"""业务调用中的会话失效检测与一次重登重试。"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from .responses import is_session_expired

T = TypeVar("T")

POST_RELOGIN_DELAY_SEC = 1.0


def call_with_session_retry(
    session_manager,
    *,
    user_id: str,
    username: str,
    password: str,
    cookies: dict | None,
    fn: Callable[[Any], T],
    on_cookies_updated: Callable[[dict, dict | None], None] | None = None,
    probe: Callable[[], None] | None = None,
    post_login_delay: float = POST_RELOGIN_DELAY_SEC,
) -> T:
    """执行 fn(client)。会话失效时 relogin 一次后重试 fn 一次。"""
    client = session_manager.get_client(user_id)
    if cookies:
        client.load_cookies(cookies)

    def _run() -> T:
        return fn(client)

    try:
        return _run()
    except Exception as exc:
        if not is_session_expired(exc):
            raise
        first_err = exc

    login_result = session_manager.relogin_user(user_id, username, password)
    if not login_result.success:
        msg = login_result.message or str(first_err)
        raise RuntimeError(f"自动重登失败: {msg}") from first_err

    client = session_manager.get_client(user_id)
    new_cookies = login_result.cookies or client.export_cookies()
    if on_cookies_updated and new_cookies:
        on_cookies_updated(new_cookies, login_result.user_info)

    if post_login_delay > 0:
        time.sleep(post_login_delay)

    if probe is not None:
        try:
            probe()
        except Exception as exc_probe:
            if is_session_expired(exc_probe):
                raise RuntimeError(f"重登后探活失败: {exc_probe}") from exc_probe
            raise

    try:
        return _run()
    except Exception as exc2:
        if is_session_expired(exc2):
            raise RuntimeError(f"重登后仍会话失效: {exc2}") from exc2
        raise
