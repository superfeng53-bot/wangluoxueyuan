"""
调度器：定时 tick，按并发限制从 store 认领队列中的账号，启动 worker 线程。
复制到 <svc>/orchestrator.py，替换 <SVC> 包名，实现 WorkerFactory。
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

# 每秒最多启动的新 worker 数（错峰启动，与并发上限正交）
TICK_STARTS_PER_SECOND = 10


class Orchestrator:
    """
    使用方式（在 run_service.py 或 lifespan 中）：
        store = Store(db_path)
        store.startup_recovery()
        orch = Orchestrator(store, worker_factory=lambda acc: AccountWorker(acc, ...))
        orch.start()  # 启动后台 tick 线程
        ...
        orch.stop()
    """

    def __init__(
        self,
        store,                          # Store 实例
        worker_factory: Callable,       # worker_factory(account_dict) -> 有 run_once() 方法的对象
        apply_worker=None,              # [OPTIONAL:申请学分] ApplyWorker 实例；无申请流程时传 None
        tick_interval: float = 3.0,
    ) -> None:
        self._store = store
        self._worker_factory = worker_factory
        self._apply_worker = apply_worker
        self._tick_interval = tick_interval

        self._active = 0
        self._lock = threading.Lock()
        self._start_timestamps: list[float] = []
        self._cancel_events: dict[int, threading.Event] = {}

        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── 公开 API ──────────────────────────────────────────────────────────────

    @property
    def active_workers(self) -> int:
        return self._active

    def interrupt_account(self, account_id: int) -> None:
        """重学前中断正在运行的 worker 线程。"""
        with self._lock:
            ev = self._cancel_events.get(account_id)
        if ev:
            ev.set()

    def is_cancelled(self, account_id: int) -> bool:
        with self._lock:
            ev = self._cancel_events.get(account_id)
        return bool(ev and ev.is_set())

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="orchestrator")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    # ── 内部 ──────────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception:
                pass
            time.sleep(self._tick_interval)

    def _tick(self) -> None:
        now = time.time()

        # [OPTIONAL:申请学分] apply worker 不受 paused 影响（继续消化已学待申请的积压）
        if self._apply_worker is not None:
            try:
                self._apply_worker.process_one(now)
            except Exception:
                pass
        # [END OPTIONAL:申请学分]

        if self._store.is_paused():
            return

        limit = self._store.get_concurrency_limit()

        with self._lock:
            self._prune_start_timestamps(now)
            budget = min(
                TICK_STARTS_PER_SECOND - len(self._start_timestamps),
                max(0, limit - self._active),
            )

        for _ in range(budget):
            account = self._store.claim_next_queued(now)
            if not account:
                break
            with self._lock:
                self._start_timestamps.append(now)
                self._active += 1
            threading.Thread(
                target=self._run_account,
                args=(account,),
                daemon=True,
                name=f"worker-{account['id']}",
            ).start()

    def _prune_start_timestamps(self, now: float) -> None:
        cutoff = now - 1.0
        self._start_timestamps = [t for t in self._start_timestamps if t > cutoff]

    def _run_account(self, account: dict) -> None:
        acc_id = account["id"]
        cancel_ev = threading.Event()
        with self._lock:
            self._cancel_events[acc_id] = cancel_ev
        try:
            worker = self._worker_factory(account, cancel_event=cancel_ev)
            worker.run_once()
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                self._store.update_account_status(
                    account["id"], "queued", "orchestrator 异常", retry_delta=1
                )
            except Exception:
                pass
        finally:
            with self._lock:
                self._cancel_events.pop(acc_id, None)
                self._active -= 1
