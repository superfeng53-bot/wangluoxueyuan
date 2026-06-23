"""非学习时段错误识别与次日晨间恢复调度。"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
MORNING_HOUR = 8
MORNING_WINDOW_SEC = 3600  # 8:00–9:00 内随机

_OUTSIDE_STUDY_HOURS = re.compile(r"未到\s*学习\s*时间")


def is_outside_study_hours_error(msg: str) -> bool:
    return bool(msg and _OUTSIDE_STUDY_HOURS.search(msg))


def next_morning_resume_timestamp(*, now: datetime | None = None) -> float:
    """返回下一次 8:00–9:00（上海时区）内的随机 Unix 时间戳。"""
    now = now or datetime.now(tz=TZ)
    day_start = now.replace(hour=MORNING_HOUR, minute=0, second=0, microsecond=0)
    window_end = day_start + timedelta(seconds=MORNING_WINDOW_SEC)

    if now >= window_end:
        day_start += timedelta(days=1)
        offset = random.randint(0, MORNING_WINDOW_SEC - 1)
        return (day_start + timedelta(seconds=offset)).timestamp()

    if now >= day_start:
        remaining = max(60, int((window_end - now).total_seconds()) - 1)
        offset = random.randint(60, remaining)
        return (now + timedelta(seconds=offset)).timestamp()

    offset = random.randint(0, MORNING_WINDOW_SEC - 1)
    return (day_start + timedelta(seconds=offset)).timestamp()


def format_resume_time(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=TZ).strftime("%m-%d %H:%M")
