"""按 user_id 隔离 HttpClient，支持 token 复用与登录锁。"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path

from .captcha_limiter import (
    format_cooldown_message,
    get_cooldown_remaining,
)
from .client import HttpClient
from .config import DEFAULT_COOKIES_FILE, DEFAULT_USER_PROFILE_FILE
from .exam import ExamService
from .login import LoginResult, LoginService
from .member import MemberService
from .study import StudyService
from .train import TrainService
from .year_task import YearTaskRunner

_username_locks: dict[str, threading.Lock] = {}
_username_locks_guard = threading.Lock()


def _username_login_lock(username: str) -> threading.Lock:
    with _username_locks_guard:
        if username not in _username_locks:
            _username_locks[username] = threading.Lock()
        return _username_locks[username]


class SessionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._clients: dict[str, HttpClient] = {}

    def get_client(self, user_id: str) -> HttpClient:
        with self._lock:
            if user_id not in self._clients:
                self._clients[user_id] = HttpClient(user_id=user_id)
            return self._clients[user_id]

    def remove(self, user_id: str) -> None:
        with self._lock:
            self._clients.pop(user_id, None)

    def load_user_cookies_file(
        self,
        user_id: str,
        cookies_path: str | Path = DEFAULT_COOKIES_FILE,
    ) -> HttpClient:
        client = self.get_client(user_id)
        cookies = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
        client.load_cookies(cookies)
        if DEFAULT_USER_PROFILE_FILE.exists():
            client.user_profile = json.loads(DEFAULT_USER_PROFILE_FILE.read_text(encoding="utf-8"))
        return client

    def get_member_service(self, user_id: str) -> MemberService:
        return MemberService(self.get_client(user_id))

    def get_train_service(self, user_id: str) -> TrainService:
        return TrainService(self.get_client(user_id))

    def get_study_service(self, user_id: str) -> StudyService:
        return StudyService(self.get_client(user_id))

    def get_exam_service(self, user_id: str) -> ExamService:
        return ExamService(self.get_client(user_id))

    def get_year_task_runner(self, user_id: str) -> YearTaskRunner:
        return YearTaskRunner(self.get_client(user_id))

    def login_user(self, user_id: str, username: str, password: str) -> LoginResult:
        remaining = get_cooldown_remaining()
        if remaining > 0:
            return LoginResult(
                success=False,
                message=format_cooldown_message(remaining),
                rate_limited=True,
                retry_after=remaining,
            )
        with _username_login_lock(username):
            client = self.get_client(user_id)
            return LoginService(client).login(username, password)

    def relogin_user(self, user_id: str, username: str, password: str) -> LoginResult:
        self.remove(user_id)
        return self.login_user(user_id, username, password)

    def ensure_session(
        self,
        user_id: str,
        username: str,
        password: str,
        cookies: dict[str, str] | None = None,
        *,
        probe: Callable[[], None] | None = None,
        require_probe: bool = False,
    ) -> tuple[bool, dict[str, str], dict | None, str | None]:
        """返回 (reused_token, cookies, user_info, error_message)。"""
        if cookies:
            try:
                client = self.get_client(user_id)
                client.load_cookies(cookies)
                if client.is_logged_in():
                    if probe is not None:
                        try:
                            probe()
                        except Exception:
                            if require_probe:
                                raise
                            # probe 失败则走重新登录
                        else:
                            return True, client.export_cookies(), client.user_profile, None
                    else:
                        return True, client.export_cookies(), client.user_profile, None
            except Exception:
                pass

        self.remove(user_id)
        result = self.login_user(user_id, username, password)
        if not result.success:
            self.remove(user_id)
            return False, {}, None, result.message
        return False, result.cookies, dict(result.user_info), None

    def ensure_session_with_member_probe(
        self,
        user_id: str,
        username: str,
        password: str,
        cookies: dict[str, str] | None = None,
    ) -> tuple[bool, dict[str, str], dict | None, str | None]:
        member = self.get_member_service(user_id)

        def _probe() -> None:
            member.get_profile_by_token()

        return self.ensure_session(
            user_id,
            username,
            password,
            cookies,
            probe=_probe,
            require_probe=True,
        )


_default: SessionManager | None = None
_default_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    global _default
    with _default_lock:
        if _default is None:
            _default = SessionManager()
        return _default
