"""状态机（通用，直接用）。

账号主状态、apply_queue 子状态：枚举、合法转移表、守卫函数、中文标签。
store / worker / apply_worker 经本模块校验转移；运维强制目标（queued / paused）可 bypass。

按能力裁剪：`has_credit=False` 时 `waiting_apply` 不可达。
"""
from __future__ import annotations

from enum import Enum


class AccountStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPLY = "waiting_apply"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ApplyStatus(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    DEAD = "dead"
    SKIPPED = "skipped"


class UnitState:
    """课程单元 state 字段（需求 §3.2）；无独立转移表，由业务写入。"""
    PENDING = ""
    PREFILL = "pending"   # 预匹配已选中、尚未开始学习
    RUNNING = "running"
    LEARNED = "learned"
    APPLIED = "applied"
    FAILED = "failed"
    SKIPPED = "skipped"

    TERMINAL = frozenset({APPLIED, FAILED, SKIPPED})


ACCOUNT_LABELS: dict[str, str] = {
    AccountStatus.QUEUED: "排队",
    AccountStatus.RUNNING: "进行中",
    AccountStatus.WAITING_APPLY: "等待申请",
    AccountStatus.COMPLETED: "已完成",
    AccountStatus.FAILED: "失败",
    AccountStatus.PAUSED: "已暂停",
}

APPLY_LABELS: dict[str, str] = {
    ApplyStatus.PENDING: "待申请",
    ApplyStatus.IN_FLIGHT: "申请中",
    ApplyStatus.SUCCEEDED: "已申请",
    ApplyStatus.DEAD: "申请失败",
    ApplyStatus.SKIPPED: "已跳过",
}


_ACCOUNT_TRANSITIONS: dict[AccountStatus, set[AccountStatus]] = {
    AccountStatus.QUEUED: {AccountStatus.RUNNING, AccountStatus.PAUSED},
    AccountStatus.RUNNING: {
        AccountStatus.COMPLETED, AccountStatus.WAITING_APPLY,
        AccountStatus.FAILED, AccountStatus.QUEUED,
        AccountStatus.PAUSED,
    },
    AccountStatus.WAITING_APPLY: {
        AccountStatus.COMPLETED, AccountStatus.RUNNING,
        AccountStatus.FAILED, AccountStatus.QUEUED,
    },
    AccountStatus.COMPLETED: {AccountStatus.QUEUED},
    AccountStatus.FAILED: {AccountStatus.QUEUED},
    AccountStatus.PAUSED: {AccountStatus.QUEUED},
}

_APPLY_TRANSITIONS: dict[ApplyStatus, set[ApplyStatus]] = {
    ApplyStatus.PENDING: {ApplyStatus.IN_FLIGHT, ApplyStatus.SKIPPED},
    ApplyStatus.IN_FLIGHT: {ApplyStatus.SUCCEEDED, ApplyStatus.PENDING, ApplyStatus.DEAD},
    ApplyStatus.SUCCEEDED: set(),
    ApplyStatus.DEAD: {ApplyStatus.PENDING},
    ApplyStatus.SKIPPED: {ApplyStatus.PENDING},
}

_FORCE_TARGETS = frozenset({AccountStatus.PAUSED.value, AccountStatus.QUEUED.value})


def reachable_account_states(*, has_credit: bool) -> list[str]:
    states = [s.value for s in AccountStatus]
    if not has_credit:
        states = [s for s in states if s != AccountStatus.WAITING_APPLY]
    return states


def can_transition(frm: str, to: str) -> bool:
    try:
        return AccountStatus(to) in _ACCOUNT_TRANSITIONS[AccountStatus(frm)]
    except (ValueError, KeyError):
        return False


def assert_account_transition(frm: str, to: str, *, force: bool = False) -> str:
    if frm == to:
        return to
    if force or is_force_target(to):
        return to
    if not can_transition(frm, to):
        raise ValueError(f"非法账号状态转移：{frm} -> {to}")
    return to


def can_apply_transition(frm: str, to: str) -> bool:
    try:
        return ApplyStatus(to) in _APPLY_TRANSITIONS[ApplyStatus(frm)]
    except (ValueError, KeyError):
        return False


def assert_apply_transition(frm: str, to: str) -> str:
    if frm == to:
        return to
    if not can_apply_transition(frm, to):
        raise ValueError(f"非法申请队列状态转移：{frm} -> {to}")
    return to


def is_force_target(to: str) -> bool:
    return to in _FORCE_TARGETS
