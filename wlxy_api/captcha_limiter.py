"""验证码与登录频率限制（跨进程持久化冷却状态）。"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

CAPTCHA_MAX_ATTEMPTS_PER_LOGIN = 5
GLOBAL_FAILURE_COOLDOWN_SEC = 90.0
MIN_INTERVAL_SEC = 1.2

_STATE_FILE: Path | None = None
_LOCK = threading.Lock()
_STATE: dict[str, float | int] = {
    "last_attempt_ts": 0.0,
    "cooldown_until": 0.0,
    "consecutive_failures": 0,
}


class CaptchaRateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: float = 0.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def configure_state_file(path: Path) -> None:
    """将冷却状态持久化到磁盘，供多进程/重启后共享。"""
    global _STATE_FILE
    _STATE_FILE = path
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                _STATE.update(loaded)
        except Exception:
            pass


def _save() -> None:
    if _STATE_FILE is None:
        return
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(_STATE, ensure_ascii=False), encoding="utf-8")


def get_cooldown_remaining() -> float:
    return max(0.0, float(_STATE["cooldown_until"]) - time.time())


def is_captcha_rate_limited(msg: str | None) -> bool:
    if not msg:
        return False
    text = str(msg)
    keywords = ("过于频繁", "频率过快", "6112", "rate limit", "稍后再试", "请求过于频繁")
    return any(k in text for k in keywords)


def wait_before_captcha(block: bool = True) -> None:
    """在发起验证码获取前强制执行最小间隔与全局冷却。"""
    with _LOCK:
        remaining = get_cooldown_remaining()
        if remaining > 0:
            if block:
                time.sleep(min(remaining, 30))
            else:
                raise CaptchaRateLimitError(
                    f"captcha cooldown: {remaining:.0f}s",
                    retry_after=remaining,
                )
        gap = time.time() - float(_STATE["last_attempt_ts"])
        if gap < MIN_INTERVAL_SEC:
            time.sleep(MIN_INTERVAL_SEC - gap)


def mark_captcha_attempt() -> None:
    with _LOCK:
        _STATE["last_attempt_ts"] = time.time()
        _save()


def report_recognition_failure(msg: str) -> bool:
    """连续识别失败达阈值时触发冷却；返回是否已触发冷却。"""
    _ = msg
    with _LOCK:
        _STATE["consecutive_failures"] = int(_STATE["consecutive_failures"]) + 1
        if int(_STATE["consecutive_failures"]) >= 3:
            _STATE["cooldown_until"] = time.time() + GLOBAL_FAILURE_COOLDOWN_SEC
            _STATE["consecutive_failures"] = 0
            _save()
            return True
        _save()
        return False


def report_recognition_success() -> None:
    with _LOCK:
        _STATE["consecutive_failures"] = 0
        _save()


def report_rate_limited(msg: str, *, cooldown_sec: float = GLOBAL_FAILURE_COOLDOWN_SEC) -> float:
    _ = msg
    with _LOCK:
        _STATE["cooldown_until"] = time.time() + cooldown_sec
        _save()
        return cooldown_sec


def format_cooldown_message(remaining: float) -> str:
    return f"验证码冷却中，还需 {remaining:.0f}s"


def state_snapshot() -> dict:
    with _LOCK:
        return dict(_STATE)
